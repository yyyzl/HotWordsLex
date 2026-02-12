"""Dev.to - 近 N 天热门文章"""

from __future__ import annotations

from .base import BaseSource


class DevToSource(BaseSource):
    name = "Dev.to"
    article_limit: int = 300

    def fetch(self, time_window_days: int = 3) -> list[str]:
        print(f"[{self.name}] 正在采集近 {time_window_days} 天热门文章 ...")
        results: list[str] = []
        page = 1
        per_page = 30

        while len(results) < self.article_limit:
            try:
                resp = self._request_with_retry(
                    "https://dev.to/api/articles",
                    params={"top": time_window_days, "per_page": per_page, "page": page},
                )
                articles = resp.json()
                if not articles:
                    break
                for article in articles:
                    title = article.get("title", "")
                    tags = article.get("tag_list", [])
                    desc = article.get("description", "") or ""

                    line = f"[Dev.to] {title}"
                    if desc:
                        line += f" - {desc[:100]}"
                    if tags:
                        line += f" (tags: {', '.join(tags[:8])})"
                    results.append(line)

                page += 1
                if len(articles) < per_page:
                    break
                self._sleep()
            except Exception as e:
                print(f"  [{self.name}] 请求失败: {e}")
                break

        results = results[:self.article_limit]
        print(f"[{self.name}] 采集到 {len(results)} 条")
        return results
