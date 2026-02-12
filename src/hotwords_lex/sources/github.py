"""GitHub - 按 star 分层搜索，Token 认证，突破单次 1000 上限"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

from .base import BaseSource

# star 分层搜索策略：每层最多 1000 条（API 上限）
_STAR_TIERS = [
    ("stars:>500", 1000),
    ("stars:50..500", 1000),
    ("stars:10..50", 1000),
]


class GitHubSource(BaseSource):
    name = "GitHub"
    per_tier_limit: int = 1000

    def _get_auth_headers(self) -> dict:
        """构建带 Token 认证的请求头"""
        headers = {"Accept": "application/vnd.github.v3+json"}
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def fetch(self, time_window_days: int = 3) -> list[str]:
        token = os.environ.get("GITHUB_TOKEN", "")
        auth_info = "已认证(5000/h)" if token else "未认证(10/min)"
        print(f"[{self.name}] {auth_info}，按 star 分层搜索近 {time_window_days} 天仓库 ...")

        since = (datetime.now(timezone.utc) - timedelta(days=time_window_days)).strftime("%Y-%m-%d")
        all_results: list[str] = []
        seen_names: set[str] = set()

        for star_query, limit in _STAR_TIERS:
            tier_results = self._search_tier(star_query, since, limit, seen_names)
            all_results.extend(tier_results)

        print(f"[{self.name}] 总计采集 {len(all_results)} 条（去重后）")
        return all_results

    def _search_tier(
        self, star_query: str, since: str, limit: int, seen: set[str],
    ) -> list[str]:
        """搜索单个 star 层级"""
        results: list[str] = []
        page = 1
        per_page = 100
        auth_headers = self._get_auth_headers()

        while len(results) < limit:
            try:
                resp = self._request_with_retry(
                    "https://api.github.com/search/repositories",
                    params={
                        "q": f"{star_query} pushed:>{since}",
                        "sort": "stars",
                        "order": "desc",
                        "per_page": per_page,
                        "page": page,
                    },
                    headers=auth_headers,
                )
                data = resp.json()
                items = data.get("items", [])
                if not items:
                    break

                for item in items:
                    full_name = item.get("full_name", "")
                    if full_name in seen:
                        continue
                    seen.add(full_name)

                    name = item.get("name", "")
                    desc = item.get("description", "") or ""
                    topics = item.get("topics", [])
                    lang = item.get("language", "") or ""

                    line = f"[GitHub] {name}"
                    if desc:
                        line += f" - {desc[:150]}"
                    if topics:
                        line += f" (topics: {', '.join(topics[:8])})"
                    if lang:
                        line += f" [{lang}]"
                    results.append(line)

                page += 1
                remaining = resp.headers.get("X-RateLimit-Remaining", "?")
                print(f"  [{self.name}] {star_query} p{page - 1}, +{len(items)}, 累计 {len(results)}, 剩余: {remaining}")

                if len(items) < per_page:
                    break
                # GitHub Search API: 认证用户 30 req/min，翻页间隔 2s 足够
                time.sleep(2.0)
            except Exception as e:
                print(f"  [{self.name}] {star_query} 请求失败: {e}")
                break

        results = results[:limit]
        print(f"  [{self.name}] {star_query}: {len(results)} 条")
        return results
