"""Helpers for working with markdown documents."""

import re

import requests

GITHUB_BLOB_URL_PATTERN = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<path>.+)"
)
GITHUB_MARKDOWN_RENDER_API_URL = "https://api.github.com/markdown"
GITHUB_REQUEST_TIMEOUT_S = 10

# Literal "<" in markdown, except when opening an autolink (<https://...>,
# <mailto:...>). Markdown renderers otherwise treat any other <token> as
# inline HTML: QTextDocument swallows the rest of the document and GitHub's
# markdown API strips the token (e.g. "PID_<HEATER>" in a changelog entry).
MARKDOWN_NON_AUTOLINK_ANGLE_BRACKET_PATTERN = re.compile(
    r"<(?!(?:https?|mailto):[^\s>]+>)")


def escape_tag_like_tokens(markdown_text: str) -> str:
    """Escape literal ``<`` (sparing autolinks) so tag-like tokens survive
    markdown rendering as text; intentional inline HTML is consequently not
    supported."""
    return MARKDOWN_NON_AUTOLINK_ANGLE_BRACKET_PATTERN.sub("&lt;", markdown_text)


MARKDOWN_PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
{base_tag}
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


def changelog_sections_added_since(previous_text: str, current_text: str) -> str:
    """Return the content newly prepended to a prepend-style changelog.

    Commitizen prepends each release's section to the top of CHANGELOG.md,
    leaving the earlier content byte-identical below it, so the delta is the
    prefix of ``current_text`` sitting above ``previous_text``. If the old
    text is no longer a literal suffix (changelog rewritten or reformatted),
    falls back to collecting top-level ``## `` sections from the top until
    one whose header line already appears in ``previous_text``. Returns
    ``""`` when nothing is new.
    """
    if current_text == previous_text:
        return ""
    if current_text.endswith(previous_text):
        return current_text[:len(current_text) - len(previous_text)]

    previous_section_headers = {
        line for line in previous_text.splitlines() if line.startswith("## ")
    }
    newly_added_lines = []
    for line in current_text.splitlines(keepends=True):
        if line.startswith("## ") and line.rstrip() in previous_section_headers:
            break
        newly_added_lines.append(line)
    return "".join(newly_added_lines)


def fetch_github_markdown(github_blob_url: str) -> str:
    """Fetch the raw markdown text behind a GitHub blob URL.

    ``github_blob_url`` is a ``https://github.com/<owner>/<repo>/blob/<ref>/<path>``
    URL to a markdown file. Raises ``ValueError`` for a non-blob URL and
    ``requests`` errors on any network/HTTP failure — callers decide the
    fallback.
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
    return raw_response.text


def render_markdown_as_html_page(markdown_text: str, base_href: str = None) -> str:
    """Render markdown to a styled standalone HTML page via GitHub's markdown API.

    GFM rendering wrapped in a minimal GitHub-ish stylesheet — noticeably
    nicer than QTextDocument's output. ``base_href`` (optional) becomes a
    ``<base>`` tag so relative links resolve. Raises ``requests`` errors on
    any network/HTTP failure — callers decide the fallback (typically the
    offline ``pyside_helpers.markdown_text_to_html``).
    """
    render_response = requests.post(
        GITHUB_MARKDOWN_RENDER_API_URL,
        json={"text": escape_tag_like_tokens(markdown_text), "mode": "gfm"},
        headers={"Accept": "application/vnd.github+json"},
        timeout=GITHUB_REQUEST_TIMEOUT_S,
    )
    render_response.raise_for_status()
    base_tag = f'<base href="{base_href}">' if base_href else ""
    return MARKDOWN_PAGE_TEMPLATE.format(base_tag=base_tag,
                                         rendered_markdown=render_response.text)
