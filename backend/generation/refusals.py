"""Which cards the image model will not paint under their own name.

MEASURED 2026-08-10, n=10 licensed-only cards, named brief with the official art attached
(bd mtg-kx4). Eight generated the actual licensed character first try — Raphael with his sai,
Cloud with the Buster Sword, Frodo with Sting and the Ring, the Fourth Doctor's scarf. Two were
refused with PROHIBITED_CONTENT, with the art attached and without it, and both are Marvel.

That overturns how `prompts._subject` was written. Its licensed branch — describe the card's game
identity and never its proper noun — was generalised from a single rightsholder, and it is right
for Marvel and wrong for the other eight: it paints Raphael as "a legendary mutant ninja turtle"
and loses the character the client explicitly asked for.

Independently confirmed against the reference site's own gallery on the same day: all 3265 of
their cards, and the crossovers in it are Raphael (ten times), Gimli, Sephiroth, Y'shtola and The
One Ring — every one at full likeness, named. There is not a single Marvel card in the gallery,
which is what you would expect if Marvel is the one rightsholder the model blocks.

So: try the name first, and fall back to the game identity only once the model has actually
refused. A refusal repeats forever for a given prompt, so it is worth remembering — the first
user to hit a blocked card pays one wasted generation and everyone after them gets the fallback
for free. The seed below is that measurement, so no Marvel card ever pays it.
"""

import json
from pathlib import Path

STORE = Path(__file__).resolve().parent / "refused.json"

# Scryfall oracle names, exactly as `cards.scryfall` reports them. Seeded from bd mtg-kx4 so the
# measurement is not re-bought a card at a time.
SEED = {
    "Hulk, Bruce Banner",
    "Spider-Man, Web-Slinger",
}


def _load():
    if not STORE.is_file():
        return set()
    try:
        return set(json.loads(STORE.read_text()))
    except (ValueError, OSError):
        # A corrupt cache must not stop a deck generating. The cost of ignoring it is one wasted
        # generation on a blocked card, which is exactly the cost of not having it at all.
        return set()


def is_refused(name):
    """True if this card has already been refused under its own name."""
    return name in SEED or name in _load()


def remember(name):
    """Record a refusal so the next caller skips straight to the fallback brief."""
    if name in SEED:
        return
    known = _load()
    known.add(name)
    try:
        STORE.write_text(json.dumps(sorted(known), indent=1))
    except OSError:
        # Best-effort: an unwritable cache costs a repeated generation, not a wrong card.
        pass
