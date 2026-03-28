"""Reddit - AI/ML 社区热帖（r/LocalLLaMA、r/MachineLearning 等）"""

from __future__ import annotations

import time

from .base import BaseSource

# AI 相关 subreddit（按重要性排序）
_AI_SUBREDDITS = [
    "LocalLLaMA",
    "MachineLearning",
    "artificial",
    "singularity",
    "OpenAI",
]

_POSTS_PER_SUB = 50


class RedditSource(BaseSource):
    name = "Reddit"
    # Reddit 对频繁请求较敏感，放宽间隔
    min_interval: float = 2.0
    max_interval: float = 3.0

    def fetch(self, time_window_days: int = 3) -> list[str]:
        print(f"[{self.name}] 采集 AI 社区热帖 ...")
        results: list[str] = []

        for sub in _AI_SUBREDDITS:
            try:
                resp = self._request_with_retry(
                    f"https://www.reddit.com/r/{sub}/hot.json",
                    params={"limit": _POSTS_PER_SUB},
                    headers={
                        # Reddit 要求非浏览器 UA 须标注来源
                        "User-Agent": "hotwords-lex/1.0 (hot-word collection bot)",
                    },
                )
                children = resp.json().get("data", {}).get("children", [])
                sub_count = 0
                for child in children:
                    post = child.get("data", {})
                    title = post.get("title", "").strip()
                    flair = post.get("link_flair_text", "") or ""
                    if not title:
                        continue
                    line = f"[Reddit r/{sub}] {title}"
                    if flair:
                        line += f" [{flair}]"
                    results.append(line)
                    sub_count += 1
                print(f"  [{self.name}] r/{sub}: {sub_count} 条")
            except Exception as e:
                print(f"  [{self.name}] r/{sub} 失败: {e}")
            self._sleep()

        print(f"[{self.name}] 总计 {len(results)} 条")
        return results
