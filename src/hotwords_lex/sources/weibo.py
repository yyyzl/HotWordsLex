"""微博热搜"""

from __future__ import annotations

from .base import BaseSource


class WeiboSource(BaseSource):
    name = "微博热搜"

    def fetch(self, time_window_days: int = 3) -> list[str]:
        print(f"[{self.name}] 正在采集 ...")
        try:
            resp = self._request_with_retry(
                "https://weibo.com/ajax/side/hotSearch",
                headers={"Referer": "https://weibo.com/"},
            )
            data = resp.json()
            realtime = data.get("data", {}).get("realtime", [])
            texts = []
            for item in realtime:
                word = item.get("word", "").strip()
                if word:
                    label = item.get("label_name", "")
                    prefix = f"[{label}] " if label else ""
                    texts.append(f"[微博] {prefix}{word}")
            print(f"[{self.name}] 采集到 {len(texts)} 条")
            return texts
        except Exception as e:
            print(f"[{self.name}] 采集失败: {e}")
            return []
