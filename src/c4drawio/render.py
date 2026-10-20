"""Render a Document to draw.io XML (one diagram page per Page)."""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

from .icons import GLYPHS, icon_color
from .layout import edge_label_parts, edge_label_size, layout_page, title_metrics, title_width
from .model import C4_KINDS, C4_TYPE, Document, Node, Page, Relationship, base_kind, load_yaml
from .router import End, EdgeReq, Rect, Route, Router
from .text import hard_lines, line_height, text_width, to_html
from .theme import Theme


def _a(v) -> str:
    return escape(str(v), {'"': "&quot;", "\n": "&#10;"})


def _n(v: float) -> str:
    v = round(float(v), 1)
    return str(int(v)) if v.is_integer() else str(v)


def _fill(v) -> str:
    return "none" if v in (None, "none", "") else str(v)


class _Out:
    def __init__(self) -> None:
        self.cells: list[str] = []

    def vertex(self, cid: str, label: str, style: str, parent: str, x, y, w, h, attrs: dict | None = None,
               visible: bool = True) -> None:
        geo = f'<mxGeometry x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" as="geometry"/>'
        vis = "" if visible else ' visible="0"'
        if attrs is not None:
            extra = "".join(f' {k}="{_a(v)}"' for k, v in attrs.items() if v not in (None, ""))
            self.cells.append(f'<object id="{_a(cid)}" label="{_a(label)}" placeholders="1"{extra}>'
                              f'<mxCell style="{_a(style)}" vertex="1" parent="{_a(parent)}"{vis}>{geo}</mxCell></object>')
        else:
            self.cells.append(f'<mxCell id="{_a(cid)}" value="{_a(label)}" style="{_a(style)}" vertex="1" '
                              f'parent="{_a(parent)}"{vis}>{geo}</mxCell>')

    def edge(self, cid: str, label: str, style: str, src: str, tgt: str, points, label_x: float | None,
             attrs: dict) -> None:
        pts = ""
        if points:
            pts = '<Array as="points">' + "".join(f'<mxPoint x="{_n(x)}" y="{_n(y)}"/>' for x, y in points) + "</Array>"
        lx = f' x="{_n(label_x)}"' if label_x is not None else ""
        extra = "".join(f' {k}="{_a(v)}"' for k, v in attrs.items() if v not in (None, ""))
        self.cells.append(f'<object id="{_a(cid)}" label="{_a(label)}" placeholders="1"{extra}>'
                          f'<mxCell style="{_a(style)}" edge="1" parent="1" source="{_a(src)}" target="{_a(tgt)}">'
                          f'<mxGeometry{lx} relative="1" as="geometry">{pts}</mxGeometry></mxCell></object>')


# --------------------------------------------------------------------------- element styles
def _leaf_style(n: Node, theme: Theme) -> tuple[str, str]:
    st = theme.element(n.kind)
    fs = float(st.get("font_size", 11))
    ns = float(st.get("name_size", 13))
    fill = _fill(theme.color(n.color) or st.get("fill"))
    stroke = _fill(st.get("stroke"))
    fc = theme.color(n.font_color) or st.get("font_color", "#000000")
    family = theme.font.get("family", "Helvetica")
    common = (f"html=1;whiteSpace=wrap;fontFamily={family};fontSize={_n(fs)};fontColor={fc};fillColor={fill};"
              f"strokeColor={stroke};metaEdit=1;")
    if st.get("shadow"):
        common += "shadow=1;"
    bk = base_kind(n.kind)
    if n.kind == "icon":
        icon = n.icon or "generic_application"
        color = theme.color(n.color) or icon_color(icon)
        base = (f"sketch=0;outlineConnect=0;gradientColor=none;html=1;fontFamily={family};fontSize={_n(fs)};"
                f"fontColor={fc};verticalLabelPosition=bottom;verticalAlign=top;align=center;aspect=fixed;"
                f"pointerEvents=1;dashed=0;metaEdit=1;")
        if "." in icon:
            style = base + f"shape={icon};fillColor={color};strokeColor=none;"
        elif icon in GLYPHS:
            style = base + f"shape=mxgraph.aws4.{icon};fillColor={theme.color(n.color) or '#232F3E'};strokeColor=none;"
        else:
            style = base + f"shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{icon};fillColor={color};strokeColor=#FFFFFF;"
        parts = (["%c4Technology%"] if n.technology else []) + ["<b>%c4Name%</b>"] + (
            ["%c4Description%"] if n.description else [])
        return style, "<br>".join(parts)
    if n.kind == "text":
        return (f"text;html=1;whiteSpace=wrap;fontFamily={family};fontSize={_n(fs)};fontColor={fc};align=left;"
                f"verticalAlign=top;metaEdit=1;"), "%c4Name%"
    if n.kind == "note":
        label = "<b>%c4Name%</b>" + ("<br>%c4Description%" if n.description else "")
        return (common + f"rounded=1;arcSize={_n(st.get('rounded', 6))};absoluteArcSize=1;align=left;"
                         f"verticalAlign=top;spacing=10;"), label
    if n.kind == "raw":
        return n.style or common, n.name
    # C4 boxes
    label = f'<font style="font-size:{_n(ns)}px"><b>%c4Name%</b></font>'
    if bk in C4_KINDS:
        label += "<div>[%c4Type%: %c4Technology%]</div>" if n.technology else "<div>[%c4Type%]</div>"
    if n.description:
        label += '<div style="margin-top:6px">%c4Description%</div>'
    if bk == "person":
        shape = "shape=mxgraph.c4.person2;align=center;verticalAlign=top;spacingTop=6;"
    elif bk == "database":
        shape = "shape=cylinder3;size=12;boundedLbl=1;align=center;verticalAlign=middle;"
    elif bk == "queue":
        shape = "shape=mxgraph.flowchart.direct_data;align=center;verticalAlign=middle;spacingLeft=12;spacingRight=24;"
    else:
        shape = (f"rounded=1;arcSize={_n(st.get('rounded', 8))};absoluteArcSize=1;align=center;"
                 f"verticalAlign=middle;spacing=8;")
    return common + shape, label


