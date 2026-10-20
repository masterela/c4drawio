"""Obstacle-avoiding orthogonal edge router (pure Python, no libavoid).

Approach
--------
1. Build a sparse orthogonal grid from the borders of every obstacle (shapes inflated by a margin), the
   centre of every channel between them, and every port stub.
2. Mark grid nodes / segments that run *inside* an obstacle as blocked; count, for each segment, how many
   container borders it crosses.
3. A* over (node, direction) states. Cost = length + bend penalty + container-crossing penalty + penalty for
   running on top of an already routed, unrelated line.
4. Pass 1 lets each edge pick the best side of its source and target. Pass 2 spreads the edges that share a
   side along that side (ordered to avoid crossings) and re-routes with the final ports.
5. Labels go on the longest free segment.
"""

from __future__ import annotations

import heapq
import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

SIDES = ("top", "right", "bottom", "left")
NORMAL = {"top": (0, -1), "right": (1, 0), "bottom": (0, 1), "left": (-1, 0)}
DVEC = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIR_OF = {v: i for i, v in enumerate(DVEC)}
OPP = (1, 0, 3, 2)


def rd(v: float) -> float:
    return round(v, 1)


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def r(self) -> float:
        return self.x + self.w

    @property
    def b(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def inflate(self, m: float) -> Rect:
        return Rect(self.x - m, self.y - m, self.w + 2 * m, self.h + 2 * m)

    def intersects(self, o: Rect) -> bool:
        return self.x < o.r and o.x < self.r and self.y < o.b and o.y < self.b


@dataclass
class End:
    node: str
    rect: Rect                  # shape rect: ports sit on its sides
    bottom_dy: float = 0.0      # extra offset below the shape (icon labels)
    sides: tuple = SIDES


@dataclass
class EdgeReq:
    id: str
    src: End
    tgt: End
    label_w: float = 0.0
    label_h: float = 0.0


@dataclass
class Route:
    points: list[tuple[float, float]]
    src_side: str
    tgt_side: str
    src_frac: float
    tgt_frac: float
    src_dy: float = 0.0
    tgt_dy: float = 0.0
    label_t: float | None = None  # relative position of the label along the path (0..1)
    label_clash: bool = False     # label still overlaps a shape or another label
    ok: bool = True


def port_point(end: End, side: str, f: float) -> tuple[float, float]:
    r = end.rect
    if side == "top":
        return (r.x + f * r.w, r.y)
    if side == "bottom":
        return (r.x + f * r.w, r.b + end.bottom_dy)
    if side == "left":
        return (r.x, r.y + f * r.h)
    return (r.r, r.y + f * r.h)


def side_penalty(side: str, frm: Rect, to: Rect) -> float:
    nx, ny = NORMAL[side]
    dx, dy = to.cx - frm.cx, to.cy - frm.cy
    # facing side if the other shape lies beyond this side
    if side == "right" and to.x >= frm.r:
        return 0.0
    if side == "left" and to.r <= frm.x:
        return 0.0
    if side == "bottom" and to.y >= frm.b:
        return 0.0
    if side == "top" and to.b <= frm.y:
        return 0.0
    dot = nx * dx + ny * dy
    return 25.0 if dot > 0 else (60.0 if dot == 0 else 120.0)


class Grid:
    def __init__(self, obstacles: list[Rect], borders: list[Rect], points: list[tuple[float, float]],
                 bounds: Rect, margin: float):
        xs, ys = {rd(bounds.x), rd(bounds.r)}, {rd(bounds.y), rd(bounds.b)}
        for o in obstacles:
            xs.update((rd(o.x), rd(o.r)))
            ys.update((rd(o.y), rd(o.b)))
        for px, py in points:
            xs.add(rd(px))
            ys.add(rd(py))
        self.xs = self._with_channels(sorted(xs), margin)
        self.ys = self._with_channels(sorted(ys), margin)
        nx, ny = len(self.xs), len(self.ys)
        self.nx, self.ny = nx, ny
        self.node_blk = bytearray(nx * ny)
        self.h_blk = bytearray(nx * ny)
        self.v_blk = bytearray(nx * ny)
        self.h_cross = bytearray(nx * ny)
        self.v_cross = bytearray(nx * ny)
        for o in obstacles:
            il, ir = bisect_left(self.xs, rd(o.x)), bisect_left(self.xs, rd(o.r))
            jt, jb = bisect_left(self.ys, rd(o.y)), bisect_left(self.ys, rd(o.b))
            for i in range(il, ir + 1):
                for j in range(jt, jb + 1):
                    k = i * ny + j
                    inside_x, inside_y = il < i < ir, jt < j < jb
                    if inside_x and inside_y:
                        self.node_blk[k] = 1
                    if i < ir and inside_y:
                        self.h_blk[k] = 1
                    if j < jb and inside_x:
                        self.v_blk[k] = 1
        for b in borders:
            jt, jb = bisect_right(self.ys, b.y), bisect_left(self.ys, b.b)
            for X in (b.x, b.r):
                i = bisect_right(self.xs, X) - 1
                if self.xs[i] == X:
                    i -= 1
                if 0 <= i < nx - 1:
                    for j in range(jt, jb):
                        self.h_cross[i * ny + j] = min(255, self.h_cross[i * ny + j] + 1)
            il, ir = bisect_right(self.xs, b.x), bisect_left(self.xs, b.r)
            for Y in (b.y, b.b):
                j = bisect_right(self.ys, Y) - 1
                if self.ys[j] == Y:
                    j -= 1
                if 0 <= j < ny - 1:
                    for i in range(il, ir):
                        self.v_cross[i * ny + j] = min(255, self.v_cross[i * ny + j] + 1)

    @staticmethod
    def _with_channels(vals: list[float], margin: float) -> list[float]:
        out = set(vals)
        for a, b in zip(vals, vals[1:]):
            if b - a > 2 * margin:
                out.add(rd((a + b) / 2))
        return sorted(out)

    def index(self, p: tuple[float, float]) -> tuple[int, int] | None:
        x, y = rd(p[0]), rd(p[1])
        i, j = bisect_left(self.xs, x), bisect_left(self.ys, y)
        if i < self.nx and j < self.ny and self.xs[i] == x and self.ys[j] == y:
            return i, j
        return None


@dataclass
class _Usage:
    owners: dict = field(default_factory=dict)  # segment key -> list of (src node, tgt node)

    def penalty(self, key, src: str, tgt: str, pen: float) -> float:
        lst = self.owners.get(key)
        if not lst:
            return 0.0
        return pen * sum(1 for s, t in lst if s != src and t != tgt)

    def add(self, key, src: str, tgt: str) -> None:
        self.owners.setdefault(key, []).append((src, tgt))


class Router:
    def __init__(self, obstacles: dict[str, list[Rect]], borders: list[Rect], extra_obstacles: list[Rect],
                 margin: float = 12.0, bend: float = 40.0, crossing: float = 70.0, overlap: float = 45.0):
        self.obstacles = obstacles            # node id -> rects of the shape and its label (not inflated)
        self.borders = borders                # container rects (crossing their border costs)
        self.extra = extra_obstacles          # e.g. container title bands
        self.margin, self.bend, self.crossing, self.overlap = margin, bend, crossing, overlap
        shapes = [r for rs in obstacles.values() for r in rs]
        allr = shapes + borders + extra_obstacles
        if allr:
            x0, y0 = min(r.x for r in allr), min(r.y for r in allr)
            x1, y1 = max(r.r for r in allr), max(r.b for r in allr)
        else:
            x0 = y0 = 0.0
            x1 = y1 = 100.0
        self.bounds = Rect(x0 - 3 * margin, y0 - 3 * margin, x1 - x0 + 6 * margin, y1 - y0 + 6 * margin)
        self.inflated = [r.inflate(margin) for r in shapes] + [r.inflate(margin / 2) for r in extra_obstacles]
        self.shapes = shapes

    # ------------------------------------------------------------------ public
    def route_all(self, edges: list[EdgeReq]) -> dict[str, Route]:
        if not edges:
            return {}
        # pass 1: free side choice, ports in the middle of each side
        pts = []
        for e in edges:
            for end in (e.src, e.tgt):
                for s in end.sides:
                    pts += self._port_and_stub(end, s, 0.5)
        grid = Grid(self.inflated, self.borders, pts, self.bounds, self.margin)
        usage = _Usage()
        first = {e.id: self._route(grid, e, usage, None) for e in edges}
        # pass 2: distribute ports along each used side
        fracs = self._distribute(edges, first)
        pts = []
        for e in edges:
            r = first[e.id]
            pts += self._port_and_stub(e.src, r.src_side, fracs[(e.id, "s")])
            pts += self._port_and_stub(e.tgt, r.tgt_side, fracs[(e.id, "t")])
        grid = Grid(self.inflated, self.borders, pts, self.bounds, self.margin)
        usage = _Usage()
        out = {}
        for e in edges:
            r = first[e.id]
            fixed = ((r.src_side, fracs[(e.id, "s")]), (r.tgt_side, fracs[(e.id, "t")]))
            res = self._route(grid, e, usage, fixed)
            if not res.ok:
                res = r
            out[e.id] = res
        self._place_labels(edges, out)
        return out

    # ------------------------------------------------------------------ helpers
    def _port_and_stub(self, end: End, side: str, f: float) -> list[tuple[float, float]]:
        p = port_point(end, side, f)
        n = NORMAL[side]
        return [p, (p[0] + n[0] * self.margin, p[1] + n[1] * self.margin)]

    def _distribute(self, edges: list[EdgeReq], routes: dict[str, Route]) -> dict:
        groups: dict = {}
        for e in edges:
            r = routes[e.id]
            for role, end, side, other in (("s", e.src, r.src_side, r.points[2] if len(r.points) > 3 else None),
                                            ("t", e.tgt, r.tgt_side, r.points[-3] if len(r.points) > 3 else None)):
                oth = e.tgt.rect if role == "s" else e.src.rect
                ref = other if other is not None else (oth.cx, oth.cy)
                groups.setdefault((end.node, side), []).append((e.id, role, ref))
        fracs = {}
        for (node, side), lst in groups.items():
            axis = 0 if side in ("top", "bottom") else 1
            lst.sort(key=lambda t: t[2][axis])
            n = len(lst)
            for k, (eid, role, _) in enumerate(lst):
                fracs[(eid, role)] = (k + 1) / (n + 1)
        return fracs

    def _route(self, grid: Grid, e: EdgeReq, usage: _Usage, fixed) -> Route:
        if e.src.node == e.tgt.node:
            return self._self_loop(e)
        starts, goals = [], {}
        src_opts = [fixed[0]] if fixed else [(s, 0.5) for s in e.src.sides]
        tgt_opts = [fixed[1]] if fixed else [(s, 0.5) for s in e.tgt.sides]
        for s, f in src_opts:
            p, stub = self._port_and_stub(e.src, s, f)
            ij = grid.index(stub)
            if ij and not grid.node_blk[ij[0] * grid.ny + ij[1]]:
                starts.append((ij, DIR_OF[NORMAL[s]], side_penalty(s, e.src.rect, e.tgt.rect), s, f, p))
        for s, f in tgt_opts:
            p, stub = self._port_and_stub(e.tgt, s, f)
            ij = grid.index(stub)
            if ij and not grid.node_blk[ij[0] * grid.ny + ij[1]]:
                arr = DIR_OF[(-NORMAL[s][0], -NORMAL[s][1])]
                goals.setdefault(ij, []).append((arr, side_penalty(s, e.tgt.rect, e.src.rect), s, f, p))
        best = self._astar(grid, starts, goals, usage, e.src.node, e.tgt.node)
        if best is None:
            s0 = (fixed[0] if fixed else ("bottom", 0.5))
            t0 = (fixed[1] if fixed else ("top", 0.5))
            return Route([port_point(e.src, *s0), port_point(e.tgt, *t0)], s0[0], t0[0], s0[1], t0[1],
                         e.src.bottom_dy if s0[0] == "bottom" else 0, e.tgt.bottom_dy if t0[0] == "bottom" else 0,
                         ok=False)
        cells, start, goal = best
        for a, b in zip(cells, cells[1:]):
            usage.add(self._seg_key(grid, a, b), e.src.node, e.tgt.node)
        pts = [start[5]] + [(grid.xs[i], grid.ys[j]) for i, j in cells] + [goal[4]]
        return Route(_simplify(pts), start[3], goal[2], start[4], goal[3],
                     e.src.bottom_dy if start[3] == "bottom" else 0.0,
                     e.tgt.bottom_dy if goal[2] == "bottom" else 0.0)

    @staticmethod
    def _seg_key(grid: Grid, a, b):
        (i1, j1), (i2, j2) = a, b
        if j1 == j2:
            return ("h", min(i1, i2) * grid.ny + j1)
        return ("v", i1 * grid.ny + min(j1, j2))

    def _astar(self, grid: Grid, starts, goals, usage: _Usage, src: str, tgt: str):
        if not starts or not goals:
            return None
        xs, ys, ny = grid.xs, grid.ys, grid.ny
        gpts = [(xs[i], ys[j]) for i, j in goals]

        def h(i, j):
            x, y = xs[i], ys[j]
            return min(abs(x - gx) + abs(y - gy) for gx, gy in gpts)

        heap, best, parent, tie = [], {}, {}, 0
        for k, (ij, d, pen, *_rest) in enumerate(starts):
            key = (ij[0], ij[1], d)
            if pen < best.get(key, math.inf):
                best[key] = pen
                parent[key] = ("start", k)
                heapq.heappush(heap, (pen + h(*ij), tie, pen, 0, key, None))
                tie += 1
        bend, cross_pen, ov = self.bend, self.crossing, self.overlap
        while heap:
            f, _, g, is_goal, key, goal = heapq.heappop(heap)
            if is_goal:
                cells, k = [], key
                while True:
                    cells.append((k[0], k[1]))
                    p = parent[k]
                    if p[0] == "start":
                        start = starts[p[1]]
                        break
                    k = p
                return cells[::-1], start, goal
            if g > best.get(key, math.inf):
                continue
            i, j, d = key
            for arr, pen, *rest in goals.get((i, j), ()):
                total = g + pen + (bend if d != arr else 0)
                heapq.heappush(heap, (total, tie, total, 1, key, (arr, pen, *rest)))
                tie += 1
            for nd in range(4):
                if nd == OPP[d]:
                    continue
                dx, dy = DVEC[nd]
                if dx:
                    ni, nj = i + dx, j
                    if ni < 0 or ni >= grid.nx:
                        continue
                    seg = (i if dx > 0 else ni) * ny + j
                    if grid.h_blk[seg]:
                        continue
                    length, cr, ukey = abs(xs[ni] - xs[i]), grid.h_cross[seg], ("h", seg)
                else:
                    ni, nj = i, j + dy
                    if nj < 0 or nj >= ny:
                        continue
                    seg = i * ny + (j if dy > 0 else nj)
                    if grid.v_blk[seg]:
                        continue
                    length, cr, ukey = abs(ys[nj] - ys[j]), grid.v_cross[seg], ("v", seg)
                if grid.node_blk[ni * ny + nj]:
                    continue
                ng = g + length + (bend if nd != d else 0) + cr * cross_pen + usage.penalty(ukey, src, tgt, ov)
                nkey = (ni, nj, nd)
                if ng < best.get(nkey, math.inf):
                    best[nkey] = ng
                    parent[nkey] = key
                    heapq.heappush(heap, (ng + h(ni, nj), tie, ng, 0, nkey, None))
                    tie += 1
        return None

    def _self_loop(self, e: EdgeReq) -> Route:
        r, m = e.src.rect, self.margin * 2
        pts = [(r.r, r.y + r.h * 0.3), (r.r + m, r.y + r.h * 0.3), (r.r + m, r.y - m), (r.x + r.w * 0.7, r.y - m),
               (r.x + r.w * 0.7, r.y)]
        return Route(pts, "right", "top", 0.3, 0.7)

    # ------------------------------------------------------------------ labels
    def _place_labels(self, edges: list[EdgeReq], routes: dict[str, Route]) -> None:
        blockers = self.shapes + self.extra
        placed: list[Rect] = []
        lines = []  # (edge id, thin rect) for every routed segment
        for eid, r in routes.items():
            for a, b in zip(r.points, r.points[1:]):
                lines.append((eid, Rect(min(a[0], b[0]) - 1, min(a[1], b[1]) - 1,
                                        abs(b[0] - a[0]) + 2, abs(b[1] - a[1]) + 2)))
        for e in edges:
            r = routes[e.id]
            if not e.label_w or len(r.points) < 2:
                continue
            segs = []
            total = 0.0
            for a, b in zip(r.points, r.points[1:]):
                length = abs(b[0] - a[0]) + abs(b[1] - a[1])
                segs.append((length, total, a, b))
                total += length
            if total <= 0:
                continue
            best_t, best_score, best_box, best_hits = None, -math.inf, None, 0
            for length, start, a, b in segs:
                horizontal = a[1] == b[1]
                fits = length >= (e.label_w if horizontal else e.label_h) + 8
                for frac in (0.5, 0.3, 0.7, 0.15, 0.85):
                    mx = a[0] + (b[0] - a[0]) * frac
                    my = a[1] + (b[1] - a[1]) * frac
                    box = Rect(mx - e.label_w / 2, my - e.label_h / 2, e.label_w, e.label_h)
                    pad = box.inflate(3)
                    hits = sum(1 for o in blockers if o.intersects(box)) + 2 * sum(1 for o in placed if o.intersects(pad))
                    crossings = sum(1 for eid, ln in lines if eid != e.id and ln.intersects(pad))
                    score = (-1000 * hits - 150 * crossings + (200 if fits else 0) + (50 if horizontal else 0)
                             + min(length, 400) * 0.1 - abs(frac - 0.5) * 40)
                    if score > best_score:
                        best_score, best_t, best_box, best_hits = score, (start + length * frac) / total, box, hits
            r.label_t = best_t
            r.label_clash = best_hits > 0
            placed.append(best_box)


def _simplify(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in pts:
        p = (rd(p[0]), rd(p[1]))
        if out and out[-1] == p:
            continue
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            if (a[0] == b[0] == p[0]) or (a[1] == b[1] == p[1]):
                out[-1] = p
                continue
        out.append(p)
    return out
