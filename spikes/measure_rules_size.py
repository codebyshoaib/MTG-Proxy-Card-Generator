"""Is RULES_MIN = 0.020 the wrong floor, or is the painted panel too small?

`compositor.RULES_MIN = 0.020` fails a card whose rules text had to be set below 2.0% of the
card's height (48px on our 2400px canvas). Nothing has ever checked that number against what
Wizards themselves print, and real cards DO set long text smaller. So this measures the truth
curve before anyone writes a fix against a threshold nobody validated.

METRIC: x-height as a fraction of card height. Not font size — font size is not comparable
across faces (real cards are Plantin, we ship PT Serif, and their x-height/em ratios differ).
x-height is what the eye actually resolves across a table, so it is the honest comparable, and
it is measured here by ONE algorithm applied to both sides.

Three numbers come out:
  1. real_x   — what Wizards prints, per oracle character count.
  2. ours     — the x-height RULES_MIN permits at its floor.
  3. need     — the panel height our typesetter would need to MATCH Wizards at that count.

(1) vs (2) says whether the floor is wrong. (3) says whether the panel is.
"""

import json
import statistics
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import os  # noqa: E402

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()  # cards.scryfall imports cards.models, so the app registry has to be up.

from cards import fonts, textlayout  # noqa: E402

# Reuse the repo's own identifying User-Agent and rate limit rather than inventing a second
# Scryfall client — CLAUDE.md makes both a correctness rule, not a style one.
from cards.scryfall import API, BATCH, DELAY, HEADERS  # noqa: E402

CACHE = Path(__file__).parent / "cards-cache"
CACHE.mkdir(exist_ok=True)

# Our canvas, and the panel width a rules strip actually gets: measured strips run about 84% of
# the card's width once the painted edge material is clear of them.
CANVAS_H = 2400
CANVAS_W = 1792
# The INNER width the text actually wraps to: a strip about 88% of the card, less the compositor's
# PAD at each end. Measuring against the outer width assumes a wider measure than the text ever
# gets and under-counts the lines.
PANEL_W = round(CANVAS_W * 0.88 * (1 - 2 * 0.055))
RULES_MIN = 0.020

# Normal-layout, non-planeswalker cards chosen to span oracle length from a single keyword to
# the longest text that still fits a printed card. Planeswalkers and DFCs are excluded because
# their text box geometry is a different renderer (bd mtg-dw2, mtg-35r).
NAMES = [
    # short
    "Llanowar Elves", "Counterspell", "Shock", "Serra Angel", "Giant Growth",
    "Lightning Bolt", "Sol Ring", "Dark Ritual", "Swords to Plowshares",
    # medium
    "Baleful Strix", "Eternal Witness", "Wall of Omens", "Kokusho, the Evening Star",
    "Elesh Norn, Grand Cenobite", "Avacyn, Angel of Hope", "Sheoldred, the Apocalypse",
    "Consecrated Sphinx", "Mulldrifter", "Reflector Mage", "Solemn Simulacrum",
    # long
    "Craterhoof Behemoth", "Grave Titan", "Atraxa, Praetors' Voice", "Snapcaster Mage",
    "Jin-Gitaxias, Core Augur", "Kozilek, Butcher of Truth", "Sen Triplets",
    "Nekusar, the Mindrazer", "Zacama, Primal Calamity", "Ulamog, the Ceaseless Hunger",
    # very long
    "The One Ring", "Emrakul, the Promised End", "Niv-Mizzet Reborn", "Sisay, Weatherlight Captain",
    "Kenrith, the Returned King", "Urza, Lord High Artificer", "Omnath, Locus of Creation",
    "Kaldra Compleat", "Golos, Tireless Pilgrim", "Najeela, the Blade-Blossom",
    "Lurrus of the Dream-Den", "Korvold, Fae-Cursed King", "Yidris, Maelstrom Wielder",
    "Ramos, Dragon Engine",
]


