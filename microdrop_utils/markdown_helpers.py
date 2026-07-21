"""Helpers for rendering markdown documents into standalone HTML pages."""

import re

import requests

GITHUB_BLOB_URL_PATTERN = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<path>.+)"
)
GITHUB_MARKDOWN_RENDER_API_URL = "https://api.github.com/markdown"
GITHUB_REQUEST_TIMEOUT_S = 10

MARKDOWN_PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<base href="{base_href}">
<style>
body {{
    font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    color: #1f2328; line-height: 1.5; max-width: 850px;
    margin: 0 auto; padding: 2rem;
}}
a {{ color: #0969da; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
h1, h2 {{ border-bottom: 1px solid #d1d9e0; padding-bottom: .3em; }}
code, pre {{ font-family: ui-monospace, Consolas, monospace; background: #f6f8fa; border-radius: 6px; }}
code {{ padding: .2em .4em; font-size: 85%; }}
pre {{ padding: 1em; overflow-x: auto; }}
pre code {{ padding: 0; }}
img {{ max-width: 100%; }}
blockquote {{ color: #59636e; border-left: .25em solid #d1d9e0; margin: 0; padding: 0 1em; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid #d1d9e0; padding: 6px 13px; }}
</style>
</head>
<body>
{rendered_markdown}
</body>
</html>
"""


def fetch_github_markdown_as_html(github_blob_url: str) -> str:
    """Fetch a markdown file from GitHub and return it rendered as a full HTML page.

    ``github_blob_url`` is a ``https://github.com/<owner>/<repo>/blob/<ref>/<path>``
    URL to a markdown file. The raw markdown is fetched and rendered to HTML via
    GitHub's markdown API (GFM dialect), then wrapped in a minimally styled page
    whose ``<base>`` tag points back at the blob directory so relative links
    resolve to github.com.

    Raises ``ValueError`` for a non-blob URL and ``requests`` errors on any
    network/HTTP failure — callers decide the fallback.
    """
    match = GITHUB_BLOB_URL_PATTERN.match(github_blob_url)
    if match is None:
        raise ValueError(f"Not a GitHub blob URL: {github_blob_url}")
    owner, repo, ref, path = match.group("owner", "repo", "ref", "path")

    raw_response = requests.get(
        f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}",
        timeout=GITHUB_REQUEST_TIMEOUT_S,
    )
    raw_response.raise_for_status()

    render_response = requests.post(
        GITHUB_MARKDOWN_RENDER_API_URL,
        json={"text": raw_response.text, "mode": "gfm", "context": f"{owner}/{repo}"},
        headers={"Accept": "application/vnd.github+json"},
        timeout=GITHUB_REQUEST_TIMEOUT_S,
    )
    render_response.raise_for_status()

    base_href = github_blob_url.rsplit("/", 1)[0] + "/"
    return MARKDOWN_PAGE_TEMPLATE.format(base_href=base_href,
                                         rendered_markdown=render_response.text)
