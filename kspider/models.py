from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SearchResult:
    query: str
    source: str          # 'web', 'images', 'news'
    title: str
    url: str
    snippet: Optional[str] = None
    thumbnail_url: Optional[str] = None
    source_domain: Optional[str] = None
    published_at: Optional[str] = None
    fetched_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    # set after DB insert
    id: Optional[int] = None
    search_run_id: Optional[int] = None
