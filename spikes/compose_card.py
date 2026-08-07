#!/usr/bin/env python3
"""Step 2 of the match test: print the real card text onto a generated card.

The model paints the art and the empty scroll. This finds the scroll and prints the real
Scryfall type line and rules text into it, so the finished card carries correct game text
no matter what the model drew.

Panel finding is deliberately crude — largest flat, bright, low-detail region in the lower
half. Good enough to prove the pipeline; the production version is Milestone 1 work.

Run:  python3 compose_card.py evidence/A-craterhoof-behemoth.jpg "Craterhoof Behemoth"
"""
import sys, pathlib
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SERIF = "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf"
BODY = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"


def scryfall(name):
    r = requests.get("https://api.scryfall.com/cards/named", params={"exact": name},
                     headers={"User-Agent": "mtg-proxy-evidence/0.1"}, timeout=30)
    r.raise_for_status()
    return r.json()


def find_panel(im, top_frac=0.45, bot_frac=1.0):
    """Largest flat bright block in the lower part of the card = the rules scroll."""
    g = np.asarray(im.convert("L").filter(ImageFilter.GaussianBlur(2)), dtype=np.float32)
    h, w = g.shape
    y0, y1 = int(h * top_frac), int(h * bot_frac)
    band = g[y0:y1]
    # local detail: difference from a heavily blurred copy. Flat surfaces score near zero.
    smooth = np.asarray(Image.fromarray(band.astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(18)), dtype=np.float32)
    flat = (np.abs(band - smooth) < 9) & (band > 110)
    # widest run of flat pixels per row, then the tallest stack of wide rows
    rows = flat.mean(axis=1)
    good = rows > 0.45
    best, run, start = (0, 0, 0), 0, 0
    for i, ok in enumerate(good):
        if ok:
            run = run + 1 if run else 1
            start = i - run + 1
            if run > best[0]:
                best = (run, start, i)
    if best[0] < 40:
        return None
    r0, r1 = y0 + best[1], y0 + best[2]
    cols = flat[best[1]:best[2] + 1].mean(axis=0) > 0.5
    xs = np.flatnonzero(cols)
    if xs.size < 40:
        return None
    return int(xs[0]), r0, int(xs[-1]), r1


def wrap(draw, text, font, width):
    out, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            out.append(line); line = word
    if line:
        out.append(line)
    return out


def compose(img_path, card_name, out_path):
    c = scryfall(card_name)
    im = Image.open(img_path).convert("RGB")
    box = find_panel(im)
    if not box:
        print(f"  no panel found in {img_path}"); return None
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(im)
    pad = int((x1 - x0) * 0.05)
    tw = (x1 - x0) - 2 * pad

    # type line sits just above the panel, rules text inside it
    size = max(22, int((y1 - y0) * 0.115))
    ftype = ImageFont.truetype(SERIF, size)
    fbody = ImageFont.truetype(BODY, size)
    d.text((x0 + pad, y0 - int(size * 1.6)), c["type_line"], font=ftype,
           fill=(15, 15, 20), stroke_width=max(2, size // 14), stroke_fill=(255, 255, 255))

    lines = []
    for para in (c.get("oracle_text") or "").split("\n"):
        lines += wrap(d, para, fbody, tw)
    while len(lines) * size * 1.32 > (y1 - y0) - 2 * pad and size > 18:
        size = int(size * 0.92)
        fbody = ImageFont.truetype(BODY, size)
        lines = []
        for para in (c.get("oracle_text") or "").split("\n"):
            lines += wrap(d, para, fbody, tw)

    y = y0 + pad
    for ln in lines:
        d.text((x0 + pad, y), ln, font=fbody, fill=(18, 16, 14))
        y += int(size * 1.32)

    if c.get("power"):
        fpt = ImageFont.truetype(SERIF, int(im.width * 0.045))
        pt = f"{c['power']}/{c['toughness']}"
        d.text((im.width * 0.86, im.height * 0.925), pt, font=fpt, anchor="mm",
               fill=(15, 15, 20), stroke_width=5, stroke_fill=(255, 255, 255))

    im.save(out_path, quality=95)
    print(f"  composed {out_path}  panel={box}  {len(lines)} lines @ {size}px")
    return out_path


if __name__ == "__main__":
    jobs = [("evidence/A-craterhoof-behemoth.jpg", "Craterhoof Behemoth"),
            ("evidence/B-craterhoof-behemoth-run2.jpg", "Craterhoof Behemoth"),
            ("evidence/A-dark-ritual.jpg", "Dark Ritual"),
            ("evidence/A-birds-of-paradise.jpg", "Birds of Paradise"),
            ("evidence/A-demonic-tutor.jpg", "Demonic Tutor")]
    if len(sys.argv) > 2:
        jobs = [(sys.argv[1], sys.argv[2])]
    out = pathlib.Path("evidence/composed"); out.mkdir(parents=True, exist_ok=True)
    for path, name in jobs:
        compose(path, name, out / (pathlib.Path(path).stem + "-composed.jpg"))
