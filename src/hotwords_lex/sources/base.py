"""数据源基类 - 含限流、重试、User-Agent 随机化"""

from __future__ import annotations

import random
import threading
import time
from abc import ABC, abstractmethod

import requests

# 常见浏览器 User-Agent 列表
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
]

_thread_local = threading.local()


class BaseSource(ABC):
    """数据源基类"""

    name: str = "未命名"
    # 请求间隔范围（秒）
    min_interval: float = 1.0
    max_interval: float = 2.0
    # 请求超时
    timeout: int = 20
    # 最大重试
    max_retries: int = 3

    def _get_session(self) -> requests.Session:
        """线程局部 Session（直连，不走系统代理）"""
        if not hasattr(_thread_local, "session"):
            s = requests.Session()
            s.proxies = {"http": None, "https": None}
            s.trust_env = False
            _thread_local.session = s
        return _thread_local.session

    def _get_headers(self, extra: dict | None = None) -> dict:
        """随机 User-Agent 请求头"""
        headers = {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if extra:
            headers.update(extra)
        return headers

    def _sleep(self) -> None:
        """请求间隔 sleep"""
        time.sleep(random.uniform(self.min_interval, self.max_interval))

    def _request_with_retry(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        method: str = "GET",
    ) -> requests.Response:
        """带重试和指数退避的 HTTP 请求"""
        session = self._get_session()
        req_headers = self._get_headers(headers)

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = session.request(
                    method, url,
                    params=params,
                    headers=req_headers,
                    timeout=self.timeout,
                )
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    print(f"  [{self.name}] 429 限流，等待 {wait}s 后重试")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    print(f"  [{self.name}] 请求失败({attempt}/{self.max_retries}): {e}，{wait}s 后重试")
                    time.sleep(wait)
                else:
                    raise

        # 不可达，但 mypy 需要
        raise requests.RequestException(f"[{self.name}] 重试 {self.max_retries} 次均失败")

    @abstractmethod
    def fetch(self, time_window_days: int = 3) -> list[str]:
        """采集数据，返回格式化文本列表

        每条文本格式: [来源标签] 标题/内容
        """
        ...
