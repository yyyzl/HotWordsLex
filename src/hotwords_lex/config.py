"""配置管理 - 支持 .env / 环境变量 / CLI 参数 / keys.txt"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """全局配置，优先级：CLI 参数 > 环境变量 > .env 文件 > keys.txt > 默认值"""

    # LLM
    llm_api_keys: list[str] = field(default_factory=list)
    llm_endpoint: str = "https://api.longcat.chat/openai/v1/chat/completions"
    llm_model: str = "LongCat-Flash-Lite"

    # 采集参数
    extract_rounds: int = 5
    min_frequency: int = 50
    time_window_days: int = 3
    batch_size: int = 50

    # 文件路径
    hotwords_file: str = "hotwords.txt"
    output_dir: str = "output"
    publish_repo: str = ""
    publish_ref: str = "main"

    # 网络
    request_timeout: int = 20
    llm_timeout: int = 90
    proxy: str = "none"

    # 并发
    max_llm_workers: int = 30
    hn_concurrency: int = 10


def load_config(
    *,
    api_key: str | None = None,
    keys_file: str | None = None,
    endpoint: str | None = None,
    model: str | None = None,
    rounds: int | None = None,
    min_freq: int | None = None,
    days: int | None = None,
    batch_size: int | None = None,
    hotwords_file: str | None = None,
    output_dir: str | None = None,
    publish_repo: str | None = None,
    publish_ref: str | None = None,
    proxy: str | None = None,
) -> Config:
    """从多个来源加载配置"""
    # 本地运行加载 .env；GitHub Actions 仅使用工作流注入的 secrets/vars
    is_github_actions = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
    if not is_github_actions:
        load_dotenv()

    cfg = Config()

    # LLM 端点
    cfg.llm_endpoint = (
        endpoint
        or os.environ.get("LLM_ENDPOINT")
        or cfg.llm_endpoint
    )

    # LLM 模型
    cfg.llm_model = (
        model
        or os.environ.get("LLM_MODEL")
        or cfg.llm_model
    )

    # 采集参数
    if rounds is not None:
        cfg.extract_rounds = rounds
    elif os.environ.get("EXTRACT_ROUNDS"):
        cfg.extract_rounds = int(os.environ["EXTRACT_ROUNDS"])

    if min_freq is not None:
        cfg.min_frequency = min_freq
    elif os.environ.get("MIN_FREQUENCY"):
        cfg.min_frequency = int(os.environ["MIN_FREQUENCY"])

    if days is not None:
        cfg.time_window_days = days
    elif os.environ.get("TIME_WINDOW_DAYS"):
        cfg.time_window_days = int(os.environ["TIME_WINDOW_DAYS"])

    if batch_size is not None:
        cfg.batch_size = batch_size

    # 文件路径
    cfg.hotwords_file = (
        hotwords_file
        or os.environ.get("HOTWORDS_FILE")
        or cfg.hotwords_file
    )
    cfg.output_dir = output_dir or cfg.output_dir
    cfg.publish_repo = (
        publish_repo
        or os.environ.get("HOTWORDS_PUBLISH_REPO")
        or cfg.publish_repo
    )
    cfg.publish_ref = (
        publish_ref
        or os.environ.get("HOTWORDS_PUBLISH_REF")
        or cfg.publish_ref
    )

    # 代理
    if proxy is not None:
        cfg.proxy = proxy

    # API Keys 加载
    cfg.llm_api_keys = _load_keys(api_key, keys_file)

    return cfg


def _load_keys(api_key_arg: str | None, keys_file: str | None) -> list[str]:
    """从多个来源加载 API Key 列表"""
    keys: list[str] = []

    # 1. 从文件加载
    if keys_file:
        path = Path(keys_file)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                k = line.strip()
                if k and not k.startswith("#"):
                    keys.append(k)
            if keys:
                print(f"[Key] 从文件 {keys_file} 加载了 {len(keys)} 个 key")
                return keys

    # 2. 从 CLI 参数（逗号分隔）
    if api_key_arg:
        parts = [k.strip() for k in api_key_arg.split(",") if k.strip()]
        if parts:
            print(f"[Key] 从参数加载了 {len(parts)} 个 key")
            return parts

    # 3. 从环境变量 LLM_API_KEYS
    env_keys = os.environ.get("LLM_API_KEYS", "")
    if env_keys:
        parts = [k.strip() for k in env_keys.split(",") if k.strip()]
        if parts:
            print(f"[Key] 从 LLM_API_KEYS 环境变量加载了 {len(parts)} 个 key")
            return parts

    # 4. 从环境变量 LLM_API_KEY（单个）
    env_key = os.environ.get("LLM_API_KEY", "")
    if env_key:
        print("[Key] 从 LLM_API_KEY 环境变量加载了 1 个 key")
        return [env_key]

    return keys
