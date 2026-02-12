"""数据源统一调度模块"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from .weibo import WeiboSource
from .baidu import BaiduSource
from .bilibili import BilibiliSource
from .toutiao import ToutiaoSource
from .douyin import DouyinSource
from .hackernews import HackerNewsSource
from .github import GitHubSource
from .devto import DevToSource

ALL_SOURCES = [
    WeiboSource,
    BaiduSource,
    BilibiliSource,
    ToutiaoSource,
    DouyinSource,
    HackerNewsSource,
    GitHubSource,
    DevToSource,
]


def collect_all(time_window_days: int = 3) -> list[str]:
    """并行采集所有数据源，返回合并的原始文本列表"""
    all_texts: list[str] = []
    sources = [cls() for cls in ALL_SOURCES]

    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        future_map = {
            pool.submit(_safe_fetch, src, time_window_days): src.name
            for src in sources
        }
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                texts = future.result()
                if texts:
                    all_texts.extend(texts)
                    print(f"[采集] {name}: {len(texts)} 条")
                else:
                    print(f"[采集] {name}: 无数据")
            except Exception as e:
                print(f"[采集] {name}: 失败 - {e}")

    print(f"[采集] 总计 {len(all_texts)} 条原始文本")
    return all_texts


def _safe_fetch(source, time_window_days: int) -> list[str]:
    """安全调用单个数据源"""
    return source.fetch(time_window_days)