def _boundary_style(n: Node, theme: Theme) -> tuple[str, str]:
    st = theme.boundary(n.kind)
    fs = float(st.get("font_size", 12))
    fill = _fill(theme.color(n.color) or st.get("fill"))
    stroke = _fill(st.get("stroke"))
    fc = theme.color(n.font_color) or st.get("font_color", "#333333")
    dashed = 1 if st.get("dashed") else 0
    bold = "fontStyle=1;" if st.get("bold", True) else ""
    family = theme.font.get("family", "Helvetica")
    _, _, tpos = title_metrics(n, theme)
    common = (f"html=1;whiteSpace=wrap;container=1;collapsible=0;recursiveResize=0;pointerEvents=0;"
              f"fontFamily={family};fontSize={_n(fs)};fontColor={fc};{bold}strokeColor={stroke};fillColor={fill};"
              f"dashed={dashed};dashPattern={st.get('dash_pattern', '8 4')};metaEdit=1;")
    if st.get("aws_group"):
        style = (common + f"shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.{st['aws_group']};points=[];outlineConnect=0;"
                          f"gradientColor=none;verticalAlign=top;align=left;spacingLeft=30;")
    else:
        r = float(st.get("rounded", 0) or 0)
        style = (common + f"rounded={1 if r else 0};arcSize={_n(r)};absoluteArcSize=1;align=left;"
                          f"verticalAlign={'bottom' if tpos == 'bottom' else 'top'};spacingLeft=10;spacingTop=2;"
                          f"spacingBottom=2;")
    label = "%c4Name%" + ('<br><font style="font-size:{}px;font-weight:normal">[%c4Technology%]</font>'.format(
        _n(fs - 1)) if n.technology else "")
    return style, label


def _c4type(n: Node) -> str:
    t = C4_TYPE.get(base_kind(n.kind), "")
    return ("External " + t) if (t and n.kind.endswith("_ext")) else t


def _node_attrs(n: Node) -> dict:
    d = {
        "c4Kind": n.kind, "c4Name": to_html(n.name), "c4Type": _c4type(n), "c4Technology": to_html(n.technology),
        "c4Description": to_html(n.description), "c4Icon": n.icon, "c4Color": n.color, "c4FontColor": n.font_color,
        "c4Badge": n.badge, "c4Style": n.style if n.kind != "raw" else None,
    }
    if n.kind == "icon" and n.size:
        d["c4IconSize"] = _n(n.size[0])
    if n.is_boundary:
        for key, default in (("layout", "row"), ("columns", 0), ("gap", None), ("padding", None), ("align", "start"),
                             ("justify", "start"), ("stretch", True)):
            v = getattr(n, key)
            if v != default:
                d["c4" + key.capitalize()] = json.dumps(v) if not isinstance(v, str) else v
    return d


# --------------------------------------------------------------------------- page
def _obstacles(page: Page, theme: Theme) -> tuple[dict, list[Rect], list[Rect]]:
    obstacles: dict[str, list[Rect]] = {}
    borders: list[Rect] = []
    extras: list[Rect] = []
    band = float(theme.spacing.get("title_band", 28))
    for n in page.root.walk():
        if n.kind == "page":
            continue
        if n.is_boundary:
            borders.append(Rect(n.ax, n.ay, n.w, n.h))
            if n.name:
                _, _, tpos = title_metrics(n, theme)
                tw = min(title_width(n, theme), n.w)
                ty = n.ay if tpos == "top" else n.ay + n.h - band
                extras.append(Rect(n.ax, ty, tw, band))
            continue
        x, y, w, h = n.shape_rect()
        rects = [Rect(x, y, w, h)]
        if n.kind == "icon" and n.label_h:
            rects.append(Rect(n.ax, n.ay + n.icon_size, n.w, n.label_h))
        if n.badge:
            rects.append(Rect(x + w - 10, y - 8, 32, 14))
        obstacles[n.id] = rects
    return obstacles, borders, extras


