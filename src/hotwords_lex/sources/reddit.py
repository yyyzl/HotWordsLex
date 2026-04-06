"""Reddit - AI/编程/科技/金融等子版块热门帖子

三层降级策略:
1. OAuth JSON API（如有 REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET）
   - 60 req/min, oauth.reddit.com, 100 条/子版块, 含 score
2. RSS Feed（零配置默认主力）
   - 无需认证, 不受 TLS 指纹检测影响
   - 25 条/子版块, 含标题/作者/时间/链接
3. 公开 JSON API（最终兜底，大概率被 403）
"""

from __future__ import annotations

import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

import requests

from .base import BaseSource

# 默认子版块列表 - 按领域分组
# 可通过环境变量 REDDIT_SUBREDDITS 覆盖（逗号分隔）
_DEFAULT_SUBREDDITS: list[tuple[str, str]] = [
    # === AI & LLM ===
    ("LocalLLaMA", "AI"),           # 本地 LLM 部署: Ollama, vLLM, GGUF, QLoRA
    ("ChatGPT", "AI"),              # ChatGPT 生态: GPT-4o, Custom GPTs, DALL-E
    ("OpenAI", "AI"),               # OpenAI 产品: Sora, Whisper, Codex
    ("MachineLearning", "AI"),      # 学术 ML: Transformer, LoRA, RLHF
    ("ClaudeAI", "AI"),             # Anthropic/Claude: MCP, Artifacts
    ("singularity", "AI"),          # AGI/未来技术: scaling laws, ASI
    ("Artificial", "AI"),           # 通用 AI: NLP, computer vision, robotics
    ("StableDiffusion", "AI"),      # AI 图像生成: ComfyUI, ControlNet, Flux
    # === 编程 & 开发 ===
    ("programming", "编程"),         # 编程全领域: Rust, Zig, Bun, WebAssembly
    ("webdev", "编程"),              # Web 开发: Next.js, Tailwind, Vercel
    ("Python", "编程"),              # Python 生态: FastAPI, Pydantic, uv, Ruff
    ("rust", "编程"),                # Rust: tokio, cargo, borrow checker
    ("devops", "编程"),              # DevOps: Kubernetes, Terraform, ArgoCD
    # === 科技 & 数码 ===
    ("technology", "数码"),          # 科技新闻: Apple Vision Pro, Starlink, TSMC
    ("hardware", "数码"),            # PC 硬件: RTX 5090, AM5, DDR5
    ("gadgets", "数码"),             # 消费电子: iPhone, Galaxy, AirPods
    ("Apple", "数码"),               # Apple 生态: M4, macOS, Apple Intelligence
    ("Android", "数码"),             # Android: Pixel, OneUI, Gemini Nano
    # === 金融 ===
    ("CryptoCurrency", "金融"),      # 加密货币: Bitcoin ETF, DeFi, ZK-rollup
    ("wallstreetbets", "金融"),      # 股票/期权: NVDA, TSLA, short squeeze
    # === 娱乐 ===
    ("gaming", "文娱"),              # 游戏: GTA VI, Elden Ring, Steam Deck
]

# User-Agent
_REDDIT_UA = "HotWordsLex/1.0 (ASR hot-words collector)"

# 速率控制
_OAUTH_INTERVAL = 1.0   # OAuth: 60 req/min
_RSS_INTERVAL = 2.0     # RSS: 保守间隔，避免被限
_PUBLIC_INTERVAL = 6.0  # 公开 JSON: ~10 req/min

