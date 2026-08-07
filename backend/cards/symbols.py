"""Mana pips and the other card symbols, as official Scryfall artwork.

Why not the Mana font (which BUILD-SPEC §16 originally picked): its glyphs are
monochrome, and hybrid and Phyrexian pips are not glyphs at all — `.ms-wu` is two
half-glyphs layered by CSS ::before/::after over a coloured background. Reproducing
that in Pillow means reimplementing the whole pip colour scheme by hand.

Scryfall's /symbology endpoint gives all 84 symbols as complete full-colour SVGs,
hybrids and Phyrexian included, which is what the reference site composites. One file
per symbol, vendored by `manage.py fetch_symbols`, rasterised on demand and cached.
"""

import io
import re
from functools import lru_cache
from pathlib import Path

import cairosvg
from PIL import Image

SYMBOL_DIR = Path(__file__).resolve().parent.parent / "assets" / "symbols"

TOKEN = re.compile(r"\{([^}]{1,6})\}")

# Scryfall's own SVG filenames: '{W/U}' is WU.svg, '{∞}' is INFINITY.svg. The two
# non-ASCII names are the only ones that aren't just the token stripped of {}/ and
# upper-cased, so they are listed rather than transliterated.
_FILENAME_ALIASES = {"∞": "INFINITY", "½": "HALF"}


def _filename(token):
    body = token.strip("{}")
    return _FILENAME_ALIASES.get(body) or body.replace("/", "").upper()


def path_for(token):
    """Vendored SVG path for '{W/U}', or None if we don't have that symbol.

    Unknown returns None so the caller can fall back to drawing the token as literal
    text — a cost must never be silently dropped from a card.
    """
    p = SYMBOL_DIR / f"{_filename(token)}.svg"
    return p if p.is_file() else None


@lru_cache(maxsize=512)
def pip(token, px):
    """Render '{W/U}' as a square RGBA image `px` tall, or None if unknown.

    Cached because a 100-card deck draws the same handful of pips thousands of times.
    """
    p = path_for(token)
    if p is None:
        return None
    png = cairosvg.svg2png(url=str(p), output_width=px, output_height=px)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def split_text(text):
    """Split rules text into ('text', str) and ('symbol', token) runs, in order.

    Oracle text delimits its own symbols ("{T}: Add {G}."), so inline substitution is a
    scan, not a parse. A token we have no artwork for stays literal text.
    """
    runs, pos = [], 0
    for m in TOKEN.finditer(text):
        if path_for(m.group(0)) is None:
            continue
        if m.start() > pos:
            runs.append(("text", text[pos:m.start()]))
        runs.append(("symbol", m.group(0)))
        pos = m.end()
    if pos < len(text):
        runs.append(("text", text[pos:]))
    return runs
