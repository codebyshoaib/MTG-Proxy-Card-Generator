"""Rules text -> lines of words and mana pips, wrapped to fit a box.

Pillow has no rich text engine, and MTG rules text needs four things at once: word wrap,
mana symbols sitting inline mid-sentence on the baseline, italic runs for ability words and
reminder text, and a font size that shrinks until the text fits the panel it was given. This
module is that engine, and nothing in it touches Pillow's drawing side — it measures and
decides, `compositor` draws.

Kept separate from `compositor` because it is the part with all the arithmetic in it, so it is
the part worth testing: `tests/test_textlayout.py` runs it against the real vendored fonts.
"""

import re
from dataclasses import dataclass

from PIL import ImageFont

from cards import fonts, symbols

# An ability word opens a paragraph and is followed by an em dash: "Alliance — Whenever...".
# It is italic on a real card, and the em dash is the only reliable marker.
ABILITY_WORD = re.compile(r"^([A-Z][A-Za-z'’ ]{2,24}) — ")

# Pips are square and set slightly smaller than the cap height so they sit in the line rather
# than pushing it apart. Measured off the reference site's own composited cards.
PIP_SCALE = 0.82

# MEASURED 2026-08-10 against the reference site's own Terror of the Peaks, side by side: their
# lines sit tighter than ours did at 1.14, and each ability is clearly separated instead of the
# whole block running together at one even rhythm. Leading tightened, and the gap moved to where
# it carries meaning — between abilities.
# A multiplier on the font's own ascent+descent, which already carries built-in leading, so a
# value above 1.0 double-counts it — at 1.06 our lines sat visibly further apart than the
# reference site's. Retuned for PT Serif, whose metrics are tighter than EB Garamond's.
LEADING = 0.98
PARAGRAPH_GAP = 0.55

# A paragraph of bare keywords ("Flying", "Flying, vigilance, deathtouch, lifelink") is set
# heavier and larger on a real card, and on theirs. Anything with a sentence in it is not.
KEYWORD_LINE = re.compile(r"^[A-Z][A-Za-z ]*(?:,\s*[a-z][A-Za-z ]*)*$")
# How much larger. `compositor._line` draws at this scale, so anything MEASURING a keyword
# paragraph has to use it too or the block is measured smaller than it is drawn. That was
# harmless while every paragraph shared one slab and the paragraph gaps absorbed it; with one
# panel per paragraph a lone "Flying" is the entire content of its panel and the error is the
# whole error.
KEYWORD_SCALE = 1.28


@dataclass(frozen=True)
class Atom:
    """One indivisible thing on a line: a word, or a mana symbol."""

    text: str
    italic: bool = False
    symbol: bool = False
    keyword: bool = False
    # Flavour text is not rules text. A real card sets it italic BELOW a divider rule, and it
    # carries no game meaning — which is exactly why it must be visually separable: a player
    # reading the card has to be able to tell at a glance which words are rules.
    flavour: bool = False


def is_keyword_line(paragraph):
    return bool(KEYWORD_LINE.match(paragraph.strip())) and len(paragraph) < 60


def smart_quotes(text):
    """ASCII quotes as typographic ones, which is what a printed card uses.

    Scryfall ships a straight apostrophe in "that creature's power"; the reference site prints
    "creature’s". Small, but it is visible at card size and it is the difference between text
    that was typeset and text that was pasted.
    """
    out, previous = [], " "
    for char in text:
        if char == "'":
            out.append("’" if previous.isalnum() else "‘")
        elif char == '"':
            out.append("”" if previous.isalnum() or previous in ".,!?" else "“")
        else:
            out.append(char)
        previous = char
    return "".join(out)


def atoms(text, flavour=""):
    """Rules text as a list of lines, each a list of `Atom`.

    Splits on the newlines Scryfall uses between abilities, keeps `{2}{R}` tokens whole, and
    marks the two things MTG sets in italic: an opening ability word, and reminder text in
    parentheses.

    `flavour` is appended as further paragraphs, every atom italic and flagged. It is opt-in
    because the reference site makes it opt-in (`include_flavor_text` in their generate payload),
    and because it competes with the rules text for the one panel we get.
    """
    out = []
    paragraphs = [(p, False) for p in smart_quotes(text).split("\n")]
    paragraphs += [(p, True) for p in smart_quotes(flavour).split("\n") if p.strip()]
    for paragraph, is_flavour in paragraphs:
        # A flavour line is never a keyword line however short it is: "Hulk smash!" matches the
        # keyword shape and would otherwise be set large and heavy in the display face.
        keyword = is_keyword_line(paragraph) and not is_flavour
        italic_until = 0
        match = ABILITY_WORD.match(paragraph)
        if match:
            italic_until = match.end(1)

        line, depth, cursor = [], 0, 0
        for chunk in re.split(r"(\s+)", paragraph):
            if not chunk or chunk.isspace():
                cursor += len(chunk)
                continue
            # Parenthesised reminder text is italic, and the brackets can open and close
            # mid-word ("(Then shuffle.)"), so depth is tracked per chunk rather than per word.
            opens, closes = chunk.count("("), chunk.count(")")
            italic = cursor < italic_until or depth > 0 or opens > closes
            depth = max(0, depth + opens - closes)
            for piece in _split_symbols(chunk):
                line.append(
                    piece
                    if piece.symbol
                    else Atom(
                        piece.text,
                        italic or is_flavour,
                        keyword=keyword,
                        flavour=is_flavour,
                    )
                )
            cursor += len(chunk)
        out.append(line)
    return out


