from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from typing import Optional

from bs4 import BeautifulSoup


@dataclass
class Page:
    url: str
    status_code: int
    html: str
    depth: int = 0
    _soup: Optional[BeautifulSoup] = field(default=None, repr=False)

    @property
    def soup(self) -> BeautifulSoup:
        if self._soup is None:
            self._soup = BeautifulSoup(self.html, "lxml")
        return self._soup

    @property
    def title(self) -> Optional[str]:
        tag = self.soup.find("title")
        return tag.get_text(strip=True) if tag else None

    @property
    def text(self) -> str:
        return self.soup.get_text(separator=" ", strip=True)

    def links(self, base_url: Optional[str] = None) -> list[str]:
        base = base_url or self.url
        urls = []
        for tag in self.soup.find_all("a", href=True):
            href = tag["href"].strip()
            if href.startswith(("javascript:", "mailto:", "#")):
                continue
            absolute = urljoin(base, href)
            parsed = urlparse(absolute)
            # strip fragment
            urls.append(parsed._replace(fragment="").geturl())
        return urls

    def select(self, css: str) -> list[str]:
        return [el.get_text(strip=True) for el in self.soup.select(css)]
