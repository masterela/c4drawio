# AGENTS.md

Guidance for coding agents working on **c4drawio**: C4-style YAML ⇄ draw.io diagrams with automatic layout and
obstacle-avoiding orthogonal routing. User-facing documentation is in [README.md](README.md).

## Hard constraints

- **Pure Python, one runtime dependency (PyYAML).** Do not add dependencies, and do not call the draw.io CLI,
  Node, or any native library from the package. (The draw.io CLI may be used *by developers* for previews.)
- **Python ≥ 3.10**, standard library only besides PyYAML.
- **Round trip must stay stable:** render → parse → render → parse yields identical YAML
  (`test_round_trip_is_stable`). Every new element/boundary field must be written as a `c4*` attribute in
  `render._node_attrs` and read back in `parser._page`.
- **Generated cells keep draw.io's C4 placeholder convention** (`placeholders="1"`, `c4Name`, `c4Type`,
  `c4Technology`, `c4Description`) so users can edit them with Edit > Edit Data.
- **Lines never cross shapes they do not connect** (`test_routes_avoid_shapes`).

## Pipeline

```
YAML ──model.load_document──▶ Document(pages ▸ Node tree + Relationships)
     ──layout.layout_page───▶ sizes and positions (relative x/y, absolute ax/ay)
     ──router.Router────────▶ orthogonal routes, port sides/fractions, label positions
     ──render.render_page───▶ draw.io XML (one <diagram> per page)
.drawio ──parser.parse_drawio──▶ Document (positions kept as pos/size unless --no-layout)
```

| Module | Responsibility |
|---|---|
| `model.py` | Dataclasses (`Node`, `Relationship`, `Page`, `Document`), kinds (`LEAF_KINDS`, `BOUNDARY_KINDS`), YAML loading/validation (`ModelError`), YAML dump |
| `theme.py` | Theme files: `extends:` inheritance, deep merge, `element(kind)` = `default` + kind (+ `external` for `*_ext`), `relationship("a+b")`, palette lookup |
| `themes/*.yaml` | Built-in themes; `c4.yaml` is the complete, commented base every other theme extends |
| `text.py` | Approximate text metrics (no font files) |
| `layout.py` | `measure` (natural sizes, bottom-up) then `place` (positions, top-down); row / column / grid, `justify`, `align`, `stretch`; `label_gaps` widens gaps so relationship labels fit |
| `router.py` | Sparse grid from obstacle borders + channel centres + port stubs; A* over (node, direction) with bend / border-crossing / overlap penalties; pass 1 chooses sides, pass 2 spreads ports; label placement |
| `render.py` | Styles per kind, labels, badges, titles, edges (`exitX/Y`, `entryX/Y`, waypoints); collects warnings |
| `parser.py` | Reads plain or compressed `.drawio`; c4 cells → kinds, unknown cells → `kind: raw` |
| `icons.py` | `aws_icons.txt` (names extracted from draw.io) and AWS category colours |
| `cli.py` | `render`, `parse`, `validate`, `themes`, `icons`, `example` |

Coordinates: children are stored relative to their parent container (draw.io `container=1` cells); edges and
their waypoints are absolute (parent `1`). Top-level `pos` values are absolute page coordinates. For icons,
`pos` is the icon box; the layout footprint also includes the label below it, and the router models an icon as
two obstacles (icon + label) so left/right ports stay free.

## Commands

```
uv venv && uv pip install -e . pytest      # dev environment
uv run pytest -q                           # tests (must pass)
c4drawio render examples/c4-containers.yaml -o out/c4.drawio
c4drawio render src/c4drawio/example.yaml -o out/example.drawio
```

## Visual check (required after layout, routing, style or theme changes)

Tests catch geometry errors, not ugliness. After such changes, render both examples, export PNGs with the
draw.io desktop CLI (`draw.io -x -f png -s 1.2 -b 10 -o out/x.png out/x.drawio`), look at them, and confirm:
no label on a shape, label or line; no text cut off inside shapes; no long detours; `render` prints no warnings
for the examples. Keep `out/` out of git.

## How to extend

- **New leaf or boundary kind:** add it to `model.py` (`LEAF_KINDS` / `BOUNDARY_KINDS`, `C4_TYPE` if relevant),
  give it a section in `themes/c4.yaml`, its style in `render._leaf_style` / `_boundary_style`, its size rule in
  `layout.leaf_size` if needed; document it in README.
- **New theme option:** add it, commented, to `themes/c4.yaml` with a sensible default, read it with a default
  in code, and document it in README's Themes section.
- **New relationship style:** theme-only change (`relationships:` in a theme file).
- **Router changes:** keep the cost model explicit (penalties come from `theme.routing`) and keep both passes.

## Conventions

- Type hints, `from __future__ import annotations`, small pure functions; no global state except the
  per-page `_NEED` gap table in `layout.py` (reset in `layout_page`).
- Shapes that need non-rotated anchors: never use `direction=` in a style (it rotates `exitX/exitY`).
- Keep README.md and this file in sync with behaviour changes.
