from pathlib import Path

import pytest
import yaml

from c4drawio import load_document, parse_drawio, render_document
from c4drawio.layout import layout_page
from c4drawio.model import ModelError, dump_yaml, load_yaml
from c4drawio.render import _obstacles
from c4drawio.router import Rect
from c4drawio.theme import Theme

HERE = Path(__file__).parent
EXAMPLES = [HERE.parent / "src" / "c4drawio" / "example.yaml", HERE.parent / "examples" / "c4-containers.yaml"]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_render_has_no_warnings(path):
    warnings = []
    xml = render_document(load_yaml(path), warnings=warnings)
    assert xml.startswith("<mxfile")
    assert warnings == []


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_round_trip_is_stable(path, tmp_path):
    a = tmp_path / "a.drawio"
    a.write_text(render_document(load_yaml(path)), encoding="utf-8")
    y1 = dump_yaml(parse_drawio(a))
    b = tmp_path / "b.yaml"
    b.write_text(y1, encoding="utf-8")
    c = tmp_path / "c.drawio"
    c.write_text(render_document(load_yaml(b)), encoding="utf-8")
    assert dump_yaml(parse_drawio(c)) == y1


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_routes_avoid_shapes(path, tmp_path):
    """No routed segment may cross the interior of a shape it does not connect."""
    doc = load_yaml(path)
    theme = Theme.load(doc.theme)
    out = tmp_path / "x.drawio"
    out.write_text(render_document(doc), encoding="utf-8")
    parsed = parse_drawio(out)
    page = doc.pages[0]
    layout_page(page, theme)
    obstacles, _, _ = _obstacles(page, theme)
    import re
    xml = out.read_text(encoding="utf-8")
    for rel in page.relationships:
        cell = re.search(r'<object id="%s".*?</object>' % re.escape(rel.id.replace(">", "&gt;")), xml).group(0)
        pts = [(float(x), float(y)) for x, y in re.findall(r'mxPoint x="([-\d.]+)" y="([-\d.]+)"', cell)]
        for a, b in zip(pts, pts[1:]):
            seg = Rect(min(a[0], b[0]), min(a[1], b[1]), abs(b[0] - a[0]) or 0.01, abs(b[1] - a[1]) or 0.01)
            for nid, rects in obstacles.items():
                if nid in (rel.source, rel.target):
                    continue
                for r in rects:
                    inner = r.inflate(-1)
                    assert not inner.intersects(seg), f"{rel.id} crosses {nid}"
    assert parsed.pages[0].relationships


def test_validation_errors():
    with pytest.raises(ModelError):
        load_document({"elements": [{"id": "a", "kind": "nope"}]})
    with pytest.raises(ModelError):
        load_document({"elements": [{"id": "a"}], "relationships": [{"from": "a", "to": "b"}]})
    with pytest.raises(ModelError):
        load_document({"elements": [{"id": "a"}, {"id": "a"}]})


def test_theme_inheritance_and_overrides():
    th = Theme.load("aws", {"elements": {"container": {"fill": "red"}}, "palette": {"red": "#FF0000"}})
    assert th.element("container")["fill"] == "#FF0000"
    assert th.boundary("vpc")["aws_group"] == "group_vpc"          # inherited from c4
    assert th.relationship("async+data")["dashed"] is True
    assert th.relationship("async+data")["color"] == "#01A88D"


def test_single_page_shorthand_and_raw_cells(tmp_path):
    doc = load_document(yaml.safe_load("""
title: T
elements:
  - {id: a, kind: system, name: A}
  - {id: b, kind: system_ext, name: B}
relationships:
  - {from: a, to: b, label: uses}
"""))
    p = tmp_path / "s.drawio"
    xml = render_document(doc)
    # simulate a shape added by hand in draw.io
    xml = xml.replace("</root>", '<mxCell id="hand" value="Added in draw.io" style="ellipse;" vertex="1" parent="1">'
                                 '<mxGeometry x="10" y="400" width="80" height="40" as="geometry"/></mxCell></root>')
    p.write_text(xml, encoding="utf-8")
    back = parse_drawio(p)
    kinds = {n.id: n.kind for n in back.pages[0].root.walk()}
    assert kinds["hand"] == "raw" and kinds["a"] == "system" and kinds["b"] == "system_ext"
    assert back.pages[0].title == "T"