def _edge_label(rel: Relationship, theme: Theme) -> tuple[str, float, float]:
    """Wrapped label as literal HTML (the unwrapped text stays in c4Description / c4Technology)."""
    desc, tech, fs = edge_label_parts(rel, theme)
    if not desc and not tech:
        return "", 0.0, 0.0
    label = "<br>".join(escape(x) for x in desc)
    if tech:
        label += ("<br>" if desc else "") + f'<font style="font-size:{_n(fs - 1)}px">' + \
            "<br>".join(escape(x) for x in tech) + "</font>"
    w, h = edge_label_size(rel, theme)
    return label, w, h


def _edge_style(rel: Relationship, route: Route, theme: Theme) -> str:
    st = theme.relationship(rel.style)
    color = theme.color(rel.color) or st.get("color", "#707070")
    rt = theme.routing
    s = (f"edgeStyle=orthogonalEdgeStyle;rounded={1 if rt.get('rounded', True) else 0};orthogonalLoop=1;"
         f"jettySize=auto;html=1;fontFamily={theme.font.get('family', 'Helvetica')};strokeColor={color};"
         f"strokeWidth={_n(st.get('width', 1.5))};fontSize={_n(st.get('font_size', 10))};"
         f"fontColor={st.get('font_color', '#333333')};labelBackgroundColor=#FFFFFF;")
    end = st.get("end_arrow", "block")
    start = "block" if rel.bidirectional and st.get("start_arrow", "none") == "none" else st.get("start_arrow", "none")
    s += f"endArrow={end};endFill={0 if end in ('open', 'none') else 1};"
    s += f"startArrow={start};startFill={0 if start in ('open', 'none') else 1};"
    if st.get("dashed"):
        s += f"dashed=1;dashPattern={st.get('dash_pattern', '6 4')};"
    if rt.get("jump"):
        s += "jumpStyle=arc;jumpSize=8;"

    def anchor(side: str, f: float, dy: float, pre: str) -> str:
        x, y = {"top": (f, 0), "bottom": (f, 1), "left": (0, f), "right": (1, f)}[side]
        return (f"{pre}X={round(x, 4):g};{pre}Y={round(y, 4):g};{pre}Dx=0;{pre}Dy={_n(dy)};"
                f"{pre}Perimeter=0;")

    s += anchor(route.src_side, route.src_frac, route.src_dy, "exit")
    s += anchor(route.tgt_side, route.tgt_frac, route.tgt_dy, "entry")
    return s


