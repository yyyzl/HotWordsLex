"""主入口 + CLI"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime

from .config import Config, load_config
from .key_pool import KeyPool
from .hotword_store import HotwordStore
from .deduplicator import SmartDeduplicator, DeduplicationResult
from .changelog import write_changelog
from .sources import collect_all
from .extractor import extract_terms
from .filter import (
    build_frequency_table,
    filter_by_frequency,
    asr_filter,
    compute_frequency_distribution,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HotWordsLex - 网络热词自动采集系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  # 快速测试（2轮，低频阈值）
  uv run python -m hotwords_lex --keys-file keys.txt --rounds 2 --min-freq 5

  # 完整运行（默认 5 轮，频次 >= 50）
  uv run python -m hotwords_lex --keys-file keys.txt

  # 指定参数
  uv run python -m hotwords_lex --keys-file keys.txt --rounds 3 --min-freq 20 --days 7
""",
    )
    parser.add_argument("--api-key", help="LLM API Key（逗号分隔多个）")
    parser.add_argument("--keys-file", help="API Key 文件路径（每行一个）")
    parser.add_argument("--endpoint", help="LLM API Endpoint")
    parser.add_argument("--model", help="LLM 模型名")
    parser.add_argument("--rounds", type=int, help="提取轮次（默认5）")
    parser.add_argument("--min-freq", type=int, help="最低频次阈值（默认50）")
    parser.add_argument("--days", type=int, help="时间窗口天数（默认3）")
    parser.add_argument("--batch-size", type=int, help="每批文本条数（默认50）")
    parser.add_argument("--hotwords-file", help="热词库路径（默认 hotwords.txt）")
    parser.add_argument("--output", help="输出目录（默认 output）")
    parser.add_argument("--publish-repo", help="发布仓库 owner/repo（用于生成镜像地址）")
    parser.add_argument("--publish-ref", help="发布分支（用于生成镜像地址，默认 main）")
    parser.add_argument("--proxy", help="代理: 'none'=直连, 'auto'=系统, 或地址")
    return parser.parse_args()


