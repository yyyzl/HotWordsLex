"""IT之家 - RSS 新闻（AI / 数码 / 科技）"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .base import BaseSource

_RSS_URL = "https://www.ithome.com/rss/"


class ITHomeSource(BaseSource):
    name = "IT之家"

    def fetch(self, time_window_days: int = 3) -> list[str]:
        print(f"[{self.name}] 采集 RSS 新闻 ...")
        results: list[str] = []

        try:
            resp = self._request_with_retry(
                _RSS_URL,
                headers={"Accept": "application/rss+xml, text/xml, */*"},
            )
            root = ET.fromstring(resp.content)
            ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
            channel = root.find("channel")
            if channel is None:
                print(f"[{self.name}] 未找到 channel")
                return results

            for item in channel.findall("item"):
                title_el = item.find("title")
                desc_el = item.find("description")
                title = (title_el.text or "").strip() if title_el is not None else ""
                if not title:
                    continue
                # 从 description 中提取纯文本摘要（strip HTML tags）
                raw_desc = (desc_el.text or "") if desc_el is not None else ""
                # 去除 HTML 标签，取前 100 字
                import re
                plain = re.sub(r"<[^>]+>", "", raw_desc).strip()[:100]
                line = f"[IT之家] {title}"
                if plain:
                    line += f" - {plain}"
                results.append(line)

            print(f"[{self.name}] 采集到 {len(results)} 条")
        except Exception as e:
            print(f"[{self.name}] 采集失败: {e}")

        return results