def fetch():
    """Scryfall metadata for every name, via /cards/collection in batches of 75."""
    cache = CACHE / "meta.json"
    if cache.exists():
        return json.loads(cache.read_text())
    found = []
    for i in range(0, len(NAMES), BATCH):
        chunk = NAMES[i : i + BATCH]
        time.sleep(DELAY)
        response = requests.post(
            f"{API}/cards/collection",
            json={"identifiers": [{"name": n} for n in chunk]},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        for miss in body.get("not_found", []):
            print(f"  NOT FOUND: {miss}", file=sys.stderr)
        found.extend(body["data"])
    cache.write_text(json.dumps(found))
    return found


def image(card):
    """The 745x1040 PNG, cached on disk so a rerun costs nothing."""
    path = CACHE / f"{card['id']}.png"
    if not path.exists():
        url = (card.get("image_uris") or {}).get("png")
        if not url:
            return None
        time.sleep(DELAY)
        path.write_bytes(requests.get(url, headers=HEADERS, timeout=30).content)
    return Image.open(path).convert("L")


# ---------------------------------------------------------------------------------------------
# The one measurement, applied to real cards and to our own rendering alike.
# ---------------------------------------------------------------------------------------------

def bands(grey, top, bottom, left, right):
    """Rows of ink in the crop, as (start, end, per-row ink counts).

    Threshold is per-row against that row's own median, because the 2015 text box is a gradient:
    a single global cutoff reads the bottom of the box as ink.
    """
    pixels = grey.load()
    rows = []
    for y in range(top, bottom):
        line = [pixels[x, y] for x in range(left, right)]
        background = statistics.median(line)
        rows.append(sum(1 for v in line if v < background - 40))

    out, start = [], None
    for i, count in enumerate(rows):
        if count >= 3 and start is None:
            start = i
        elif count < 3 and start is not None:
            out.append((start, i, rows[start:i]))
            start = None
    if start is not None:
        out.append((start, len(rows), rows[start:]))
    return out


def x_height(band):
    """Longest run of rows carrying at least half the band's peak ink.

    Lowercase bodies pack far more ink per row than ascenders and descenders do, so that run IS
    the x-height zone. Works on serif text without needing the font's own metrics — which is the
    point, since the real cards' face is Plantin and we cannot load it.
    """
    _, _, counts = band
    if not counts:
        return 0
    cutoff = max(counts) * 0.5
    best = run = 0
    for count in counts:
        run = run + 1 if count >= cutoff else 0
        best = max(best, run)
    return best


def measure_real(card):
    """(pitch, x-height) of the printed rules text, each as a fraction of card height.

    PITCH — baseline to baseline — is the load-bearing number, because our own `textlayout.wrap`
    returns exactly that for our side, so the two are produced by the same definition rather than
    by me estimating a font metric on one side and reading it off code on the other. x-height
    comes along as a sanity check against the 34px-vs-24px note in textlayout's docstring.
    """
    grey = image(card)
    if grey is None:
        return None
    w, h = grey.size
    # BELOW the type line: the 2015 type bar sits at roughly y 0.56-0.61 and its lettering is
    # larger than the rules text, so starting at 0.58 measured the type line as if it were a
    # rules line on every card. Stop above the P/T box and the collector row.
    top, bottom = int(h * 0.615), int(h * 0.895)
    found = bands(grey, top, bottom, int(w * 0.09), int(w * 0.91))
    # A full text line at 1040px is 22-35 rows tall. Anything shorter is a paragraph divider, a
    # box edge, or the search window clipping a row in half.
    found = [b for b in found if 12 <= (b[1] - b[0]) <= 45 and b[0] > 0 and b[1] < bottom - top]
    if len(found) < 2:
        return None
    # Short final lines of a paragraph carry too little ink for the x-height run to be stable —
    # that is what dragged Sheoldred to a third of every other card. Keep the full-ish lines.
    peak = statistics.median(max(b[2]) for b in found)
    full = [b for b in found if max(b[2]) >= peak * 0.5]

    tops = sorted(b[0] for b in full)
    gaps = [b - a for a, b in zip(tops, tops[1:])]
    if not gaps:
        return None
    # Consecutive lines WITHIN a paragraph give the pitch; the gap between paragraphs is larger
    # and must not be averaged in.
    tight = [g for g in gaps if g <= min(gaps) * 1.35]
    heights = [x for x in (x_height(b) for b in full) if x >= 3]
    if not heights:
        return None
    # A card with one rules line has no within-paragraph gap at all, so the only gap available is
    # rules-to-flavour — which includes the divider and is not pitch. Shock measured 6.4% that
    # way, nearly double every other card. Report the line count so the summary can drop them.
    return statistics.median(tight) / h, statistics.median(heights) / h, len(full)


def measure_ours(size):
    """x-height of PT Serif at `size`, by the SAME algorithm, so the two are comparable."""
    canvas = Image.new("L", (900, size * 3), 255)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(str(fonts.REGULAR), size)
    draw.text((10, size), "amounts numerous creatures overrun", font=font, fill=0)
    found = bands(canvas, 0, canvas.height, 0, canvas.width)
    return max((x_height(b) for b in found), default=0)


PT_X_RATIO = None  # x-height per point of PT Serif, measured once at a large size.


def our_pitch(size):
    """Our own baseline-to-baseline distance at `size` — straight out of the shipping code."""
    _, line_height, _ = textlayout.wrap(textlayout.atoms("the quick brown fox"), size, PANEL_W, None)
    return line_height


def size_for_pitch(target_px):
    """The font size at which OUR pitch matches a real card's, rescaled to our canvas."""
    for size in range(20, 200):
        if our_pitch(size) >= target_px:
            return size
    return 200


def panel_needed(oracle, size):
    """Panel height, as a fraction of the card, to hold this oracle text at `size`.

    Answers the other half: if the floor is fine and cards still come out small, the panel the
    model painted was never tall enough to hold the text at a readable size in the first place.
    """
    text = "\n".join(p for p in oracle.split("\n") if p.strip())
    # ONE pass over the whole oracle, as `compositor._rules` does it. Measuring each ability alone
    # and adding the results drops the gap `block_height` charges BETWEEN abilities — on a
    # four-ability card that is three gaps, and it under-reports the panel by several points.
    wrapped, line_height, _ = textlayout.wrap(textlayout.atoms(text), size, PANEL_W, None)
    return textlayout.block_height(wrapped, line_height) / CANVAS_H


def main():
    global PT_X_RATIO
    PT_X_RATIO = measure_ours(400) / 400
    floor_size = round(CANVAS_H * RULES_MIN)
    floor_pitch = our_pitch(floor_size) / CANVAS_H
    floor_x = floor_size * PT_X_RATIO / CANVAS_H

    print(f"PT Serif x-height/em        {PT_X_RATIO:.4f}   (measured, not looked up)")
    print(f"RULES_MIN = {RULES_MIN}          {floor_size}px font on a {CANVAS_H}px card")
    print(f"  the floor as line pitch   {floor_pitch*100:.3f}% of card height")
    print(f"  the floor as x-height     {floor_x*100:.3f}% of card height\n")

    rows, skipped = [], []
    for card in fetch():
        oracle = card.get("oracle_text") or ""
        # Retro-frame reprints have a different text box entirely — measuring them would compare
        # our 2015-frame target against a 1997 layout.
        if not oracle.strip() or card.get("layout") != "normal" or card.get("frame") != "2015":
            skipped.append(f"{card['name']} (frame {card.get('frame')})")
            continue
        got = measure_real(card)
        if got is None:
            skipped.append(f"{card['name']} (unreadable)")
            continue
        pitch, xh, lines = got
        size = size_for_pitch(pitch * CANVAS_H)
        rows.append(
            (len(oracle), card["name"], pitch, xh, size, panel_needed(oracle, size), lines)
        )

    rows.sort()
    print(f"{'chars':>5}  {'card':32} {'lines':>5} {'pitch%':>7} {'x-ht%':>7} "
          f"{'vs floor':>9} {'our size':>9} {'panel':>7}")
    print("-" * 96)
    for chars, name, pitch, xh, size, need, lines in rows:
        flag = " BELOW FLOOR" if pitch < floor_pitch else ("  (pitch n/a)" if lines < 3 else "")
        print(f"{chars:5}  {name[:32]:32} {lines:5} {pitch*100:6.3f}% {xh*100:6.3f}% "
              f"{pitch/floor_pitch:8.2f}x {size:8}px {need*100:6.1f}%{flag}")

    # Only cards with 3+ measured lines have a real within-paragraph pitch.
    solid = [r for r in rows if r[6] >= 3]
    below = [r for r in solid if r[2] < floor_pitch]
    print(f"\n=== {len(solid)} cards with a trustworthy pitch (3+ lines), "
          f"{len(rows) - len(solid)} single/double-line cards excluded from the stats ===\n")
    print(f"{len(below)} of {len(solid)} real printed cards set rules text SMALLER than "
          f"RULES_MIN allows.")
    print(f"median real pitch   {statistics.median(r[2] for r in solid)*100:.3f}%    "
          f"our floor {floor_pitch*100:.3f}%    "
          f"SMALLEST real {min(r[2] for r in solid)*100:.3f}% "
          f"({min(solid, key=lambda r: r[2])[1]}) = {min(r[2] for r in solid)/floor_pitch:.2f}x "
          f"the floor")
    med_x = statistics.median(r[3] for r in solid)
    print(f"median real x-height {med_x*100:.3f}% = {med_x*CANVAS_H:.0f}px on our canvas "
          f"(textlayout docstring: reference site 34px, ours 24px)")
    print(f"\nfont size we would need to match Wizards: "
          f"median {statistics.median(r[4] for r in solid):.0f}px, "
          f"min {min(r[4] for r in solid)}px  — against a {floor_size}px floor")
    print(f"panel height needed to hold it: median "
          f"{statistics.median(r[5] for r in solid)*100:.1f}% of the card, "
          f"worst {max(r[5] for r in solid)*100:.1f}% ({max(solid, key=lambda r: r[5])[1]})")
    print(f"\nskipped {len(skipped)}: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
