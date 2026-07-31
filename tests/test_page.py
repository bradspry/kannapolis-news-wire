import pytest
from kspider.page import Page

HTML = """
<html>
<head><title>Test Page</title></head>
<body>
  <h1>Hello</h1>
  <a href="/about">About</a>
  <a href="https://external.com/page">External</a>
  <a href="javascript:void(0)">JS link</a>
  <a href="mailto:hi@example.com">Email</a>
  <a href="/about#section">With fragment</a>
</body>
</html>
"""


@pytest.fixture
def page():
    return Page(url="https://example.com/", status_code=200, html=HTML)


def test_title(page):
    assert page.title == "Test Page"


def test_links_absolute(page):
    links = page.links()
    assert "https://example.com/about" in links
    assert "https://external.com/page" in links


def test_links_strips_fragments(page):
    links = page.links()
    # /about#section should become https://example.com/about (no fragment)
    assert all("#" not in url for url in links)


def test_links_skips_js_and_mailto(page):
    links = page.links()
    assert not any("javascript:" in url for url in links)
    assert not any("mailto:" in url for url in links)


def test_select(page):
    assert page.select("h1") == ["Hello"]


def test_text(page):
    assert "Hello" in page.text
