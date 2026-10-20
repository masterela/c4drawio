"""Automatic layout: measure natural sizes bottom-up, then place children top-down.

Containers lay their children out in a `row`, a `column` or a `grid`. Child containers stretch on the cross
axis (so lanes in a column share one width); `justify` spreads children along the main axis.
Children with an explicit `pos` keep it (used for round-trips from draw.io).
"""

from __future__ import annotations

import math

from .model import C4_KINDS, Node, Page, Relationship, base_kind
from .text import hard_lines, line_height, text_width, wrapped_lines
from .theme import Theme


def _sp(theme: Theme, key: str, default: float) -> float:
    return float(theme.spacing.get(key, default))


def title_metrics(n: Node, theme: Theme) -> tuple[float, float, str]:
    """(top offset, bottom offset, title position) of a container's inner area."""
    st = theme.boundary(n.kind)
    pad = float(n.padding if n.padding is not None else _sp(theme, "padding", 24))
    if n.kind == "page":
        return 0.0, 0.0, "none"
    pos = "top" if st.get("aws_group") else st.get("title_position", "top")
    band = _sp(theme, "title_band", 28) if n.name else 0.0
    if pos == "bottom":
        return pad, pad / 2 + band if band else pad, "bottom"
    return (band + pad / 2) if band else pad, pad, "top"


def title_width(n: Node, theme: Theme) -> float:
    if not n.name:
        return 0.0
    st = theme.boundary(n.kind)
    w = text_width(n.name, float(st.get("font_size", 12)), bool(st.get("bold", True)))
    if n.technology:
        w = max(w, text_width(f"[{n.technology}]", float(st.get("font_size", 12)) - 1))
    return w + (40 if st.get("aws_group") else 20)


# --------------------------------------------------------------------------- leaves
def icon_label_lines(n: Node) -> list[str]:
    return hard_lines(n.technology) + hard_lines(n.name) + hard_lines(n.description)


def leaf_size(n: Node, theme: Theme) -> tuple[float, float]:
    st = theme.element(n.kind)
    fs = float(st.get("font_size", 11))
    if n.kind == "icon":
        s = float(n.size[0]) if n.size else float(st.get("size", 48))
        n.icon_size = s
        lines = icon_label_lines(n)
        lw = max([text_width(x, fs, True) for x in lines] + [0.0])
        n.label_h = len(lines) * line_height(fs) + (6 if lines else 0)
        return max(s, lw + 6), s + n.label_h
    dw, dh = st.get("size", [200, 100])
    if n.size:
        return float(n.size[0]), float(n.size[1])
    w = float(dw)
    bk = base_kind(n.kind)
    inner = w - (60 if bk == "person" else 40 if bk in ("database", "queue") else 20)
    ns = float(st.get("name_size", 13))
    if n.kind in ("text", "raw"):
        h = wrapped_lines(n.name or n.description, fs, inner) * line_height(fs) + 12
    elif n.kind == "note":
        h = (wrapped_lines(n.name, fs, inner, True) + wrapped_lines(n.description, fs, inner)) * line_height(fs) + 20
    else:
        h = wrapped_lines(n.name, ns, inner, True) * line_height(ns)
        if base_kind(n.kind) in C4_KINDS:
            h += line_height(fs)  # [Type: technology]
        if n.description:
            h += line_height(fs) * 0.6 + wrapped_lines(n.description, fs, inner) * line_height(fs)
        if base_kind(n.kind) == "person":
            h += float(dh) * 0.38  # head of the person shape
        elif base_kind(n.kind) in ("database", "queue"):
            h += 24
        h += 24
    return w, max(float(dh), h)


# --------------------------------------------------------------------------- relationship labels
def wrap_words(text: str, size: float, max_w: float) -> list[str]:
    out = []
    for line in hard_lines(text):
        cur = ""
        for w in line.split():
            cand = f"{cur} {w}".strip()
            if cur and text_width(cand, size) > max_w:
                out.append(cur)
                cur = w
            else:
                cur = cand
        out.append(cur)
    return out


def edge_label_parts(rel: Relationship, theme: Theme) -> tuple[list[str], list[str], float]:
    """Wrapped description lines, wrapped [technology] lines, font size."""
    st = theme.relationship(rel.style)
    fs = float(st.get("font_size", 10))
    max_w = float(theme.routing.get("label_max_width", 160))
    desc = wrap_words(rel.label, fs, max_w) if rel.label else []
    tech = wrap_words(f"[{rel.technology}]", fs - 1, max_w) if rel.technology else []
    return desc, tech, fs


def edge_label_size(rel: Relationship, theme: Theme) -> tuple[float, float]:
    desc, tech, fs = edge_label_parts(rel, theme)
    lines = desc + tech
    if not lines:
        return 0.0, 0.0
    return max(text_width(x, fs) for x in lines) + 10, len(lines) * line_height(fs) + 6


