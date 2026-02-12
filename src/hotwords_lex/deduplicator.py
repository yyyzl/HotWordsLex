"""智能去重引擎 — 对采集产出与 hotwords.txt 进行 4 规则去重

规则:
    1. 精确去重（忽略大小写）
    2. 单复数合并
    3. 大小写规范化（在 build_frequency_table 阶段处理）
    4. 版本号归并标记（不跳过，仅标记警告）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .hotword_store import HotwordStore

# 版本号正则：去掉常见版本号模式（要求分隔符或多位数字）
_VERSION_PATTERN = re.compile(
    r"[-\s][vV]?\d+(\.\d+)*(-\w+)?$"
    r"|"
    r"-[vV]\d+(\.\d+)*(-\w+)?$"
)
_VARIANT_PATTERN = re.compile(
    r"[-\s]?(Gen|Ultra|Pro|Flash|Mini|Lite|Max|Plus|Opus|Sonnet|Haiku)\s*\d*$",
    re.IGNORECASE,
)


def extract_base_name(term: str) -> str:
    """提取词的基础名，去掉版本号和变体后缀

    Examples:
        GPT-5.2         → gpt
        DeepSeek-V4     → deepseek
        Gemini 3 Ultra  → gemini
        Claude 4.5 Opus → claude
    """
    # 先去变体后缀（Ultra/Pro/Flash 等），再去版本号
    base = _VARIANT_PATTERN.sub("", term)
    base = _VERSION_PATTERN.sub("", base)
    return base.strip().lower()


@dataclass
class DeduplicationResult:
    """去重结果统计"""

    added: list[dict] = field(default_factory=list)
    skipped_exact: list[dict] = field(default_factory=list)
    skipped_plural: list[dict] = field(default_factory=list)
    version_warnings: list[dict] = field(default_factory=list)

    @property
    def summary(self) -> dict:
        return {
            "total_processed": (
                len(self.added)
                + len(self.skipped_exact)
                + len(self.skipped_plural)
            ),
            "added": len(self.added),
            "skipped_exact": len(self.skipped_exact),
            "skipped_plural": len(self.skipped_plural),
            "version_warnings": len(self.version_warnings),
        }


class SmartDeduplicator:
    """智能去重器：对采集结果与 hotwords.txt 已有词进行多规则去重"""

    def __init__(self, store: HotwordStore):
        self._store = store
        self._terms_info = store.get_all_terms_with_info()
        # 构建 base_name 索引，用于版本号归并检测
        self._base_name_index: dict[str, list[tuple[str, str]]] = {}
        for lower_key, (original, cat) in self._terms_info.items():
            base = extract_base_name(original)
            if base:
                self._base_name_index.setdefault(base, []).append(
                    (original, cat)
                )
        self.result = DeduplicationResult()

    def deduplicate(self, terms: list[dict]) -> list[dict]:
        """对高频词列表进行智能去重

        Args:
            terms: build_frequency_table + filter_by_frequency 产出的词列表

        Returns:
            通过去重的新词列表
        """
        new_terms = []
        for t in terms:
            term = t.get("term", "").strip()
            if not term:
                continue

            action = self._check(term, t)
            if action == "add":
                new_terms.append(t)

        return new_terms

    def _check(self, term: str, entry: dict) -> str:
        """检查单个词，返回 'add' 或 'skip'"""
        lower = term.lower()
        freq = entry.get("frequency", 0)
        cat = entry.get("category", "AI")

        # 规则 1：精确去重（忽略大小写）
        info = self._store.get_term_info(term)
        if info:
            original, existing_cat = info
            self.result.skipped_exact.append({
                "term": term,
                "reason": f"已存在于【{existing_cat}】分类（原始写法: {original}）",
            })
            return "skip"

        # 规则 2：单复数合并
        # 2a: 新词是复数 → 检查单数是否已在 hotwords.txt
        if lower.endswith("s") and len(lower) > 2:
            singular = lower[:-1]
            singular_info = self._store.get_term_info(singular)
            if singular_info:
                original, existing_cat = singular_info
                self.result.skipped_plural.append({
                    "term": term,
                    "kept": original,
                    "reason": f"单数形式 {original} 已存在于【{existing_cat}】",
                })
                return "skip"
            # 尝试去掉 es
            if lower.endswith("es") and len(lower) > 3:
                singular_es = lower[:-2]
                singular_es_info = self._store.get_term_info(singular_es)
                if singular_es_info:
                    original, existing_cat = singular_es_info
                    self.result.skipped_plural.append({
                        "term": term,
                        "kept": original,
                        "reason": f"单数形式 {original} 已存在于【{existing_cat}】",
                    })
                    return "skip"

        # 2b: 新词是单数 → 检查复数是否已在 hotwords.txt
        plural = lower + "s"
        plural_info = self._store.get_term_info(plural)
        if plural_info:
            original, existing_cat = plural_info
            self.result.skipped_plural.append({
                "term": term,
                "kept": original,
                "reason": f"复数形式 {original} 已存在于【{existing_cat}】",
            })
            return "skip"

        # 规则 4：版本号归并标记（不跳过，仅标记）
        base = extract_base_name(term)
        if base and base in self._base_name_index:
            existing_versions = self._base_name_index[base]
            # 只在 base_name 不等于 term 本身的完整小写时才标记
            # （避免完全相同的词触发误报）
            for existing_term, existing_cat in existing_versions:
                if existing_term.lower() != lower:
                    self.result.version_warnings.append({
                        "new_term": term,
                        "existing_term": existing_term,
                        "base_name": base,
                        "action": "已添加，请人工确认",
                    })
                    break  # 只记录一次

        # 通过所有规则 → 添加
        self.result.added.append({
            "term": term,
            "category": cat,
            "frequency": freq,
        })
        return "add"