def run(cfg: Config) -> None:
    """主运行流程"""
    if not cfg.llm_api_keys:
        print("错误：未设置 LLM API Key")
        print("设置方式：")
        print("  1. --api-key KEY1,KEY2,KEY3")
        print("  2. --keys-file keys.txt（每行一个 key）")
        print("  3. export LLM_API_KEYS='KEY1,KEY2,KEY3'")
        sys.exit(1)

    key_pool = KeyPool(cfg.llm_api_keys)

    # 打印配置
    print("=" * 70)
    print("  HotWordsLex - 网络热词自动采集系统")
    print("=" * 70)
    print(f"  LLM:          {cfg.llm_model} @ {cfg.llm_endpoint}")
    print(f"  API Keys:     {key_pool.size} 个")
    print(f"  最大并发:     {cfg.max_llm_workers}")
    print(f"  时间窗口:     最近 {cfg.time_window_days} 天")
    print(f"  提取轮次:     {cfg.extract_rounds} 轮")
    print(f"  高频阈值:     >= {cfg.min_frequency} 次")
    print(f"  热词库:       {cfg.hotwords_file}")
    print()

    t_start = time.time()

    # ============================================================
    # Phase 1: 并行采集所有数据源
    # ============================================================
    print("[Phase 1] 并行采集数据源 ...")
    raw_texts = collect_all(cfg.time_window_days)

    if not raw_texts:
        print("\n[错误] 所有数据源采集失败，无数据可处理")
        sys.exit(1)

    t_fetch = time.time()
    print(f"\n[Phase 1] 数据采集完成，耗时 {t_fetch - t_start:.1f}s，共 {len(raw_texts)} 条\n")

    # ============================================================
    # Phase 2: 多轮 LLM 提取
    # ============================================================
    print("[Phase 2] LLM 多轮提取 ...")
    raw_terms = extract_terms(
        raw_texts,
        key_pool,
        endpoint=cfg.llm_endpoint,
        model=cfg.llm_model,
        rounds=cfg.extract_rounds,
        batch_size=cfg.batch_size,
        max_workers=cfg.max_llm_workers,
        timeout=cfg.llm_timeout,
    )

    if not raw_terms:
        print("\n[错误] LLM 未能提取到任何词")
        sys.exit(1)

    t_extract = time.time()
    total_raw_count = len(raw_terms)
    print(f"\n[Phase 2] LLM 提取完成，耗时 {t_extract - t_fetch:.1f}s\n")

    # ============================================================
    # Phase 3: 词频统计 + 筛选 + 智能去重
    # ============================================================
    print("[Phase 3] 词频统计 + 筛选 + 智能去重 ...")
    freq_table = build_frequency_table(raw_terms)
    unique_count = len(freq_table)
    print(f"  去重后唯一词: {unique_count}（含单复数合并、大小写规范化）")

    freq_distribution = compute_frequency_distribution(freq_table)

    # 频次筛选
    high_freq_terms = filter_by_frequency(freq_table, cfg.min_frequency)
    print(f"  高频词(>={cfg.min_frequency}次): {len(high_freq_terms)}")

    # ASR 过滤
    high_freq_terms = asr_filter(high_freq_terms)

    # 加载 hotwords.txt + 智能去重
    store = HotwordStore(cfg.hotwords_file)
    store.load()

    deduper = SmartDeduplicator(store)
    high_freq_terms = deduper.deduplicate(high_freq_terms)
    dedup_result = deduper.result

    print(f"  智能去重结果:")
    print(f"    精确跳过: {len(dedup_result.skipped_exact)}")
    print(f"    单复数跳过: {len(dedup_result.skipped_plural)}")
    print(f"    版本号警告: {len(dedup_result.version_warnings)}")
    print(f"    新增词数: {len(dedup_result.added)}")

    # ============================================================
    # Phase 4: 合并输出
    # ============================================================
    print(f"\n[Phase 4] 合并输出 ...")

    # 回写 hotwords.txt
    added_count = store.add_words(high_freq_terms)
    store.save()
    print(f"  新增 {added_count} 个词条到 {cfg.hotwords_file}")

    # 输出合并后的词表副本
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(cfg.output_dir, exist_ok=True)
    merged_path = os.path.join(cfg.output_dir, f"hotwords_merged_{timestamp}.txt")
    _write_merged_hotwords(store, merged_path)
    print(f"  合并词表: {merged_path}")

    latest_path, latest_meta_path = _write_latest_publish_files(
        store,
        source_hotwords=cfg.hotwords_file,
        output_dir=cfg.output_dir,
        merged_snapshot=merged_path,
        publish_repo=cfg.publish_repo,
        publish_ref=cfg.publish_ref,
    )
    print(f"  最新词表: {latest_path}")
    print(f"  发布清单: {latest_meta_path}")

    # 输出 changelog
    changelog_path = write_changelog(
        dedup_result,
        total_collected=len(filter_by_frequency(freq_table, cfg.min_frequency)),
        source_hotwords=cfg.hotwords_file,
        output_dir=cfg.output_dir,
    )

    # ============================================================
    # Phase 5: 输出报告
    # ============================================================
    print(f"\n[Phase 5] 输出报告 ...")
    _save_report(
        high_freq_terms, freq_distribution, total_raw_count, unique_count,
        raw_texts, key_pool, cfg, dedup_result,
    )
    _print_summary(
        high_freq_terms, freq_distribution, total_raw_count, unique_count,
        added_count, key_pool, cfg, dedup_result,
    )

    t_total = time.time() - t_start
    print(f"\n总耗时: {t_total:.1f}s")
    print(f"  采集: {t_fetch - t_start:.1f}s")
    print(f"  LLM:  {t_extract - t_fetch:.1f}s")
    print(f"  后处: {time.time() - t_extract:.1f}s")