def _branch(n: Node, lca: Node) -> Node:
    while n.parent is not lca:
        n = n.parent
    return n


def label_gaps(page: Page, theme: Theme) -> dict:
    """Minimum gaps so that a relationship label fits between two neighbouring siblings.

    Keys: (container id, index of the first child) for row/column, (container id, "col"|"row") for grids.
    """
    clear = 2 * _sp(theme, "route_margin", 12) + 16
    nodes = page.nodes()
    need: dict = {}
    for rel in page.relationships:
        lw, lh = edge_label_size(rel, theme)
        if not lw:
            continue
        a, b = nodes[rel.source], nodes[rel.target]
        anc_a = [a] + list(a.ancestors()) + [page.root]
        anc_b = {id(x) for x in [b] + list(b.ancestors()) + [page.root]}
        lca = next((x for x in anc_a if id(x) in anc_b), page.root)
        if lca is a or lca is b:
            continue
        ca, cb = _branch(a, lca), _branch(b, lca)
        flow = [c for c in lca.children if c.pos is None]
        if ca not in flow or cb not in flow:
            continue
        ia, ib = flow.index(ca), flow.index(cb)
        if lca.layout == "grid":
            cols = lca.columns or max(1, math.ceil(math.sqrt(len(flow))))
            if ia // cols == ib // cols and abs(ia - ib) == 1:
                need[(lca.id, "col")] = max(need.get((lca.id, "col"), 0), lw + clear)
            elif ia % cols == ib % cols and abs(ia - ib) == cols:
                need[(lca.id, "row")] = max(need.get((lca.id, "row"), 0), lh + clear)
        elif abs(ia - ib) == 1:
            g = lw + clear if lca.layout == "row" else lh + clear
            key = (lca.id, min(ia, ib))
            need[key] = max(need.get(key, 0), g)
    return need


# --------------------------------------------------------------------------- measure
_NEED: dict = {}


def _gap(n: Node, theme: Theme) -> float:
    return float(n.gap if n.gap is not None else _sp(theme, "gap", 40))


def _gaps(n: Node, theme: Theme, count: int) -> list[float]:
    """Gap after each of the first count-1 flow children."""
    base = _gap(n, theme)
    return [max(base, _NEED.get((n.id, i), 0.0)) for i in range(max(count - 1, 0))]


def _grid_gaps(n: Node, theme: Theme) -> tuple[float, float]:
    base = _gap(n, theme)
    return max(base, _NEED.get((n.id, "col"), 0.0)), max(base, _NEED.get((n.id, "row"), 0.0))


def _pad(n: Node, theme: Theme) -> float:
    if n.kind == "page":
        return 0.0
    return float(n.padding if n.padding is not None else _sp(theme, "padding", 24))


def _grid_dims(n: Node, count: int) -> tuple[int, int]:
    cols = n.columns or max(1, math.ceil(math.sqrt(count)))
    return cols, math.ceil(count / cols) if count else 0


def measure(n: Node, theme: Theme) -> None:
    if not n.is_boundary:
        n.nat_w, n.nat_h = leaf_size(n, theme)
        return
    for c in n.children:
        measure(c, theme)
    flow = [c for c in n.children if c.pos is None]
    gap = _gap(n, theme)
    if not flow:
        cw = ch = 0.0
    elif n.layout == "row":
        cw = sum(c.nat_w for c in flow) + sum(_gaps(n, theme, len(flow)))
        ch = max(c.nat_h for c in flow)
    elif n.layout == "column":
        cw = max(c.nat_w for c in flow)
        ch = sum(c.nat_h for c in flow) + sum(_gaps(n, theme, len(flow)))
    else:
        cols, rows = _grid_dims(n, len(flow))
        gx, gy = _grid_gaps(n, theme)
        colw = [max((flow[i].nat_w for i in range(k, len(flow), cols)), default=0) for k in range(cols)]
        rowh = [max(c.nat_h for c in flow[r * cols:(r + 1) * cols]) for r in range(rows)]
        cw, ch = sum(colw) + gx * (cols - 1), sum(rowh) + gy * (rows - 1)
    top, bottom, _ = title_metrics(n, theme)
    pad = _pad(n, theme)
    w = cw + 2 * pad
    h = top + ch + bottom
    for c in n.children:
        if c.pos is not None:
            ox = c.pos[0] - (c.nat_w - c.icon_size) / 2 if c.kind == "icon" else c.pos[0]
            w = max(w, ox + c.nat_w + pad)
            h = max(h, c.pos[1] + c.nat_h + bottom)
    w = max(w, title_width(n, theme) + 2 * pad)
    if n.size:
        w, h = max(w, n.size[0]), max(h, n.size[1])
    n.nat_w, n.nat_h = w, h


