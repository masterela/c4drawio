"""Approximate text metrics (no font files needed) for Helvetica-like fonts."""

from __future__ import annotations

import re

_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<br\s*/?>|\n", re.I)


def plain(s: str) -> str:
    return _TAG.sub("", s or "").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def hard_lines(s: str) -> list[str]:
    if not s:
        return []
    return [plain(x) for x in _BR.split(s)]


def text_width(s: str, size: float, bold: bool = False) -> float:
    return len(plain(s)) * size * (0.60 if bold else 0.55)


def wrapped_lines(s: str, size: float, max_w: float, bold: bool = False) -> int:
    """Number of lines once word-wrapped at max_w."""
    n = 0
    for line in hard_lines(s):
        words, cur = line.split(), 0.0
        if not words:
            n += 1
            continue
        lines = 1
        space = size * 0.3
        for w in words:
            ww = text_width(w, size, bold)
            if cur and cur + space + ww > max_w:
                lines += 1
                cur = ww
            else:
                cur = cur + space + ww if cur else ww
        n += lines
    return n


def line_height(size: float) -> float:
    return size * 1.25


def to_html(s: str) -> str:
    """User text -> draw.io HTML label fragment (newlines become <br>)."""
    return (s or "").replace("\n", "<br>")
