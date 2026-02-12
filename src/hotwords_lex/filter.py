"""词频统计 + ASR 过滤"""

from __future__ import annotations

import re
from collections import Counter


def normalize_term(term: str) -> str:
    """归一化：全角→半角、大写→小写、去除前后空白"""
    # 全角→半角
    result = []
    for ch in term:
        code = ord(ch)
        # 全角空格
        if code == 0x3000:
            result.append(" ")
        # 全角字符范围
        elif 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        else:
            result.append(ch)
    return "".join(result).strip().lower()


def _try_merge_plural(key: str, freq_table: dict[str, dict]) -> str | None:
    """尝试找到单复数合并目标，返回应合并到的 key 或 None"""
    # key 以 s 结尾 → 尝试合并到去掉 s 的单数形式
    if key.endswith("s") and len(key) > 2:
        singular = key[:-1]
        if singular in freq_table:
            return singular
        # 尝试去掉 es（如 boxes → box）
        if key.endswith("es") and len(key) > 3:
            singular_es = key[:-2]
            if singular_es in freq_table:
                return singular_es
    return None


def build_frequency_table(raw_terms: list[dict]) -> dict[str, dict]:
    """构建词频表（归一化后统计）

    增强：
    - 记录每种大小写形式的出现次数（_case_variants）
    - 单复数合并：LLMs → LLM，合并频率到单数形式
    - 最终 term 取最高频的大小写变体
    """
    freq_table: dict[str, dict] = {}

    for t in raw_terms:
        term = t.get("term", "").strip()
        if not term:
            continue

        key = normalize_term(term)
        if not key:
            continue

        category = t.get("category", "AI")

        # 单复数合并：如果当前 key 是复数形式且单数已存在 → 合并到单数
        merge_target = _try_merge_plural(key, freq_table)
        if merge_target:
            freq_table[merge_target]["frequency"] += 1
            freq_table[merge_target]["_categories"][category] += 1
            freq_table[merge_target]["_case_variants"][term] += 1
            continue

        if key not in freq_table:
            freq_table[key] = {
                "term": term,
                "frequency": 0,
                "category": category,
                "_categories": Counter(),
                "_case_variants": Counter(),
            }

        freq_table[key]["frequency"] += 1
        freq_table[key]["_categories"][category] += 1
        freq_table[key]["_case_variants"][term] += 1

    # 第二遍：把已有的复数 key 合并到单数 key（处理先出现复数后出现单数的情况）
    keys_to_remove = []
    for key in list(freq_table.keys()):
        if key.endswith("s") and len(key) > 2:
            singular = key[:-1]
            if singular in freq_table and singular != key:
                # 合并复数到单数
                freq_table[singular]["frequency"] += freq_table[key]["frequency"]
                freq_table[singular]["_categories"] += freq_table[key]["_categories"]
                freq_table[singular]["_case_variants"] += freq_table[key]["_case_variants"]
                keys_to_remove.append(key)
    for key in keys_to_remove:
        del freq_table[key]

    # 最终处理：确定 term 为最高频大小写变体 + 确定分类
    for entry in freq_table.values():
        if entry["_case_variants"]:
            entry["term"] = entry["_case_variants"].most_common(1)[0][0]
        if entry["_categories"]:
            entry["category"] = entry["_categories"].most_common(1)[0][0]
        del entry["_categories"]
        del entry["_case_variants"]

    return freq_table


def filter_by_frequency(freq_table: dict[str, dict], min_freq: int = 50) -> list[dict]:
    """筛选高频词"""
    filtered = [e for e in freq_table.values() if e["frequency"] >= min_freq]
    filtered.sort(key=lambda x: x["frequency"], reverse=True)
    return filtered


# ASR 已能识别的常见中文词（排除列表）
_COMMON_CHINESE_WORDS = {
    "手机", "电脑", "人工智能", "视频", "新闻", "音乐", "电影", "电视",
    "游戏", "购物", "旅游", "健康", "教育", "工作", "生活", "科技",
    "互联网", "网络", "软件", "硬件", "数据", "信息", "系统", "平台",
    "应用", "服务", "技术", "产品", "公司", "市场", "用户", "内容",
    "发展", "趋势", "未来", "创新", "智能", "数字", "云计算", "大数据",
    "物联网", "机器人", "自动化", "虚拟现实", "增强现实",
}

# 纯中文正则
_PURE_CHINESE = re.compile(r"^[\u4e00-\u9fff]+$")

# 纯常见英文单词（不是专有名词）
_COMMON_ENGLISH = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "new", "old", "how", "what", "why", "who", "when", "where",
    "build", "make", "use", "using", "used", "get", "set",
    "open", "close", "start", "stop", "run", "test", "check",
    "code", "data", "web", "app", "api", "tool", "tools",
    "top", "best", "first", "last", "next", "update", "release",
}


def asr_filter(terms: list[dict]) -> list[dict]:
    """ASR 过滤：保留 ASR 难以识别的词

    保留规则：
    - 英文缩写（2-6个大写字母）
    - 品牌名/产品名（含数字或特殊大小写）
    - 中英混合词
    - 包含数字的词
    - 非标准拼写的中文网络用语
    - 专业术语（含连字符、点号等）

    排除规则：
    - 纯中文常见词
    - 纯常见英文单词
    - 太短的词（<2字符）
    """
    filtered = []

    for t in terms:
        term = t.get("term", "").strip()
        if not term or len(term) < 2:
            continue

        # 排除常见英文单词
        if term.lower() in _COMMON_ENGLISH:
            continue

        # 排除 ASR 已能识别的常见中文词
        if term in _COMMON_CHINESE_WORDS:
            continue

        # 纯中文词的额外检查：只排除特别常见的
        # 网络用语、新造词等虽然是纯中文但 ASR 不一定能识别，保留
        if _PURE_CHINESE.match(term) and len(term) <= 2 and term in _COMMON_CHINESE_WORDS:
            continue

        filtered.append(t)

    removed = len(terms) - len(filtered)
    if removed:
        print(f"[ASR过滤] 过滤掉 {removed} 个常见词，保留 {len(filtered)} 个")
    return filtered


def deduplicate_with_existing(terms: list[dict], existing_words: set[str]) -> list[dict]:
    """与现有词库去重"""
    if not existing_words:
        return terms

    filtered = []
    for t in terms:
        term = t.get("term", "").strip()
        if normalize_term(term) not in existing_words:
            filtered.append(t)

    removed = len(terms) - len(filtered)
    if removed:
        print(f"[去重] 过滤掉 {removed} 个已存在的词，剩余 {len(filtered)} 个")
    return filtered


def compute_frequency_distribution(freq_table: dict[str, dict]) -> dict[str, int]:
    """计算频次分布"""
    dist: dict[int, int] = {}
    for entry in freq_table.values():
        f = entry["frequency"]
        dist[f] = dist.get(f, 0) + 1
    result = {}
    for freq in sorted(dist.keys()):
        result[f"{freq}次"] = dist[freq]
    return result
