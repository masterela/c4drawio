"""Themes: YAML files with colours, fonts, spacing, element / boundary / relationship styles.

A theme may `extends:` another (built-in name or path); values are deep-merged.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

BUILTIN_DIR = Path(__file__).parent / "themes"


def builtin_themes() -> list[str]:
    return sorted(p.stem for p in BUILTIN_DIR.glob("*.yaml"))


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read(name_or_path: str, base_dir: Path | None) -> tuple[dict, Path | None]:
    p = Path(name_or_path)
    candidates = [p] if p.suffix in (".yaml", ".yml") else []
    if base_dir is not None and candidates:
        candidates.insert(0, base_dir / p)
    candidates.append(BUILTIN_DIR / f"{name_or_path}.yaml")
    for c in candidates:
        if c.is_file():
            return yaml.safe_load(c.read_text(encoding="utf-8")) or {}, c.parent
    raise FileNotFoundError(f"theme '{name_or_path}' not found (built-in: {', '.join(builtin_themes())})")


def load_theme_data(name_or_path: str, base_dir: Path | None = None, _depth: int = 0) -> dict:
    data, here = _read(name_or_path, base_dir)
    parent = data.pop("extends", None)
    if parent and _depth < 10:
        data = deep_merge(load_theme_data(parent, here, _depth + 1), data)
    return data


class Theme:
    def __init__(self, data: dict):
        self.data = data
        self.name = data.get("name", "custom")

    @classmethod
    def load(cls, name_or_path: str = "c4", overrides: dict | None = None, base_dir: Path | None = None) -> Theme:
        return cls(deep_merge(load_theme_data(name_or_path, base_dir), overrides or {}))

    # --- sections ---------------------------------------------------------
    def section(self, key: str) -> dict:
        return self.data.get(key, {}) or {}

    @property
    def font(self) -> dict:
        return self.section("font")

    @property
    def title(self) -> dict:
        return self.section("title")

    @property
    def spacing(self) -> dict:
        return self.section("spacing")

    @property
    def routing(self) -> dict:
        return self.section("routing")

    def color(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self.section("palette").get(value, value)

    def _merged(self, section: str, *keys: str) -> dict:
        sec = self.section(section)
        out = dict(sec.get("default", {}) or {})
        for k in keys:
            out.update(sec.get(k, {}) or {})
        for k in ("fill", "stroke", "font_color", "color"):
            if k in out:
                out[k] = self.color(out[k])
        return out

    def element(self, kind: str) -> dict:
        if kind.endswith("_ext"):
            return self._merged("elements", kind[:-4], "external", kind)
        return self._merged("elements", kind)

    def boundary(self, kind: str) -> dict:
        return self._merged("boundaries", kind)

    def relationship(self, style: str) -> dict:
        parts = [s.strip() for s in (style or "default").split("+") if s.strip()]
        return self._merged("relationships", *parts)

    def badge(self, name: str) -> dict:
        return self._merged("badges", name)