def render_page(page: Page, theme: Theme, out: _Out, theme_name: str, overrides: dict,
                warnings: list[str] | None = None) -> tuple[float, float]:
    width, height = layout_page(page, theme)
    nodes = page.nodes()
    meta = {"c4Kind": "meta", "c4Theme": theme_name}
    if overrides:
        meta["c4ThemeOverrides"] = json.dumps(overrides)
    out.vertex("__meta__", "", "text;html=1;", "1", 0, 0, 10, 10, meta, visible=False)
    # titles
    t = theme.title
    if t.get("position", "top-left") != "none":
        margin = float(theme.spacing.get("page_margin", 20))
        align = "center" if t.get("position") == "top-center" else "left"
        y = margin
        family = theme.font.get("family", "Helvetica")
        if page.title:
            size = float(t.get("size", 20))
            out.vertex("__title__", to_html(page.title),
                       f"text;html=1;align={align};verticalAlign=top;fontFamily={family};fontSize={_n(size)};"
                       f"fontStyle=1;fontColor={t.get('color', '#232F3E')};whiteSpace=wrap;",
                       "1", margin, y, width - 2 * margin, line_height(size) + 4, {"c4Kind": "title"})
            y += line_height(size) + 6
        if page.subtitle:
            size = float(t.get("subtitle_size", 12))
            h = len(hard_lines(page.subtitle)) * line_height(size) + 4
            out.vertex("__subtitle__", to_html(page.subtitle),
                       f"text;html=1;align={align};verticalAlign=top;fontFamily={family};fontSize={_n(size)};"
                       f"fontColor={t.get('subtitle_color', '#5A6C86')};whiteSpace=wrap;",
                       "1", margin, y, width - 2 * margin, h, {"c4Kind": "subtitle"})
    # shapes (containers before their children)
    for n in page.root.walk():
        if n.kind == "page":
            continue
        top = n.parent is None or n.parent.kind == "page"
        parent = "1" if top else n.parent.id
        ox, oy = (page.root.ax, page.root.ay) if top else (0.0, 0.0)
        if n.is_boundary:
            style, label = _boundary_style(n, theme)
            out.vertex(n.id, label, style + (n.style or ""), parent, ox + n.x, oy + n.y, n.w, n.h, _node_attrs(n))
            continue
        style, label = _leaf_style(n, theme)
        if n.kind != "raw":
            style += n.style or ""
        if n.kind == "icon":
            s = n.icon_size
            x, y, w, h = ox + n.x + (n.w - s) / 2, oy + n.y, s, s
        else:
            x, y, w, h = ox + n.x, oy + n.y, n.w, n.h
        out.vertex(n.id, label, style, parent, x, y, w, h, _node_attrs(n))
        if n.badge:
            b = theme.badge(n.badge)
            bw = max(30.0, text_width(n.badge, 8, True) + 10)
            out.vertex(f"{n.id}__badge", str(n.badge),
                       f"rounded=1;arcSize=40;html=1;fillColor={b.get('fill', '#5A6C86')};strokeColor=none;"
                       f"fontColor={b.get('font_color', '#FFFFFF')};fontSize=8;fontStyle=1;align=center;"
                       f"verticalAlign=middle;", parent, x + w - bw + 12, y - 7, bw, 14,
                       {"c4Kind": "badge", "c4For": n.id})
    # relationships
    obstacles, borders, extras = _obstacles(page, theme)
    sp, rt = theme.spacing, theme.routing
    router = Router(obstacles, borders, extras, margin=float(sp.get("route_margin", 12)),
                    bend=float(rt.get("bend_penalty", 40)), crossing=float(rt.get("crossing_penalty", 70)),
                    overlap=float(rt.get("overlap_penalty", 45)))
    reqs, labels = [], {}
    for rel in page.relationships:
        label, lw, lh = _edge_label(rel, theme)
        labels[rel.id] = label
        ends = []
        for nid in (rel.source, rel.target):
            n = nodes[nid]
            ends.append(End(nid, Rect(*n.shape_rect()), n.label_h if n.kind == "icon" else 0.0))
        reqs.append(EdgeReq(rel.id, ends[0], ends[1], lw, lh))
    routes = router.route_all(reqs)
    for rel in page.relationships:
        r = routes[rel.id]
        attrs = {"c4Kind": "rel", "c4Type": "Relationship", "c4Description": to_html(rel.label),
                 "c4Technology": to_html(rel.technology), "c4Style": None if rel.style == "default" else rel.style,
                 "c4Color": rel.color, "c4Bidirectional": "1" if rel.bidirectional else None}
        lx = None if r.label_t is None else 2 * r.label_t - 1
        out.edge(rel.id, labels[rel.id], _edge_style(rel, r, theme), rel.source, rel.target, r.points[1:-1], lx, attrs)
        if warnings is not None:
            if not r.ok:
                warnings.append(f"[{page.name}] {rel.id}: no clear path found, drawn as a direct line "
                                f"(move the elements apart or reorder them)")
            elif r.label_clash:
                warnings.append(f"[{page.name}] {rel.id}: label '{rel.label[:40]}' overlaps a shape or another "
                                f"label (shorten it, raise a `gap`, or move one end)")
    return width, height


def render_document(doc: Document, theme: str | None = None, base_dir: Path | None = None,
                    warnings: list[str] | None = None) -> str:
    theme_name = theme or doc.theme
    th = Theme.load(theme_name, doc.theme_overrides, base_dir)
    diagrams = []
    for i, page in enumerate(doc.pages):
        out = _Out()
        w, h = render_page(page, th, out, theme_name, doc.theme_overrides, warnings)
        body = "".join(out.cells)
        diagrams.append(
            f'<diagram name="{_a(page.name)}" id="page-{i + 1}"><mxGraphModel dx="1200" dy="800" grid="1" '
            f'gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
            f'pageWidth="{int(w) + 1}" pageHeight="{int(h) + 1}" math="0" shadow="0"><root><mxCell id="0"/>'
            f'<mxCell id="1" parent="0"/>{body}</root></mxGraphModel></diagram>')
    return '<mxfile host="c4drawio" agent="c4drawio">' + "".join(diagrams) + "</mxfile>\n"


def render_file(src: str | Path, dst: str | Path | None = None, theme: str | None = None,
                warnings: list[str] | None = None) -> Path:
    src = Path(src)
    doc = load_yaml(src)
    dst = Path(dst) if dst else src.with_suffix(".drawio")
    dst.write_text(render_document(doc, theme, src.parent, warnings), encoding="utf-8")
    return dst