# --------------------------------------------------------------------------- place
def _offsets(extra: float, count: int, justify: str) -> tuple[float, float]:
    """(start offset, additional gap) for the main axis."""
    if count == 0 or extra <= 0:
        return 0.0, 0.0
    if justify == "center":
        return extra / 2, 0.0
    if justify == "end":
        return extra, 0.0
    if justify == "space-between":
        return (0.0, extra / (count - 1)) if count > 1 else (extra / 2, 0.0)
    if justify == "space-around":
        return extra / count / 2, extra / count
    return 0.0, 0.0


def _cross(align: str, avail: float, size: float) -> float:
    if align == "center":
        return (avail - size) / 2
    if align == "end":
        return avail - size
    return 0.0


def place(n: Node, w: float, h: float, theme: Theme) -> None:
    n.w, n.h = w, h
    if not n.is_boundary:
        return
    top, bottom, _ = title_metrics(n, theme)
    pad = _pad(n, theme)
    iw, ih = w - 2 * pad, h - top - bottom
    gap = _gap(n, theme)
    flow = [c for c in n.children if c.pos is None]

    def put(c: Node, x: float, y: float, cw: float, ch: float) -> None:
        c.x, c.y = x, y
        place(c, cw, ch, theme)

    if n.layout == "row" and flow:
        gaps = _gaps(n, theme, len(flow)) + [0.0]
        total = sum(c.nat_w for c in flow) + sum(gaps)
        x, extra_gap = _offsets(iw - total, len(flow), n.justify)
        x += pad
        for c, g in zip(flow, gaps):
            ch = ih if (c.is_boundary and n.stretch) else c.nat_h
            put(c, x, top + _cross(n.align, ih, ch), c.nat_w, ch)
            x += c.nat_w + g + extra_gap
    elif n.layout == "column" and flow:
        gaps = _gaps(n, theme, len(flow)) + [0.0]
        total = sum(c.nat_h for c in flow) + sum(gaps)
        y, extra_gap = _offsets(ih - total, len(flow), n.justify)
        y += top
        for c, g in zip(flow, gaps):
            cw = iw if (c.is_boundary and n.stretch) else c.nat_w
            put(c, pad + _cross(n.align, iw, cw), y, cw, c.nat_h)
            y += c.nat_h + g + extra_gap
    elif flow:
        cols, rows = _grid_dims(n, len(flow))
        gap, gy = _grid_gaps(n, theme)
        colw = [max((flow[i].nat_w for i in range(k, len(flow), cols)), default=0) for k in range(cols)]
        rowh = [max(c.nat_h for c in flow[r * cols:(r + 1) * cols]) for r in range(rows)]
        sx, egx = _offsets(iw - sum(colw) - gap * (cols - 1), cols, n.justify)
        y = top
        for r in range(rows):
            x = pad + sx
            for k in range(cols):
                i = r * cols + k
                if i >= len(flow):
                    break
                c = flow[i]
                cw = colw[k] if (c.is_boundary and n.stretch) else c.nat_w
                ch = rowh[r] if (c.is_boundary and n.stretch) else c.nat_h
                put(c, x + _cross(n.align, colw[k], cw), y + _cross(n.align, rowh[r], ch), cw, ch)
                x += colw[k] + gap + egx
            y += rowh[r] + gy
    for c in n.children:
        if c.pos is not None:
            ox = c.pos[0] - (c.nat_w - c.icon_size) / 2 if c.kind == "icon" else c.pos[0]
            put(c, ox, c.pos[1], c.nat_w, c.nat_h)


def _absolute(n: Node, ax: float, ay: float) -> None:
    n.ax, n.ay = ax + n.x, ay + n.y
    for c in n.children:
        _absolute(c, n.ax, n.ay)


def page_header_height(page: Page, theme: Theme) -> float:
    t = theme.title
    if t.get("position", "top-left") == "none" or not (page.title or page.subtitle):
        return 0.0
    h = 0.0
    if page.title:
        h += line_height(float(t.get("size", 20))) + 6
    if page.subtitle:
        h += len(hard_lines(page.subtitle)) * line_height(float(t.get("subtitle_size", 12))) + 4
    return h + 16


def layout_page(page: Page, theme: Theme) -> tuple[float, float]:
    """Lay out a page in place; returns (width, height) of the drawing."""
    root = page.root
    margin = _sp(theme, "page_margin", 20)
    ox, oy = margin, margin + page_header_height(page, theme)
    # top-level `pos` values are absolute page coordinates: make them relative to the drawing origin
    saved = [(c, c.pos) for c in root.children if c.pos is not None]
    for c, p in saved:
        c.pos = (p[0] - ox, p[1] - oy)
    _NEED.clear()
    _NEED.update(label_gaps(page, theme))
    try:
        measure(root, theme)
        place(root, root.nat_w, root.nat_h, theme)
    finally:
        for c, p in saved:
            c.pos = p
    root.x, root.y = ox, oy
    _absolute(root, 0.0, 0.0)
    return root.x + root.w + margin, root.y + root.h + margin
