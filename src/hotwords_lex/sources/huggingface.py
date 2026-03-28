"""Hugging Face Hub - Trending 模型 / Space / Dataset"""

from __future__ import annotations

from .base import BaseSource


class HuggingFaceSource(BaseSource):
    name = "HuggingFace"

    def fetch(self, time_window_days: int = 3) -> list[str]:
        print(f"[{self.name}] 采集 Trending 模型 / Space ...")
        results: list[str] = []

        # ── Trending Models ──────────────────────────────────────────────
        try:
            resp = self._request_with_retry(
                "https://huggingface.co/api/models",
                params={"sort": "trending", "limit": 100, "direction": -1},
                headers={"Accept": "application/json"},
            )
            for m in resp.json():
                model_id = m.get("modelId") or m.get("id", "")
                if not model_id:
                    continue
                pipeline = m.get("pipeline_tag", "")
                tags = [t for t in m.get("tags", []) if len(t) < 40][:4]
                # 取 org/name 中的 name 部分作为更易读的标签
                short_name = model_id.split("/")[-1] if "/" in model_id else model_id
                line = f"[HuggingFace] {model_id} - {short_name}"
                if pipeline:
                    line += f" ({pipeline})"
                if tags:
                    line += f" [tags: {', '.join(tags[:3])}]"
                results.append(line)
            print(f"  [{self.name}] 模型: {len(results)} 条")
        except Exception as e:
            print(f"  [{self.name}] 模型采集失败: {e}")

        self._sleep()

        # ── Trending Spaces ──────────────────────────────────────────────
        space_count = 0
        try:
            resp = self._request_with_retry(
                "https://huggingface.co/api/spaces",
                params={"sort": "trending", "limit": 50, "direction": -1},
                headers={"Accept": "application/json"},
            )
            for s in resp.json():
                space_id = s.get("id", "")
                if not space_id:
                    continue
                sdk = s.get("sdk", "")
                short_name = space_id.split("/")[-1] if "/" in space_id else space_id
                line = f"[HuggingFace Space] {space_id} - {short_name}"
                if sdk:
                    line += f" ({sdk})"
                results.append(line)
                space_count += 1
            print(f"  [{self.name}] Space: {space_count} 条")
        except Exception as e:
            print(f"  [{self.name}] Space 采集失败: {e}")

        print(f"[{self.name}] 总计 {len(results)} 条")
        return results
