"""Helpers for working with markdown documents."""

import re

import requests

GITHUB_BLOB_URL_PATTERN = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<path>.+)"
)
GITHUB_REQUEST_TIMEOUT_S = 10


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