# Atom XML 命名空间
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class RedditSource(BaseSource):
    name = "Reddit"
    timeout = 30

    def __init__(self) -> None:
        super().__init__()
        self._access_token: str | None = None
        self._mode: str = "rss"  # "oauth" | "rss" | "json"
        self._request_interval: float = _RSS_INTERVAL

    # ------------------------------------------------------------------
    # 模式选择
    # ------------------------------------------------------------------

    def _select_mode(self) -> None:
        """按优先级选择访问模式"""
        # 1. 尝试 OAuth
        if self._try_oauth_login():
            return

        # 2. 默认 RSS（零配置，已验证稳定）
        self._mode = "rss"
        self._request_interval = _RSS_INTERVAL
        print(f"  [{self.name}] 使用 RSS Feed 模式（零配置，25条/子版块）")

    def _try_oauth_login(self) -> bool:
        """尝试 OAuth 认证"""
        client_id = os.environ.get("REDDIT_CLIENT_ID", "").strip()
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            return False

        print(f"  [{self.name}] OAuth 认证中 ...")
        try:
            session = self._get_session()
            resp = session.post(
                "https://www.reddit.com/api/v1/access_token",
                data={"grant_type": "client_credentials"},
                auth=(client_id, client_secret),
                headers={"User-Agent": _REDDIT_UA},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token", "")
            if token:
                self._access_token = token
                self._mode = "oauth"
                self._request_interval = _OAUTH_INTERVAL
                print(f"  [{self.name}] OAuth 认证成功 (60 req/min, 100条/子版块)")
                return True
        except Exception as e:
            print(f"  [{self.name}] OAuth 认证失败: {e}，回退到 RSS")
        return False

    # ------------------------------------------------------------------
    # 子版块配置
    # ------------------------------------------------------------------

    def _parse_subreddit_config(self) -> list[tuple[str, str]]:
        """解析子版块配置"""
        env_subs = os.environ.get("REDDIT_SUBREDDITS", "").strip()
        if env_subs:
            result = []
            for part in env_subs.split(","):
                part = part.strip()
                if not part:
                    continue
                if ":" in part:
                    name, category = part.split(":", 1)
                    result.append((name.strip(), category.strip()))
                else:
                    result.append((part, "AI"))
            if result:
                return result
        return list(_DEFAULT_SUBREDDITS)

    # ------------------------------------------------------------------
    # 主采集流程
    # ------------------------------------------------------------------

    def fetch(self, time_window_days: int = 3) -> list[str]:
        subreddits = self._parse_subreddit_config()
        print(f"[{self.name}] 正在采集 {len(subreddits)} 个子版块 ...")

        self._select_mode()

        all_results: list[str] = []
        seen_titles: set[str] = set()

        for idx, (sub_name, _category) in enumerate(subreddits):
            try:
                if self._mode == "oauth":
                    posts = self._fetch_oauth(sub_name, time_window_days, seen_titles)
                else:
                    posts = self._fetch_rss(sub_name, time_window_days, seen_titles)

                all_results.extend(posts)
                print(f"  [{self.name}] r/{sub_name}: {len(posts)} 条"
                      f" ({idx + 1}/{len(subreddits)})")
            except Exception as e:
                print(f"  [{self.name}] r/{sub_name}: 失败 - {e}")

            # 速率控制（最后一个不需要 sleep）
            if idx < len(subreddits) - 1:
                time.sleep(self._request_interval)

        print(f"[{self.name}] 总计采集 {len(all_results)} 条")
        return all_results

    # ------------------------------------------------------------------
    # RSS 采集（零配置主力方案）
    # ------------------------------------------------------------------

    def _fetch_rss(
        self,
        subreddit: str,
        time_window_days: int,
        seen_titles: set[str],
    ) -> list[str]:
        """通过 RSS Feed 采集（不受 TLS 指纹检测影响）"""
        url = f"https://www.reddit.com/r/{subreddit}/hot.rss"
        req = urllib.request.Request(url, headers={"User-Agent": _REDDIT_UA})

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)
        entries = root.findall("atom:entry", _ATOM_NS)
        results: list[str] = []

        # 时间窗口边界
        now_utc = datetime.now(timezone.utc)
        cutoff_seconds = time_window_days * 86400

        for entry in entries:
            title_el = entry.find("atom:title", _ATOM_NS)
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            if not title:
                continue

            # 标题去重
            title_lower = title.lower()
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)

            # 时间窗口过滤
            updated_el = entry.find("atom:updated", _ATOM_NS)
            if updated_el is not None and updated_el.text:
                try:
                    post_time = datetime.fromisoformat(updated_el.text)
                    if (now_utc - post_time).total_seconds() > cutoff_seconds:
                        continue
                except (ValueError, TypeError):
                    pass  # 解析失败则不过滤

            # 提取分类标签
            category_el = entry.find("atom:category", _ATOM_NS)
            flair = category_el.get("label", "") if category_el is not None else ""

            line = f"[Reddit/r/{subreddit}] {title}"
            if flair and flair != subreddit:
                line += f" [{flair}]"
            results.append(line)

        return results

    # ------------------------------------------------------------------
    # OAuth JSON 采集（高配方案）
    # ------------------------------------------------------------------

    def _fetch_oauth(
        self,
        subreddit: str,
        time_window_days: int,
        seen_titles: set[str],
    ) -> list[str]:
        """通过 OAuth JSON API 采集（100 条/子版块，含 score）"""
        url = f"https://oauth.reddit.com/r/{subreddit}/hot.json"
        headers = {
            "User-Agent": _REDDIT_UA,
            "Authorization": f"Bearer {self._access_token}",
        }
        params = {"limit": 100, "raw_json": 1}

        resp = self._request_with_retry(url, params=params, headers=headers)
        data = resp.json()

        children = data.get("data", {}).get("children", [])
        results: list[str] = []

        now_utc = datetime.now(timezone.utc).timestamp()
        cutoff = now_utc - time_window_days * 86400

        for child in children:
            post = child.get("data", {})

            if post.get("stickied", False):
                continue
            created = post.get("created_utc", 0)
            if created < cutoff:
                continue

            title = post.get("title", "").strip()
            if not title:
                continue

            title_lower = title.lower()
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)

            score = post.get("score", 0)
            flair = post.get("link_flair_text", "") or ""

            line = f"[Reddit/r/{subreddit}] {title}"
            if flair:
                line += f" [{flair}]"
            if score > 0:
                line += f" ({score}\u2191)"
            results.append(line)

        return results
