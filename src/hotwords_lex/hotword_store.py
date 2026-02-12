"""hotwords.txt 读写 - 解析 / 去重 / 回写

文件格式：
    【AI】:[OpenAI,GPT-5.2,o1-pro,...]
    【编程】:[Cursor,Windsurf,...]
    ...
"""

from __future__ import annotations

import re
from pathlib import Path


# 标准分类列表（与 hotwords.txt 对齐）
CATEGORIES = [
    "AI", "编程", "职场", "数码", "汽车", "金融", "社交", "购物",
    "设计", "健康", "旅游", "文娱", "营销", "法律", "人力", "教育",
    "房产", "运动", "政务",
]

# 分类名别名映射（LLM 可能返回的变体 → 标准名）
CATEGORY_ALIASES = {
    # 标准分类自映射
    "ai": "AI",
    "编程": "编程",
    "职场": "职场",
    "数码": "数码",
    "汽车": "汽车",
    "金融": "金融",
    "社交": "社交",
    "购物": "购物",
    "设计": "设计",
    "健康": "健康",
    "旅游": "旅游",
    "文娱": "文娱",
    "营销": "营销",
    "法律": "法律",
    "人力": "人力",
    "教育": "教育",
    "房产": "房产",
    "运动": "运动",
    "政务": "政务",
    # AI 相关别名
    "人工智能": "AI",
    "机器学习": "AI",
    "深度学习": "AI",
    "大模型": "AI",
    "nlp": "AI",
    "自然语言处理": "AI",
    "计算机视觉": "AI",
    "科学": "AI",
    "物理": "AI",
    "数学": "AI",
    "天文": "AI",
    # 编程相关别名
    "前端": "编程",
    "后端": "编程",
    "devops": "编程",
    "数据库": "编程",
    "语言": "编程",
    "工具": "编程",
    "安全": "编程",
    "开发": "编程",
    "技术": "编程",
    "开源": "编程",
    "web": "编程",
    "programming": "编程",
    "software": "编程",
    "infrastructure": "编程",
    "cloud": "编程",
    # 数码/硬件
    "硬件": "数码",
    "电子": "数码",
    "芯片": "数码",
    "手机": "数码",
    "消费电子": "数码",
    "科技": "数码",
    # 金融
    "区块链": "金融",
    "加密货币": "金融",
    "crypto": "金融",
    "经济": "金融",
    "投资": "金融",
    # 文娱
    "娱乐": "文娱",
    "影视": "文娱",
    "游戏": "文娱",
    "音乐": "文娱",
    "动漫": "文娱",
    "综艺": "文娱",
    # 社交
    "社会": "社交",
    "时事": "社交",
    "新闻": "社交",
    "热点": "社交",
    "网络": "社交",
    # 其他映射
    "军事": "政务",
    "政治": "政务",
    "国际": "政务",
    "历史": "文娱",
    "文化": "文娱",
    "美食": "旅游",
    "自然": "旅游",
    "环保": "政务",
    "能源": "政务",
    "航空": "数码",
    "航天": "数码",
    "医疗": "健康",
    "养生": "健康",
    "体育": "运动",
    "媒体": "营销",
    # 默认
    "其他": "AI",
}

# 解析一行的正则: 【分类名】:[词1,词2,...]
_LINE_PATTERN = re.compile(r"^【(.+?)】:\[(.+)]$")


class HotwordStore:
    """hotwords.txt 的读写管理器"""

    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)
        # 按分类存储词条，保持顺序
        self.categories: dict[str, list[str]] = {}
        # 所有词条：小写 → (原始写法, 所属分类)
        self._all_terms_info: dict[str, tuple[str, str]] = {}
        # 原始行顺序
        self._category_order: list[str] = []

    def load(self) -> None:
        """读取 hotwords.txt"""
        if not self.filepath.exists():
            print(f"[词库] {self.filepath} 不存在，将创建新文件")
            # 初始化空分类
            for cat in CATEGORIES:
                self.categories[cat] = []
                self._category_order.append(cat)
            return

        text = self.filepath.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = _LINE_PATTERN.match(line)
            if match:
                cat_name = match.group(1)
                words_str = match.group(2)
                words = [w.strip() for w in words_str.split(",") if w.strip()]
                self.categories[cat_name] = words
                self._category_order.append(cat_name)
                for w in words:
                    self._all_terms_info[w.lower()] = (w, cat_name)

        total = sum(len(ws) for ws in self.categories.values())
        print(f"[词库] 已加载 {len(self.categories)} 个分类，{total} 个词条")

    def contains(self, word: str) -> bool:
        """检查某个词是否已存在（忽略大小写）"""
        return word.lower() in self._all_terms_info

    def get_term_info(self, word: str) -> tuple[str, str] | None:
        """查询词的原始写法和所属分类

        Returns:
            (原始写法, 分类名) 或 None
        """
        return self._all_terms_info.get(word.lower())

    def add_words(self, new_words: list[dict]) -> int:
        """添加新词到对应分类

        Args:
            new_words: [{"term": "xxx", "category": "AI"}, ...]

        Returns:
            实际新增的词数
        """
        added = 0
        for item in new_words:
            term = item.get("term", "").strip()
            if not term:
                continue

            # 去重
            if self.contains(term):
                continue

            # 映射分类
            raw_cat = item.get("category", "其他")
            cat = self._resolve_category(raw_cat)

            # 确保分类存在
            if cat not in self.categories:
                self.categories[cat] = []
                self._category_order.append(cat)

            self.categories[cat].append(term)
            self._all_terms_info[term.lower()] = (term, cat)
            added += 1

        return added

    def save(self) -> None:
        """回写 hotwords.txt（空分类不输出）"""
        lines = []
        for cat in self._category_order:
            words = self.categories.get(cat, [])
            if not words:
                continue
            line = f"【{cat}】:[{','.join(words)}]"
            lines.append(line)

        # 写入（末尾不加多余换行）
        self.filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
        total = sum(len(ws) for ws in self.categories.values())
        print(f"[词库] 已保存 {len(self.categories)} 个分类，{total} 个词条 → {self.filepath}")

    def get_all_words(self) -> set[str]:
        """返回所有词条的小写集合"""
        return set(self._all_terms_info.keys())

    def get_all_terms_with_info(self) -> dict[str, tuple[str, str]]:
        """返回所有词条的映射：小写 → (原始写法, 分类名)"""
        return dict(self._all_terms_info)

    @staticmethod
    def _resolve_category(raw: str) -> str:
        """将 LLM 返回的分类名映射到标准分类"""
        key = raw.lower().strip()
        return CATEGORY_ALIASES.get(key, "AI")
