# c4drawio

C4-style YAML ⇄ draw.io diagrams. Pure Python (only dependency: PyYAML). No draw.io CLI, no Node, no libavoid.

- **Automatic layout**: containers lay out their children in rows, columns or grids; lanes stretch to a common
  width; gaps widen automatically so relationship labels fit.
- **Obstacle-avoiding orthogonal routing**: A* on a sparse grid with bend, border-crossing and overlap
  penalties; ports spread along each side; labels placed on free segments.
- **Themes**: colours, fonts, sizes, spacing, container and arrow styles in YAML, with inheritance.
- **Round trip**: the generated cells use draw.io's native C4 placeholders (`c4Name`, `c4Type`,
  `c4Technology`, `c4Description`), so `parse` turns a `.drawio` (also one edited by hand) back into YAML.

## Install

```
uv tool install git+https://github.com/masterela/c4drawio    # puts `c4drawio` on PATH
# or, from a clone (edits apply immediately):
uv tool install --editable .
```

## Usage

```
c4drawio example -o demo.yaml
c4drawio render demo.yaml                 # -> demo.drawio (warnings on stderr)
c4drawio parse demo.drawio -o back.yaml   # positions kept; --no-layout to drop them
c4drawio themes list | show aws | init aws my-theme.yaml
c4drawio icons lambda                     # search the 645 AWS icon names draw.io knows
c4drawio validate demo.yaml
```

Optional PNG preview (needs draw.io desktop): `draw.io -x -f png -s 1.5 -b 10 -o demo.png demo.drawio`.

## YAML format

```yaml
theme: aws                 # built-in (c4, aws, mono) or a path to a theme YAML
theme_overrides:           # optional, deep-merged into the theme
  palette: {brand: "#5236AB"}
pages:                     # or put title/elements/relationships at the top level for one page
  - name: Variant A        # draw.io page (tab) name
    title: Target architecture
    subtitle: One line of context
    layout: row            # how the top-level elements are arranged: row | column | grid
    elements:
      - id: cloud          # unique per page; becomes the draw.io cell id
        kind: aws_cloud    # a boundary kind -> it can have children
        name: AWS Cloud
        layout: column     # row | column | grid (with `columns: N`)
        gap: 30            # space between children (default: theme spacing.gap)
        padding: 20
        justify: space-between   # main axis: start | center | end | space-between | space-around
        align: start       # cross axis: start | center | end
        stretch: true      # child boundaries fill the cross axis (default true)
        children:
          - {id: fn, kind: icon, icon: lambda, technology: AWS Lambda, name: Ingest, description: "validate\narchive", badge: NEW}
          - {id: db, kind: database, name: Orders, technology: PostgreSQL, description: Order history}
    relationships:
      - {from: fn, to: db, label: writes, technology: SQL, style: data}
      - {from: db, to: fn, style: async+dotted, color: red}
```

Quote values that contain `: `, `#` or commas inside `{...}` flow mappings.

### Element kinds (leaves)

| kind | look |
|---|---|
| `person`, `system`, `container`, `component` | C4 boxes: **name**, `[Type: technology]`, description |
| `database`, `queue` | cylinder / horizontal drum |
| any of the above + `_ext` | external variant (greyed), e.g. `system_ext` |
| `icon` | an AWS icon (`icon: s3`) or any draw.io shape (`icon: mxgraph.azure.function_apps`); label = technology / **name** / description, below the icon |
| `note`, `text` | sticky note, free text |
| `raw` | anything else (keeps `style`, `name` as label, `pos`, `size`); produced by `parse` for hand-drawn cells |

Common element fields: `name`, `technology`, `description` (use `\n` for line breaks), `color` (fill; palette
name or `#hex`), `font_color`, `badge` (`NEW`, `EXT`, `TBC` or any text), `style` (raw draw.io style appended),
`size: [w, h]`, `pos: [x, y]` (relative to the parent; absolute on the page for top-level elements).

### Boundary kinds (containers)

`enterprise`, `system_boundary`, `container_boundary` (C4, dashed), `group`, `lane` (light panel),
`aws_cloud`, `account`, `region`, `az`, `vpc`, `subnet_private`, `subnet_public`, `security_group`, `onprem`
(official draw.io AWS group shapes).

### Relationship styles

`default`, `sync`, `async` (dashed), `dotted`, `thick`, `thin`, `data` (teal), `control` (blue, thicker),
`error` (red), `warning` (amber), `dependency` (grey dashed). Combine with `+` (`async+data`). Add your own in a
theme. `bidirectional: true` adds a start arrow; `color:` overrides the colour.

## Themes

`c4drawio themes init c4 mine.yaml` copies the fully commented base theme. Sections: `font`, `title`
(position `top-left | top-center | none`, sizes, colours), `spacing` (`page_margin`, `gap`, `padding`,
`title_band`, `route_margin`), `routing` (`bend_penalty`, `crossing_penalty`, `overlap_penalty`, `rounded`,
`jump`, `label_max_width`), `palette`, `elements` (`default` + per kind + `external`), `boundaries`
(`default` + per kind; `title_position: top | bottom`, `dashed`, `dash_pattern`, `rounded`, `aws_group`),
`relationships` (`color`, `width`, `dashed`, `dash_pattern`, `end_arrow`, `start_arrow`, `font_size`),
`badges`. A theme can start with `extends: aws` and only list what changes.

## Python API

```python
from c4drawio import load_yaml, render_document, parse_drawio
warnings = []
xml = render_document(load_yaml("demo.yaml"), warnings=warnings)
doc = parse_drawio("edited.drawio")
```

## Repository layout

```
src/c4drawio/
  model.py      YAML <-> model: kinds, fields, validation, YAML dump
  theme.py      theme loading: extends, deep-merge, per-kind lookups, palette
  themes/       built-in themes (c4.yaml is the fully commented base)
  layout.py     measure / place, automatic label gaps
  router.py     orthogonal A* router and label placement
  render.py     model -> draw.io XML (styles, C4 placeholders, badges)
  parser.py     .drawio -> model (round trip)
  icons.py      AWS icon names (aws_icons.txt) and category colours
  cli.py        command line
  example.yaml  the example written by `c4drawio example`
examples/       more example diagrams
tests/          pytest suite
```

## Development

```
uv venv && uv pip install -e . pytest
uv run pytest -q
```

See [AGENTS.md](AGENTS.md) for the architecture, invariants and the visual check expected after any change to
layout, routing or rendering.
