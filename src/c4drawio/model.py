"""Diagram model: elements (leaves), boundaries (containers), relationships, pages, documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Leaf kinds. Any of the first six also exists with an "_ext" suffix (external, greyed out).
C4_KINDS = ("person", "system", "container", "database", "queue", "component")
LEAF_KINDS = set(C4_KINDS) | {k + "_ext" for k in C4_KINDS} | {"icon", "note", "text", "raw"}
BOUNDARY_KINDS = {
    "enterprise", "system_boundary", "container_boundary", "group", "lane",
    "aws_cloud", "account", "region", "az", "vpc", "subnet_private", "subnet_public",
    "security_group", "onprem",
}
C4_TYPE = {
    "person": "Person", "system": "Software System", "container": "Container", "database": "Container",
    "queue": "Container", "component": "Component", "enterprise": "Enterprise",
    "system_boundary": "Software System", "container_boundary": "Container",
}
LAYOUTS = ("row", "column", "grid")


def base_kind(kind: str) -> str:
    return kind[:-4] if kind.endswith("_ext") else kind


@dataclass
class Node:
    id: str
    kind: str
    name: str = ""
    technology: str = ""
    description: str = ""
    icon: str | None = None          # aws4 icon name, or any full draw.io shape name (contains a dot)
    color: str | None = None         # fill (palette name or #hex)
    font_color: str | None = None
    badge: str | None = None         # e.g. NEW / EXT
    style: str = ""                  # raw draw.io style appended to the generated one
    # container layout hints
    layout: str = "row"
    columns: int = 0
    gap: float | None = None
    padding: float | None = None
    align: str = "start"             # cross axis: start | center | end
    justify: str = "start"           # main axis: start | center | end | space-between | space-around
    stretch: bool = True             # child boundaries fill the cross axis
    # explicit geometry (relative to parent; for icons: the icon box)
    pos: tuple[float, float] | None = None
    size: tuple[float, float] | None = None
    children: list[Node] = field(default_factory=list)
    parent: Node | None = field(default=None, repr=False)
    # computed by layout
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    ax: float = 0.0
    ay: float = 0.0
    nat_w: float = 0.0
    nat_h: float = 0.0
    label_h: float = 0.0             # icons: height of the label below the icon
    icon_size: float = 0.0

    @property
    def is_boundary(self) -> bool:
        return self.kind in BOUNDARY_KINDS or self.kind == "page"

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def ancestors(self):
        p = self.parent
        while p is not None and p.kind != "page":
            yield p
            p = p.parent

    def shape_rect(self) -> tuple[float, float, float, float]:
        """Absolute rect of the drawn shape (for icons: the icon box only)."""
        if self.kind == "icon":
            s = self.icon_size
            return (self.ax + (self.w - s) / 2, self.ay, s, s)
        return (self.ax, self.ay, self.w, self.h)


@dataclass
class Relationship:
    id: str
    source: str
    target: str
    label: str = ""
    technology: str = ""
    style: str = "default"           # theme relationship style(s), combine with "+": "async+data"
    color: str | None = None
    bidirectional: bool = False


@dataclass
class Page:
    name: str
    root: Node
    title: str = ""
    subtitle: str = ""
    relationships: list[Relationship] = field(default_factory=list)

    def nodes(self) -> dict[str, Node]:
        return {n.id: n for n in self.root.walk() if n.kind != "page"}


@dataclass
class Document:
    pages: list[Page]
    theme: str = "c4"
    theme_overrides: dict = field(default_factory=dict)


class ModelError(ValueError):
    pass


# --------------------------------------------------------------------------- loading
NODE_KEYS = {
    "id", "kind", "name", "technology", "tech", "description", "desc", "icon", "color", "font_color", "badge",
    "style", "layout", "columns", "gap", "padding", "align", "justify", "stretch", "pos", "size", "children",
    "elements",
}


def _pair(v, what, nid):
    if v is None:
        return None
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return (float(v[0]), float(v[1]))
    raise ModelError(f"{nid}: '{what}' must be a list of two numbers, got {v!r}")


def _node(d: dict, ids: set, path: str) -> Node:
    if not isinstance(d, dict):
        raise ModelError(f"{path}: element must be a mapping, got {d!r}")
    unknown = set(d) - NODE_KEYS
    nid = str(d.get("id") or "")
    if not nid:
        raise ModelError(f"{path}: element without 'id'")
    if unknown:
        raise ModelError(f"{nid}: unknown keys {sorted(unknown)}")
    if nid in ids:
        raise ModelError(f"duplicate id '{nid}'")
    ids.add(nid)
    kids = d.get("children", d.get("elements")) or []
    kind = d.get("kind") or ("group" if kids else "container")
    if kind not in LEAF_KINDS and kind not in BOUNDARY_KINDS:
        raise ModelError(f"{nid}: unknown kind '{kind}'. Leaves: {sorted(LEAF_KINDS)}; "
                         f"boundaries: {sorted(BOUNDARY_KINDS)}")
    if kind in LEAF_KINDS and kids:
        raise ModelError(f"{nid}: kind '{kind}' cannot have children (use a boundary kind such as 'group')")
    layout = d.get("layout", "row")
    if layout not in LAYOUTS:
        raise ModelError(f"{nid}: layout must be one of {LAYOUTS}")
    n = Node(
        id=nid, kind=kind, name=str(d.get("name", "") or ""),
        technology=str(d.get("technology", d.get("tech", "")) or ""),
        description=str(d.get("description", d.get("desc", "")) or ""),
        icon=d.get("icon"), color=d.get("color"), font_color=d.get("font_color"),
        badge=d.get("badge"), style=d.get("style", "") or "",
        layout=layout, columns=int(d.get("columns", 0) or 0),
        gap=d.get("gap"), padding=d.get("padding"),
        align=d.get("align", "start"), justify=d.get("justify", "start"), stretch=bool(d.get("stretch", True)),
        pos=_pair(d.get("pos"), "pos", nid), size=_pair(d.get("size"), "size", nid),
    )
    if kind == "icon" and not n.icon:
        raise ModelError(f"{nid}: kind 'icon' needs an 'icon' (e.g. lambda, s3; see `c4drawio icons`)")
    for i, c in enumerate(kids):
        child = _node(c, ids, f"{nid}.children[{i}]")
        child.parent = n
        n.children.append(child)
    return n


def _page(d: dict, idx: int) -> Page:
    ids: set = set()
    root = Node(id="__page__", kind="page", layout=d.get("layout", "row"), gap=d.get("gap"),
                columns=int(d.get("columns", 0) or 0), align=d.get("align", "start"),
                justify=d.get("justify", "start"), padding=0)
    for i, e in enumerate(d.get("elements", d.get("children")) or []):
        c = _node(e, ids, f"pages[{idx}].elements[{i}]")
        c.parent = root
        root.children.append(c)
    rels, seen = [], set()
    for i, r in enumerate(d.get("relationships") or []):
        src, tgt = r.get("from", r.get("source")), r.get("to", r.get("target"))
        for end in (src, tgt):
            if end not in ids:
                raise ModelError(f"relationship #{i}: unknown element '{end}'")
        rid = str(r.get("id") or f"{src}->{tgt}")
        base, k = rid, 2
        while rid in seen or rid in ids:
            rid, k = f"{base}#{k}", k + 1
        seen.add(rid)
        rels.append(Relationship(
            id=rid, source=src, target=tgt, label=str(r.get("label", r.get("description", "")) or ""),
            technology=str(r.get("technology", r.get("tech", "")) or ""), style=r.get("style", "default") or "default",
            color=r.get("color"), bidirectional=bool(r.get("bidirectional", False))))
    return Page(name=str(d.get("name") or f"Page {idx + 1}"), root=root, title=str(d.get("title", "") or ""),
                subtitle=str(d.get("subtitle", "") or ""), relationships=rels)


def load_document(data: dict) -> Document:
    if not isinstance(data, dict):
        raise ModelError("top level must be a mapping")
    pages_data = data.get("pages")
    if pages_data is None:  # single-page shorthand
        pages_data = [{k: v for k, v in data.items() if k not in ("theme", "theme_overrides")}]
    pages = [_page(p, i) for i, p in enumerate(pages_data)]
    return Document(pages=pages, theme=data.get("theme", "c4"), theme_overrides=data.get("theme_overrides") or {})


def load_yaml(path: str | Path) -> Document:
    return load_document(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- dumping
class _Flow(list):
    pass


def _flow_repr(dumper, data):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(_Flow, _flow_repr)


def _num(v: float):
    return int(v) if float(v).is_integer() else round(v, 1)


def node_to_dict(n: Node, keep_layout: bool) -> dict:
    d: dict = {"id": n.id, "kind": n.kind}
    for key in ("name", "technology", "description", "icon", "color", "font_color", "badge", "style"):
        v = getattr(n, key)
        if v:
            d[key] = v
    if n.is_boundary:
        defaults = {"layout": "row", "columns": 0, "gap": None, "padding": None, "align": "start",
                    "justify": "start", "stretch": True}
        for key, dv in defaults.items():
            v = getattr(n, key)
            if v != dv:
                d[key] = v
    if keep_layout:
        if n.pos is not None:
            d["pos"] = _Flow([_num(n.pos[0]), _num(n.pos[1])])
        if n.size is not None:
            d["size"] = _Flow([_num(n.size[0]), _num(n.size[1])])
    if n.children:
        d["children"] = [node_to_dict(c, keep_layout) for c in n.children]
    return d


def document_to_dict(doc: Document, keep_layout: bool = True) -> dict:
    pages = []
    for p in doc.pages:
        pd: dict = {"name": p.name}
        if p.title:
            pd["title"] = p.title
        if p.subtitle:
            pd["subtitle"] = p.subtitle
        if p.root.layout != "row":
            pd["layout"] = p.root.layout
        if p.root.gap is not None:
            pd["gap"] = p.root.gap
        pd["elements"] = [node_to_dict(c, keep_layout) for c in p.root.children]
        rels = []
        for r in p.relationships:
            rd: dict = {"from": r.source, "to": r.target}
            if r.id != f"{r.source}->{r.target}":
                rd["id"] = r.id
            for key in ("label", "technology", "color"):
                if getattr(r, key):
                    rd[key] = getattr(r, key)
            if r.style != "default":
                rd["style"] = r.style
            if r.bidirectional:
                rd["bidirectional"] = True
            rels.append(rd)
        if rels:
            pd["relationships"] = rels
        pages.append(pd)
    out: dict = {"theme": doc.theme}
    if doc.theme_overrides:
        out["theme_overrides"] = doc.theme_overrides
    out["pages"] = pages
    return out


def dump_yaml(doc: Document, keep_layout: bool = True) -> str:
    return yaml.dump(document_to_dict(doc, keep_layout), Dumper=_Dumper, sort_keys=False, allow_unicode=True,
                     width=120, default_flow_style=False)
