"""API Key 池 - 轮询分配 + 限流 + 错误追踪"""

from __future__ import annotations

import itertools
import random
import threading
import time
from collections import Counter


class KeyPool:
    """线程安全的 API Key 轮询池，支持限流和错误追踪"""

    def __init__(self, keys: list[str], *, sleep_range: tuple[float, float] = (0.3, 1.0)):
        if not keys:
            raise ValueError("至少需要一个 API Key")
        self._keys = list(keys)
        self._cycle = itertools.cycle(range(len(keys)))
        self._lock = threading.Lock()
        self._sleep_range = sleep_range

        # 每个 key 的上次使用时间（限流用）
        self._last_used: dict[int, float] = {i: 0.0 for i in range(len(keys))}
        # 统计
        self._usage: Counter[int] = Counter()
        self._errors: Counter[int] = Counter()

    @property
    def size(self) -> int:
        return len(self._keys)

    def next_key(self) -> str:
        """获取下一个 key，自带随机 sleep 限流"""
        with self._lock:
            idx = next(self._cycle)
            self._usage[idx] += 1

            # 限流：确保同一 key 不会太快被复用
            now = time.time()
            elapsed = now - self._last_used[idx]
            min_interval = random.uniform(*self._sleep_range)
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_used[idx] = time.time()

        return self._keys[idx]

    def report_error(self, key: str) -> None:
        """报告某个 key 的错误"""
        try:
            idx = self._keys.index(key)
            with self._lock:
                self._errors[idx] += 1
        except ValueError:
            pass

    def stats(self) -> str:
        """返回 key 使用统计"""
        lines = []
        for i, k in enumerate(self._keys):
            masked = k[:8] + "..." + k[-4:] if len(k) > 16 else k[:4] + "..."
            lines.append(
                f"  Key {i:2d}: {masked}  调用={self._usage[i]:3d}  错误={self._errors[i]}"
            )
        return "\n".join(lines)

    def summary(self) -> str:
        """简要统计"""
        total_calls = sum(self._usage.values())
        total_errors = sum(self._errors.values())
        return (
            f"Keys: {self.size} | "
            f"总调用: {total_calls} | "
            f"总错误: {total_errors} | "
            f"错误率: {total_errors / max(total_calls, 1) * 100:.1f}%"
        )
