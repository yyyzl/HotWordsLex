"""Polymarket - 预测市场热门话题

免费公开 API，无需认证。
端点: https://gamma-api.polymarket.com/events
速率限制: 500 req/10s (events), 远超需求

预测市场反映真实关注度（真金白银下注），
话题涵盖地缘政治、科技、金融、体育等领域。
"""

from __future__ import annotations

import os

from .base import BaseSource

_API_BASE = "https://gamma-api.polymarket.com"

# 默认采集事件数量
_DEFAULT_EVENT_LIMIT = 100


class PolymarketSource(BaseSource):
    name = "Polymarket"
    timeout = 20

    def _get_event_limit(self) -> int:
        """从环境变量读取采集数量"""
        env_limit = os.environ.get("POLYMARKET_LIMIT", "").strip()
        if env_limit and env_limit.isdigit():
            return int(env_limit)
        return _DEFAULT_EVENT_LIMIT

    def fetch(self, time_window_days: int = 3) -> list[str]:
        limit = self._get_event_limit()
        print(f"[{self.name}] 正在采集热门预测市场事件(Top {limit}) ...")

        all_results: list[str] = []
        seen_slugs: set[str] = set()

        # 分页采集（每页最多 20 条以确保稳定性）
        page_size = 20
        offset = 0

        while len(all_results) < limit:
            try:
                batch = self._fetch_events_page(offset, page_size, seen_slugs)
                if not batch:
                    break
                all_results.extend(batch)
                offset += page_size
                self._sleep()
            except Exception as e:
                print(f"  [{self.name}] 请求失败: {e}")
                break

        all_results = all_results[:limit]
        print(f"[{self.name}] 采集到 {len(all_results)} 条")
        return all_results

    def _fetch_events_page(
        self,
        offset: int,
        limit: int,
        seen_slugs: set[str],
    ) -> list[str]:
        """获取一页热门事件"""
        url = f"{_API_BASE}/events"
        params = {
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
            "limit": limit,
            "offset": offset,
        }

        resp = self._request_with_retry(url, params=params)
        events = resp.json()

        if not isinstance(events, list):
            return []

        results: list[str] = []
        for event in events:
            slug = event.get("slug", "")
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            title = event.get("title", "").strip()
            if not title:
                continue

            # 提取交易量和流动性
            volume_str = self._format_volume(event.get("volume", "0"))
            volume_24h_str = self._format_volume(event.get("volume24hr", "0"))

            # 提取标签
            tags = event.get("tags", [])
            tag_labels = [t.get("label", "") for t in tags if t.get("label")]

            # 提取子市场数量
            markets = event.get("markets", [])
            market_count = len(markets)

            # 构建输出行
            line = f"[Polymarket] {title}"
            if volume_24h_str != "$0":
                line += f" (24h: {volume_24h_str})"
            elif volume_str != "$0":
                line += f" (总量: {volume_str})"
            if tag_labels:
                line += f" (tags: {', '.join(tag_labels[:5])})"
            if market_count > 1:
                line += f" [{market_count}个子市场]"

            results.append(line)

            # 同时提取高交易量的子市场标题（它们包含更具体的热词）
            for market in markets[:5]:  # 每个事件最多取 5 个子市场
                mkt_question = market.get("question", "").strip()
                mkt_slug = market.get("slug", "")
                if mkt_question and mkt_slug not in seen_slugs and mkt_question != title:
                    seen_slugs.add(mkt_slug)
                    mkt_vol = self._format_volume(market.get("volume", "0"))
                    results.append(f"[Polymarket] {mkt_question} (量: {mkt_vol})")

        return results

    @staticmethod
    def _format_volume(volume_raw: str | float | int) -> str:
        """格式化交易量: 1234567.89 → $1.2M"""
        try:
            vol = float(volume_raw)
        except (ValueError, TypeError):
            return "$0"

        if vol >= 1_000_000_000:
            return f"${vol / 1_000_000_000:.1f}B"
        if vol >= 1_000_000:
            return f"${vol / 1_000_000:.1f}M"
        if vol >= 1_000:
            return f"${vol / 1_000:.1f}K"
        if vol > 0:
            return f"${vol:.0f}"
        return "$0"
