from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class SearchResult:
    """跨平台统一的一条搜索结果（视频或图文）。"""

    platform: str          # bili | youtube | xhs | dy | zhihu | wb | twitter | manual
    item_type: str         # "video" | "text"
    title: str
    url: str
    author: str = ""
    publish_date: str = ""
    metrics: dict = field(default_factory=dict)  # plays/likes/comments/collects/shares/duration
    images: list = field(default_factory=list)   # 图文帖配图 URL 列表（小红书等）
    snippet: str = ""      # 简介/正文预览
    keyword: str = ""      # 命中关键词
    relevance: float = 0.0  # LLM 相关性得分 0-10
    reason: str = ""       # LLM 判定理由

    @property
    def uid(self) -> str:
        return f"{self.platform}|{self.url}"

    @property
    def engagement(self) -> int:
        """粗略互动量：赞*1 + 藏*2 + 评*3 + 播放/100，用于排序。"""

        def _i(x):
            try:
                return int(x)
            except (TypeError, ValueError):
                return 0

        m = self.metrics
        return (_i(m.get("likes")) + _i(m.get("collects")) * 2
                + _i(m.get("comments")) * 3 + _i(m.get("plays")) // 100)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SearchResult":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})
