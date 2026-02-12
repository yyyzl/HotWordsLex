"""变更日志 — 记录每次合并的详细操作"""

from __future__ import annotations

import json
import os
from datetime import datetime

from .deduplicator import DeduplicationResult


def write_changelog(
    result: DeduplicationResult,
    *,
    total_collected: int,
    source_hotwords: str,
    output_dir: str,
) -> str:
    """输出 changelog JSON 文件

    Args:
        result: SmartDeduplicator 的去重结果
        total_collected: 高频词总数（去重前）
        source_hotwords: hotwords.txt 文件路径
        output_dir: 输出目录

    Returns:
        changelog 文件路径
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"changelog_{timestamp}.json")

    changelog = {
        "generated_at": datetime.now().isoformat(),
        "source_hotwords": source_hotwords,
        "summary": {
            "total_collected": total_collected,
            **result.summary,
        },
        "details": {
            "added": result.added,
            "skipped_exact": result.skipped_exact,
            "skipped_plural": result.skipped_plural,
            "version_warnings": result.version_warnings,
        },
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(changelog, f, ensure_ascii=False, indent=2)

    print(f"  变更日志: {filepath}")
    return filepath