def _write_merged_hotwords(store: HotwordStore, filepath: str) -> None:
    """输出合并后的完整词表副本（不修改原文件，空分类不输出）"""
    lines = []
    for cat in store._category_order:
        words = store.categories.get(cat, [])
        if not words:
            continue
        line = f"\u3010{cat}\u3011:[{','.join(words)}]"
        lines.append(line)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_latest_publish_files(
    store: HotwordStore,
    *,
    source_hotwords: str,
    output_dir: str,
    merged_snapshot: str,
    publish_repo: str,
    publish_ref: str,
) -> tuple[str, str]:
    """输出供外部项目拉取的稳定发布文件"""
    latest_path = os.path.join(output_dir, "hotwords_latest.txt")
    _write_merged_hotwords(store, latest_path)

    with open(latest_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()

    total_terms = sum(len(words) for words in store.categories.values())
    non_empty_categories = sum(1 for words in store.categories.values() if words)

    meta = {
        "generated_at": datetime.now().isoformat(),
        "source_hotwords": source_hotwords,
        "snapshot_file": os.path.basename(merged_snapshot),
        "latest_file": os.path.basename(latest_path),
        "sha256": digest,
        "total_terms": total_terms,
        "non_empty_categories": non_empty_categories,
    }

    meta_path = os.path.join(output_dir, "hotwords_latest.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    endpoints_path = _write_mirror_endpoints(
        output_dir=output_dir,
        publish_repo=publish_repo,
        publish_ref=publish_ref,
    )
    if endpoints_path:
        print(f"  镜像地址: {endpoints_path}")

    return latest_path, meta_path


def _write_mirror_endpoints(
    *,
    output_dir: str,
    publish_repo: str,
    publish_ref: str,
) -> str | None:
    """输出镜像加速地址清单，供外部项目顺序回退拉取"""
    repo = publish_repo.strip()
    if not repo or "/" not in repo:
        return None

    ref = (publish_ref or "main").strip() or "main"
    txt_path = "output/hotwords_latest.txt"
    json_path = "output/hotwords_latest.json"

    payload = {
        "generated_at": datetime.now().isoformat(),
        "repo": repo,
        "ref": ref,
        "strategy": "ordered-fallback",
        "notes": [
            "按 endpoints 顺序尝试，第一个成功即使用",
            "前 2/5/6 为第三方镜像，稳定性不保证，建议保留直连兜底",
        ],
        "artifacts": {
            "hotwords_latest.txt": {
                "path": txt_path,
                "endpoints": _build_mirror_urls(repo, ref, txt_path),
            },
            "hotwords_latest.json": {
                "path": json_path,
                "endpoints": _build_mirror_urls(repo, ref, json_path),
            },
        },
    }

    filepath = os.path.join(output_dir, "hotwords_latest_endpoints.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filepath


def _build_mirror_urls(repo: str, ref: str, artifact_path: str) -> list[str]:
    """生成 6 个镜像源地址（顺序即回退顺序）"""
    owner, name = repo.split("/", 1)
    raw = f"https://raw.githubusercontent.com/{owner}/{name}/{ref}/{artifact_path}"
    return [
        f"https://gh-proxy.org/{raw}",
        f"https://hk.gh-proxy.org/{raw}",
        f"https://cdn.jsdelivr.net/gh/{owner}/{name}@{ref}/{artifact_path}",
        raw,
        f"https://cdn.gh-proxy.org/{raw}",
        f"https://edgeone.gh-proxy.org/{raw}",
    ]


def _save_report(
    terms: list[dict],
    freq_distribution: dict,
    total_raw: int,
    unique_count: int,
    raw_texts: list[str],
    key_pool: KeyPool,
    cfg: Config,
    dedup_result: DeduplicationResult,
) -> None:
    """保存详细报告到 output 目录"""
    os.makedirs(cfg.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report_path = os.path.join(cfg.output_dir, f"report_{timestamp}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "config": {
                "time_window_days": cfg.time_window_days,
                "extract_rounds": cfg.extract_rounds,
                "min_frequency": cfg.min_frequency,
                "batch_size": cfg.batch_size,
                "api_key_count": key_pool.size,
                "max_workers": cfg.max_llm_workers,
                "total_raw_texts": len(raw_texts),
            },
            "stats": {
                "total_raw_extractions": total_raw,
                "unique_terms": unique_count,
                "high_frequency_terms": len(terms),
            },
            "deduplication": dedup_result.summary,
            "frequency_distribution": freq_distribution,
            "terms": terms,
        }, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {report_path}")


def _print_summary(
    terms: list[dict],
    freq_distribution: dict,
    total_raw: int,
    unique_count: int,
    added_count: int,
    key_pool: KeyPool,
    cfg: Config,
    dedup_result: DeduplicationResult,
) -> None:
    """打印采集报告"""
    print("\n" + "=" * 70)
    print("  HotWordsLex 采集报告")
    print("=" * 70)

    print(f"\n统计：")
    print(f"  LLM 提取总次数（含重复）: {total_raw}")
    print(f"  去重后唯一词数:           {unique_count}")
    print(f"  高频词 (>={cfg.min_frequency}次):    {len(terms)}")
    print(f"  新增到词库:               {added_count}")

    # 智能去重详情
    print(f"\n智能去重详情：")
    print(f"  精确匹配跳过:  {len(dedup_result.skipped_exact)}")
    print(f"  单复数合并跳过: {len(dedup_result.skipped_plural)}")
    print(f"  版本号警告:     {len(dedup_result.version_warnings)}")
    if dedup_result.version_warnings:
        for vw in dedup_result.version_warnings:
            print(f"    ! {vw['new_term']} ← 已有 {vw['existing_term']}（base: {vw['base_name']}）")

    # 频率分布
    print(f"\n频率分布：")
    if freq_distribution:
        max_count = max(freq_distribution.values())
        max_bar = 40
        for freq_label, count in freq_distribution.items():
            bar_len = int(count / max(max_count, 1) * max_bar)
            bar = "#" * bar_len
            marker = " <-- 过滤线" if freq_label == f"{cfg.min_frequency}次" else ""
            print(f"  {freq_label:>5s} | {bar} {count}{marker}")

    # 分类统计
    categories: dict[str, int] = {}
    for t in terms:
        cat = t.get("category", "AI")
        categories[cat] = categories.get(cat, 0) + 1

    print(f"\n分类统计（高频新词）：")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat:>6s}: {count:3d} 个")

    # Top 50
    print(f"\nTop 50 高频热词：")
    print(f"  {'#':>3s}  {'频次':>4s}  {'分类':>6s}  {'词'}")
    print(f"  {'---':>3s}  {'----':>4s}  {'------':>6s}  {'---'}")
    for i, t in enumerate(terms[:50]):
        freq = t["frequency"]
        cat = t.get("category", "?")
        print(f"  {i + 1:3d}  {freq:4d}  [{cat:>4s}]  {t['term']}")

    if len(terms) > 50:
        print(f"\n  ... 还有 {len(terms) - 50} 个高频词，查看 output 目录")

    # Key 统计
    print(f"\nKey 使用统计：")
    print(key_pool.summary())


def main() -> None:
    """CLI 入口"""
    args = parse_args()
    cfg = load_config(
        api_key=args.api_key,
        keys_file=args.keys_file,
        endpoint=args.endpoint,
        model=args.model,
        rounds=args.rounds,
        min_freq=args.min_freq,
        days=args.days,
        batch_size=args.batch_size,
        hotwords_file=args.hotwords_file,
        output_dir=args.output,
        publish_repo=args.publish_repo,
        publish_ref=args.publish_ref,
        proxy=args.proxy,
    )
    run(cfg)


if __name__ == "__main__":
    main()
