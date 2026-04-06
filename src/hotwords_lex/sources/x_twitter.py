"""X (Twitter) - 全球/地区热门趋势

需要 Bearer Token (Basic 层 $200/月 或 Pay-Per-Use 模式)。
未设置 X_BEARER_TOKEN 时自动跳过，不影响其他数据源。

端点: GET /2/trends/by/woeid/:id
速率限制: 15 req/15min (Basic), 75 req/15min (Pro)
"""

from __future__ import annotations

import os

from .base import BaseSource

# WOEID (Where On Earth ID) 映射
# 可通过环境变量 X_WOEID_LIST 覆盖（逗号分隔，如 "1,23424977,23424856"）
_DEFAULT_WOEIDS: list[tuple[int, str]] = [
    (1, "全球"),
    (23424977, "美国"),
    (23424856, "日本"),
    (23424975, "英国"),
]

_API_BASE = "https://api.x.com"


class XTwitterSource(BaseSource):
    name = "X/Twitter"
    timeout = 20

    def _get_bearer_token(self) -> str:
        """从环境变量获取 Bearer Token"""
        return os.environ.get("X_BEARER_TOKEN", "").strip()

    def _parse_woeid_config(self) -> list[tuple[int, str]]:
        """解析 WOEID 配置"""
        env_woeids = os.environ.get("X_WOEID_LIST", "").strip()
        if env_woeids:
            result = []
            for part in env_woeids.split(","):
                part = part.strip()
                if part.isdigit():
                    result.append((int(part), f"WOEID-{part}"))
            if result:
                return result
        return list(_DEFAULT_WOEIDS)

    def fetch(self, time_window_days: int = 3) -> list[str]:
        token = self._get_bearer_token()
        if not token:
            print(f"[{self.name}] 未设置 X_BEARER_TOKEN，跳过")
            print(f"  提示: export X_BEARER_TOKEN='your-bearer-token'")
            return []

        woeids = self._parse_woeid_config()
        print(f"[{self.name}] 正在采集 {len(woeids)} 个地区的热门趋势 ...")

        all_results: list[str] = []
        seen_trends: set[str] = set()

        for woeid, region_name in woeids:
            try:
                trends = self._fetch_trends(token, woeid, region_name, seen_trends)
                all_results.extend(trends)
                print(f"  [{self.name}] {region_name}(WOEID={woeid}): {len(trends)} 条")
            except Exception as e:
                print(f"  [{self.name}] {region_name}(WOEID={woeid}): 失败 - {e}")
            self._sleep()

        print(f"[{self.name}] 总计采集 {len(all_results)} 条（去重后）")
        return all_results

    def _fetch_trends(
        self,
        token: str,
        woeid: int,
        region_name: str,
        seen: set[str],
    ) -> list[str]:
        """获取单个地区的热门趋势"""
        url = f"{_API_BASE}/2/trends/by/woeid/{woeid}"
        headers = {"Authorization": f"Bearer {token}"}

        resp = self._request_with_retry(url, headers=headers)
        data = resp.json()

        results: list[str] = []
        trends = data.get("data", [])

        for trend in trends:
            trend_name = trend.get("trend_name", "").strip()
            if not trend_name or trend_name in seen:
                continue
            seen.add(trend_name)

            tweet_count = trend.get("tweet_count", 0)
            line = f"[X趋势/{region_name}] {trend_name}"
            if tweet_count:
                line += f" ({tweet_count:,} 推)"
            results.append(line)

        return results
