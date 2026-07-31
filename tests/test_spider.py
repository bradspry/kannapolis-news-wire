import pytest
import respx
import httpx

from kspider.spider import Spider, SpiderConfig

BASE = "https://example.com"

INDEX_HTML = """
<html><head><title>Index</title></head>
<body>
  <a href="/page1">Page 1</a>
  <a href="/page2">Page 2</a>
  <a href="https://other.com/">External</a>
</body></html>
"""

PAGE1_HTML = "<html><head><title>Page 1</title></head><body>Content 1</body></html>"
PAGE2_HTML = "<html><head><title>Page 2</title></head><body>Content 2</body></html>"


@pytest.fixture
def mock_site():
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.get("/").respond(200, html=INDEX_HTML)
        mock.get("/page1").respond(200, html=PAGE1_HTML)
        mock.get("/page2").respond(200, html=PAGE2_HTML)
        yield mock


@pytest.mark.asyncio
async def test_crawl_same_domain(mock_site):
    config = SpiderConfig(max_depth=1, delay=0)
    spider = Spider(config)
    pages = await spider.crawl(f"{BASE}/")

    urls = [p.url for p in pages]
    assert f"{BASE}/" in urls
    assert f"{BASE}/page1" in urls
    assert f"{BASE}/page2" in urls


@pytest.mark.asyncio
async def test_no_external_by_default(mock_site):
    config = SpiderConfig(max_depth=1, delay=0, follow_external=False)
    spider = Spider(config)
    pages = await spider.crawl(f"{BASE}/")

    assert not any("other.com" in p.url for p in pages)


@pytest.mark.asyncio
async def test_max_pages(mock_site):
    config = SpiderConfig(max_depth=5, max_pages=2, delay=0)
    spider = Spider(config)
    pages = await spider.crawl(f"{BASE}/")

    assert len(pages) <= 2


@pytest.mark.asyncio
async def test_no_duplicate_visits(mock_site):
    config = SpiderConfig(max_depth=2, delay=0)
    spider = Spider(config)
    pages = await spider.crawl(f"{BASE}/")

    urls = [p.url for p in pages]
    assert len(urls) == len(set(urls))
