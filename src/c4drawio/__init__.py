"""c4drawio: C4-style YAML <-> draw.io diagrams with automatic layout and orthogonal routing."""

from .model import Document, load_document, load_yaml
from .parser import parse_drawio
from .render import render_document, render_file

__all__ = ["Document", "load_document", "load_yaml", "parse_drawio", "render_document", "render_file"]
__version__ = "0.1.0"
