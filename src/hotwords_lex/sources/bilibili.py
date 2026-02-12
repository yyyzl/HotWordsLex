"""B站热搜 + 热门视频排行"""

from __future__ import annotations

from .base import BaseSource


class BilibiliSource(BaseSource):
    name = "B站"

    def fetch(self, time_window_days: int = 3) -> list[str]:
        print(f"[{self.name}] 正在采集 ...")
        texts = []

        # 1. 热搜词
        try:
            resp = self._request_with_retry(
                "https://s.search.bilibili.com/main/hotword",
            )
            data = resp.json()
            for item in data.get("list", []):
                word = item.get("keyword", "").strip()
                if word:
                    texts.append(f"[B站热搜] {word}")
        except Exception as e:
            print(f"  [{self.name}] 热搜采集失败: {e}")

        self._sleep()

        # 2. 热门视频排行
        try:
            resp = self._request_with_retry(
                "https://api.bilibili.com/x/web-interface/ranking/v2",
                params={"rid": "0", "type": "all"},
                headers={
                    "Referer": "https://www.bilibili.com/v/popular/rank/all",
                    "Origin": "https://www.bilibili.com",
                },
            )
            data = resp.json()
            items = data.get("data", {}).get("list", [])
            for item in items:
                title = item.get("title", "").strip()
                owner = item.get("owner", {}).get("name", "")
                tname = item.get("tname", "")
                if title:
                    line = f"[B站热门] {title}"
                    if tname:
                        line += f" ({tname})"
                    texts.append(line)
        except Exception as e:
            print(f"  [{self.name}] 热门视频采集失败: {e}")

        print(f"[{self.name}] 采集到 {len(texts)} 条")
        return texts