def _split_symbols(chunk):
    """'{2}{R}:' -> two symbol atoms and a ':' word atom, in order."""
    pieces, last = [], 0
    for match in symbols.TOKEN.finditer(chunk):
        if match.start() > last:
            pieces.append(Atom(chunk[last : match.start()]))
        pieces.append(Atom(match.group(0), symbol=True))
        last = match.end()
    if last < len(chunk):
        pieces.append(Atom(chunk[last:]))
    return pieces or [Atom(chunk)]


def _faces(size):
    return (
        ImageFont.truetype(str(fonts.REGULAR), size),
        ImageFont.truetype(str(fonts.ITALIC), size),
    )


def width_of(atom, regular, italic, pip_px):
    if atom.symbol:
        return pip_px
    return (italic if atom.italic else regular).getlength(atom.text)


def starts_flavour(line):
    """True if this visual line is where the flavour text begins — where the divider goes."""
    return bool(line) and line[0].flavour


def wrap(lines, size, max_width, exclude=None):
    """Greedy wrap into visual lines. Returns (visual_lines, line_height, pip_px).

    `exclude` is `(y_from, narrow_width)`: below `y_from`, lines are only `narrow_width` wide.
    That is how text flows around the power/toughness shield, which the AI paints overlapping the
    slab's bottom-right corner — without it the last line runs underneath the shield and the
    numbers sit on top of the rules text (seen on Terror of the Peaks and Atraxa, 2026-08-10).
    """
    regular, italic = _faces(size)
    space = regular.getlength(" ")
    ascent, descent = regular.getmetrics()
    pip_px = max(1, round(size * PIP_SCALE))
    line_height = round((ascent + descent) * LEADING)

    def limit(index):
        if exclude and (index + 1) * line_height > exclude[0]:
            return exclude[1]
        return max_width

    wrapped = []
    for logical in lines:
        first_of_paragraph = True
        current, used = [], 0.0
        for atom in logical:
            w = width_of(atom, regular, italic, pip_px)
            # A pip abutting the previous atom keeps its space: "{2}{R}:" must not break, but
            # "deals {X} damage" needs the gap. Symbols run together, words take a space.
            gap = 0.0 if not current else (0.0 if atom.symbol and current[-1].symbol else space)
            if current and used + gap + w > limit(len(wrapped)):
                wrapped.append((current, first_of_paragraph))
                first_of_paragraph = False
                current, used = [atom], w
                continue
            current.append(atom)
            used += gap + w
        wrapped.append((current, first_of_paragraph))
    return wrapped, line_height, pip_px


def fit(text, box_width, box_height, max_size, min_size=13, exclude=None):
    """Largest size at which `text` wraps inside the box. Returns (size, lines, lh, pip_px).

    Falls back to `min_size` and overflows rather than failing: a card that renders slightly
    tight is a visible imperfection, while a card that fails to render at all costs a credit
    (BUILD-SPEC §12.1). The caller can compare the returned height against the box to know.
    """
    logical = atoms(text)
    smallest = None
    for size in range(int(max_size), int(min_size) - 1, -1):
        wrapped, lh, pip_px = wrap(logical, size, box_width, exclude)
        smallest = (size, wrapped, lh, pip_px)
        if block_height(wrapped, lh) <= box_height:
            return smallest
    return smallest


def block_height(wrapped, line_height):
    """Total height including the gaps between abilities, which the box has to hold too."""
    gaps = sum(1 for i, (_, starts) in enumerate(wrapped) if starts and i)
    return len(wrapped) * line_height + round(gaps * line_height * PARAGRAPH_GAP)


def fit_across(paragraphs, boxes, max_size, min_size=13, excludes=None, flavours=None):
    """Largest ONE size at which every paragraph fits its own panel.

    MEASURED 2026-08-10 against tcggenerator.com's own full-resolution Terror of the Peaks
    (cdn.proxyprintery.de/ai_proxy_cards/<uuid>.png, the same 1792x2400 canvas we generate on):
    they set the three oracle paragraphs on three separate pale strips, not one slab. That is
    the whole reason their body text is 1.4x ours — x-height 34px against our 24px — because a
    strip holding two lines can be set far larger than a slab holding five.

    One size for all of them rather than a best fit per panel. Two abilities on the same card at
    different sizes is the defect `compositor.RULES_MIN` exists to catch across a deck, and it is
    worse here because both are in view at once.

    Returns (size, [(wrapped, line_height, pip_px), ...]) parallel to `paragraphs`, and falls
    back to `min_size` overflowing rather than failing — same contract as `fit`.
    """
    flavours = list(flavours or [""] * len(paragraphs))
    logical = [atoms(text, flavour) for text, flavour in zip(paragraphs, flavours)]
    scales = [
        KEYWORD_SCALE if is_keyword_line(text) and not flavour else 1.0
        for text, flavour in zip(paragraphs, flavours)
    ]
    excludes = list(excludes or [None] * len(paragraphs))
    smallest = None
    for size in range(int(max_size), int(min_size) - 1, -1):
        laid, fits = [], True
        for lines, (width, height), exclude, scale in zip(logical, boxes, excludes, scales):
            drawn = max(1, round(size * scale))
            wrapped, line_height, pip_px = wrap(lines, drawn, width, exclude)
            laid.append((wrapped, line_height, pip_px))
            if block_height(wrapped, line_height) > height:
                fits = False
        smallest = (size, laid)
        if fits:
            return smallest
    return smallest
