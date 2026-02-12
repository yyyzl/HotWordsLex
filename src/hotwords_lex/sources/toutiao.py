"""今日头条热榜"""

from __future__ import annotations

from .base import BaseSource


class ToutiaoSource(BaseSource):
    name = "今日头条"

    def fetch(self, time_window_days: int = 3) -> list[str]:
        print(f"[{self.name}] 正在采集 ...")
        try:
            resp = self._request_with_retry(
                "https://www.toutiao.com/hot-event/hot-board/",
                params={"origin": "toutiao_pc"},
                headers={"Referer": "https://www.toutiao.com/"},
            )
            data = resp.json()
            items = data.get("data", [])
            texts = []
            for item in items:
                title = item.get("Title", "").strip()
                if title:
                    texts.append(f"[头条] {title}")
            print(f"[{self.name}] 采集到 {len(texts)} 条")
            return texts
        except Exception as e:
            print(f"[{self.name}] 采集失败: {e}")
            return []
