"""百度热搜"""

from __future__ import annotations

from .base import BaseSource


class BaiduSource(BaseSource):
    name = "百度热搜"

    def fetch(self, time_window_days: int = 3) -> list[str]:
        print(f"[{self.name}] 正在采集 ...")
        try:
            resp = self._request_with_retry(
                "https://top.baidu.com/api/board",
                params={"tab": "realtime"},
            )
            data = resp.json()
            cards = data.get("data", {}).get("cards", [])
            texts = []
            for card in cards:
                for item in card.get("content", []):
                    word = item.get("word", "").strip()
                    desc = item.get("desc", "").strip()
                    if word:
                        line = f"[百度] {word}"
                        if desc:
                            line += f" - {desc[:100]}"
                        texts.append(line)
            print(f"[{self.name}] 采集到 {len(texts)} 条")
            return texts
        except Exception as e:
            print(f"[{self.name}] 采集失败: {e}")
            return []
