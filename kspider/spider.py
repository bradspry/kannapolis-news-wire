from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urlparse
from typing import AsyncIterator, Callable, List, Optional

import httpx

from .page import Page


@dataclass
class SpiderConfig:
    max_depth: int = 2
    max_pages: int = 100
    delay: float = 0.5          # seconds between requests to the same host
    timeout: float = 10.0
    follow_external: bool = False
    user_agent: str = "kspider/0.1 (+https://github.com/kspider)"
    headers: dict[str, str] = field(default_factory=dict)


class Spider:
    def __init__(self, config: SpiderConfig | None = None):
        self.config = config or SpiderConfig()
        self._visited: set[str] = set()
        self._host_last_request: dict[str, float] = {}

    async def crawl(
        self,
        start_url: str,
        on_page: Optional[Callable[[Page], None]] = None,
    ) -> List[Page]:
        pages: List[Page] = []
        async for page in self._crawl_iter(start_url):
            pages.append(page)
            if on_page:
                on_page(page)
        return pages

    async def _crawl_iter(self, start_url: str) -> AsyncIterator[Page]:
        start_host = urlparse(start_url).netloc
        queue: deque[tuple[str, int]] = deque([(start_url, 0)])
        headers = {"User-Agent": self.config.user_agent, **self.config.headers}

        async with httpx.AsyncClient(
            headers=headers,
            timeout=self.config.timeout,
            follow_redirects=True,
        ) as client:
            while queue and len(self._visited) < self.config.max_pages:
                url, depth = queue.popleft()

                if url in self._visited:
                    continue
                self._visited.add(url)

                await self._polite_delay(url)

                try:
                    response = await client.get(url)
                except (httpx.RequestError, httpx.HTTPStatusError):
                    continue

                content_type = response.headers.get("content-type", "")
                if "html" not in content_type:
                    continue

                page = Page(
                    url=str(response.url),
                    status_code=response.status_code,
                    html=response.text,
                    depth=depth,
                )
                yield page

                if depth < self.config.max_depth:
                    for link in page.links():
                        if link in self._visited:
                            continue
                        link_host = urlparse(link).netloc
                        if not self.config.follow_external and link_host != start_host:
                            continue
                        queue.append((link, depth + 1))

    async def _polite_delay(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._host_last_request.get(host, 0.0)
        wait = self.config.delay - (time.monotonic() - last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._host_last_request[host] = time.monotonic()
