"""Hacker News - top/new/best 各 500"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from .base import BaseSource


class HackerNewsSource(BaseSource):
    name = "HackerNews"
    # HN API story 详情并发数（保守）
    story_concurrency: int = 10

    def fetch(self, time_window_days: int = 3) -> list[str]:
        limit = 500
        print(f"[{self.name}] 正在采集 top/new/best 各 {limit} ...")
        base_url = "https://hacker-news.firebaseio.com/v0"

        # 收集 story IDs（去重）
        story_ids: list[int] = []
        seen: set[int] = set()

        for endpoint in ("topstories", "newstories", "beststories"):
            try:
                resp = self._request_with_retry(f"{base_url}/{endpoint}.json")
                ids = resp.json()
                cap = limit if endpoint == "topstories" else limit // 2
                for sid in ids[:cap]:
                    if sid not in seen:
                        story_ids.append(sid)
                        seen.add(sid)
                self._sleep()
            except Exception as e:
                print(f"  [{self.name}] {endpoint} 失败: {e}")

        print(f"  [{self.name}] 共 {len(story_ids)} 个 story ID")

        # 并发获取标题
        titles: list[str] = []

        def _fetch_title(sid: int) -> str | None:
            try:
                r = self._get_session().get(
                    f"{base_url}/item/{sid}.json", timeout=self.timeout
                )
                r.raise_for_status()
                data = r.json()
                if data and data.get("title"):
                    return data["title"]
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=self.story_concurrency) as pool:
            futures = {pool.submit(_fetch_title, sid): sid for sid in story_ids}
            for future in as_completed(futures):
                title = future.result()
                if title:
                    titles.append(f"[HN] {title}")

        print(f"[{self.name}] 采集到 {len(titles)} 条")
        return titles
