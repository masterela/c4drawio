"""Command line: c4drawio render | parse | validate | themes | icons | example."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import __version__
from .icons import search
from .model import ModelError, dump_yaml, load_yaml
from .parser import parse_drawio
from .render import render_file
from .theme import BUILTIN_DIR, builtin_themes

EXAMPLE = Path(__file__).with_name("example.yaml")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="c4drawio", description=__doc__)
    ap.add_argument("--version", action="version", version=f"c4drawio {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="YAML -> .drawio")
    r.add_argument("src")
    r.add_argument("-o", "--out")
    r.add_argument("-t", "--theme", help="built-in theme name or path to a theme YAML (overrides the file)")

    p = sub.add_parser("parse", help=".drawio -> YAML")
    p.add_argument("src")
    p.add_argument("-o", "--out")
    p.add_argument("--no-layout", action="store_true", help="drop positions/sizes so the next render re-lays out")

    v = sub.add_parser("validate", help="check a YAML diagram")
    v.add_argument("src")

    t = sub.add_parser("themes", help="list / show / copy themes")
    t.add_argument("action", nargs="?", default="list", choices=["list", "show", "init"])
    t.add_argument("name", nargs="?", default="c4")
    t.add_argument("dest", nargs="?")

    i = sub.add_parser("icons", help="search AWS icon names")
    i.add_argument("term", nargs="?", default="")

    e = sub.add_parser("example", help="write an example YAML")
    e.add_argument("-o", "--out", default="example.yaml")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "render":
            warnings: list[str] = []
            out = render_file(a.src, a.out, a.theme, warnings)
            print(f"wrote {out}")
            for w in warnings:
                print(f"warning: {w}", file=sys.stderr)
        elif a.cmd == "parse":
            doc = parse_drawio(a.src, keep_layout=not a.no_layout)
            text = dump_yaml(doc, keep_layout=not a.no_layout)
            if a.out:
                Path(a.out).write_text(text, encoding="utf-8")
                print(f"wrote {a.out}")
            else:
                sys.stdout.write(text)
        elif a.cmd == "validate":
            doc = load_yaml(a.src)
            n = sum(len(p.nodes()) for p in doc.pages)
            m = sum(len(p.relationships) for p in doc.pages)
            print(f"ok: {len(doc.pages)} page(s), {n} element(s), {m} relationship(s)")
        elif a.cmd == "themes":
            if a.action == "list":
                for name in builtin_themes():
                    print(name)
            elif a.action == "show":
                print((BUILTIN_DIR / f"{a.name}.yaml").read_text(encoding="utf-8"))
            else:
                dest = Path(a.dest or f"{a.name}-theme.yaml")
                shutil.copyfile(BUILTIN_DIR / f"{a.name}.yaml", dest)
                print(f"wrote {dest} (edit it, then use `theme: {dest.name}` in your diagram)")
        elif a.cmd == "icons":
            names = search(a.term)
            print("\n".join(names) if names else f"no icon matching '{a.term}'")
        elif a.cmd == "example":
            shutil.copyfile(EXAMPLE, a.out)
            print(f"wrote {a.out}")
    except (ModelError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
