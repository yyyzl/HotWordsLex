"""LLM 提取模块 - 5轮并行提取，18分类 + ASR聚焦 Prompt"""

from __future__ import annotations

import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .key_pool import KeyPool

# 线程局部 Session
_thread_local = threading.local()


def _get_session() -> requests.Session:
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.proxies = {"http": None, "https": None}
        s.trust_env = False
        _thread_local.session = s
    return _thread_local.session


# ============================================================================
# Prompt - 对齐18分类 + ASR聚焦
# ============================================================================

EXTRACTION_PROMPT = """你是一个热词采集专家，专门为 ASR（语音识别）系统维护热词库。

我会给你一批来自各平台的热门内容标题。你的任务是从中提取 **ASR 不容易正确识别的名词和专有名词**。

## 提取目标

重点提取以下类型的词（这些词 ASR 容易识别错误）：
1. **品牌名/产品名**：如 DeepSeek、Kimi、仰望U8、理想MEGA
2. **新造词/网络用语**：如 显眼包、搭子、松弛感、去班味
3. **英文缩写/术语**：如 RAG、LoRA、RLHF、GLP-1、eVTOL
4. **中英混合词**：如 AI搜索、vibe coding、端侧AI
5. **非标准拼写/谐音词**：如 扩列、塌房、硬控
6. **专业术语**：如 量化加速、端到端大模型、一体化压铸
7. **人名（热点相关）**：如 雷军、黄仁勋（仅限高热度人名）
8. **技术框架/工具名**：如 Cursor、Shadcn UI、Hono

## 严格排除

- ASR 已能准确识别的常见词（如：手机、电脑、人工智能、视频、新闻）
- 过于宽泛的通用词（如：发展、趋势、未来、创新）
- 纯数字或日期
- 语气词和助词

## 分类

使用以下 18 个分类之一：
AI、编程、职场、数码、汽车、金融、社交、购物、设计、健康、旅游、文娱、营销、法律、人力、教育、房产、运动、政务

如果不确定归属哪个分类，使用最接近的。技术相关优先归入「AI」或「编程」。

## 输出格式

输出 JSON 数组，每个元素格式：
{"term": "原始词", "category": "分类名"}

规则：
1. term 保持原始大小写和拼写
2. 尽可能多提取，宁多勿少（后续通过词频筛选）
3. 只输出 JSON 数组，不要有其他文字"""


def call_llm(
    texts: list[str],
    api_key: str,
    *,
    endpoint: str,
    model: str,
    timeout: int = 90,
) -> list[dict]:
    """调用 LLM 提取热词"""
    content = "\n".join(texts)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {
                "role": "user",
                "content": f"请从以下 {len(texts)} 条热门内容中提取 ASR 热词：\n\n{content}",
            },
        ],
        "temperature": 0.3,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    resp = _get_session().post(endpoint, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    result = resp.json()
    reply = result["choices"][0]["message"]["content"].strip()

    return _parse_json_array(reply)


def _parse_json_array(text: str) -> list[dict]:
    """从 LLM 回复中提取 JSON 数组"""
    # 尝试直接解析
    try:
        terms = json.loads(text)
        if isinstance(terms, list):
            return terms
    except json.JSONDecodeError:
        pass

    # 提取 ``` 代码块
    if "```" in text:
        start = text.find("```")
        end = text.rfind("```")
        if start != end:
            block = text[start:end]
            first_newline = block.find("\n")
            if first_newline != -1:
                inner = block[first_newline + 1:]
                try:
                    terms = json.loads(inner)
                    if isinstance(terms, list):
                        return terms
                except json.JSONDecodeError:
                    pass

    # 提取 [...] 部分
    bracket_start = text.find("[")
    bracket_end = text.rfind("]")
    if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
        try:
            terms = json.loads(text[bracket_start:bracket_end + 1])
            if isinstance(terms, list):
                return terms
        except json.JSONDecodeError:
            pass

    return []


def _process_one_batch(
    batch_id: int,
    batch: list[str],
    key_pool: KeyPool,
    round_num: int,
    total_batches: int,
    *,
    endpoint: str,
    model: str,
    timeout: int,
) -> list[dict]:
    """处理单个批次（带重试 + 换 key）"""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        key = key_pool.next_key()
        try:
            terms = call_llm(
                batch, key,
                endpoint=endpoint, model=model, timeout=timeout,
            )
            print(f"  [R{round_num}] 批次 {batch_id}/{total_batches} → {len(terms)} 个词")
            return terms
        except requests.exceptions.HTTPError as e:
            key_pool.report_error(key)
            if e.response is not None and e.response.status_code == 429:
                print(f"  [R{round_num}] 批次 {batch_id} 限流(429)，等 10s 换 key")
                time.sleep(10)
            elif attempt < max_retries:
                wait = 2 ** attempt
                print(f"  [R{round_num}] 批次 {batch_id} 失败({attempt}): {e}，{wait}s 后重试")
                time.sleep(wait)
            else:
                print(f"  [R{round_num}] 批次 {batch_id} 放弃: {e}")
        except Exception as e:
            key_pool.report_error(key)
            if attempt < max_retries:
                wait = 2 ** attempt
                print(f"  [R{round_num}] 批次 {batch_id} 失败({attempt}): {e}，{wait}s 后重试")
                time.sleep(wait)
            else:
                print(f"  [R{round_num}] 批次 {batch_id} 放弃: {e}")
    return []


def extract_terms(
    raw_texts: list[str],
    key_pool: KeyPool,
    *,
    endpoint: str,
    model: str,
    rounds: int = 5,
    batch_size: int = 50,
    max_workers: int = 30,
    timeout: int = 90,
) -> list[dict]:
    """多轮并行提取：每轮打乱数据，所有批次并发"""
    all_terms: list[dict] = []
    print(f"\n[提取] {key_pool.size} 个 Key, 最大并发 {max_workers}, 共 {rounds} 轮")

    for round_num in range(1, rounds + 1):
        print(f"\n{'=' * 50}")
        print(f"[提取] 第 {round_num}/{rounds} 轮")
        print(f"{'=' * 50}")

        # 每轮打乱数据
        shuffled = raw_texts.copy()
        if round_num > 1:
            random.shuffle(shuffled)

        # 切分批次
        batches = [
            shuffled[i:i + batch_size]
            for i in range(0, len(shuffled), batch_size)
        ]
        total_batches = len(batches)
        print(f"  共 {total_batches} 个批次，最大 {max_workers} 并发")

        round_terms: list[dict] = []
        t0 = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(
                    _process_one_batch,
                    idx, batch, key_pool, round_num, total_batches,
                    endpoint=endpoint, model=model, timeout=timeout,
                ): idx
                for idx, batch in enumerate(batches, 1)
            }
            for future in as_completed(futures):
                try:
                    terms = future.result()
                    round_terms.extend(terms)
                except Exception as e:
                    print(f"  [R{round_num}] 批次异常: {e}")

        elapsed = time.time() - t0
        print(f"  [R{round_num}] 本轮 {len(round_terms)} 个词，耗时 {elapsed:.1f}s")
        all_terms.extend(round_terms)

    print(f"\n[提取] 全部 {rounds} 轮共 {len(all_terms)} 个词（含重复）")
    return all_terms
