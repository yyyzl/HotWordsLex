"""arXiv - 最新 AI/ML/NLP 论文（cs.AI + cs.LG + cs.CL）"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .base import BaseSource

_API_URL = "https://export.arxiv.org/api/query"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# AI 相关分类
_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.RO"]


class ArxivSource(BaseSource):
    name = "arXiv"

    def fetch(self, time_window_days: int = 3) -> list[str]:
        print(f"[{self.name}] 采集最新 AI 论文 ...")
        results: list[str] = []

        query = " OR ".join(f"cat:{c}" for c in _CATEGORIES)
        try:
            resp = self._request_with_retry(
                _API_URL,
                params={
                    "search_query": query,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "max_results": 200,
                    "start": 0,
                },
            )
            root = ET.fromstring(resp.content)
            entries = root.findall("atom:entry", _ATOM_NS)
            for entry in entries:
                title_el = entry.find("atom:title", _ATOM_NS)
                summary_el = entry.find("atom:summary", _ATOM_NS)
                title = (title_el.text or "").replace("\n", " ").strip()
                summary = (summary_el.text or "").replace("\n", " ").strip()[:120]
                if not title:
                    continue
                # 取论文所属分类标签
                cats = [
                    t.get("term", "")
                    for t in entry.findall("atom:category", _ATOM_NS)
                    if t.get("term", "").startswith("cs.")
                ]
                line = f"[arXiv] {title}"
                if summary:
                    line += f" - {summary}"
                if cats:
                    line += f" [{', '.join(cats[:3])}]"
                results.append(line)

            print(f"[{self.name}] 采集到 {len(results)} 条")
        except Exception as e:
            print(f"[{self.name}] 采集失败: {e}")

        return results
