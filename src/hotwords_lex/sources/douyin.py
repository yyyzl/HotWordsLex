"""抖音热榜（第三方 API）"""

from __future__ import annotations

from .base import BaseSource


class DouyinSource(BaseSource):
    name = "抖音热榜"

    def fetch(self, time_window_days: int = 3) -> list[str]:
        print(f"[{self.name}] 正在采集 ...")
        try:
            resp = self._request_with_retry(
                "https://v2.xxapi.cn/api/douyinhot",
            )
            data = resp.json()

            texts = []
            items = data.get("data", [])
            if not items and isinstance(data, list):
                items = data

            for item in items:
                title = ""
                if isinstance(item, dict):
                    title = (
                        item.get("title", "")
                        or item.get("word", "")
                        or item.get("name", "")
                    ).strip()
                elif isinstance(item, str):
                    title = item.strip()

                if title:
                    texts.append(f"[抖音] {title}")

            print(f"[{self.name}] 采集到 {len(texts)} 条")
            return texts
        except Exception as e:
            print(f"[{self.name}] 采集失败: {e}")
            return []
