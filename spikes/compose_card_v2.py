#!/usr/bin/env python3
"""Print real card text onto a generated card — second attempt.

Fixes over v1:
  panels can now be dark        -> text colour flips to light-on-dark when the panel is dark
  text was too small            -> it grows to fill the panel instead of sitting in a corner
  {B}{B}{B} showed as codes      -> mana symbols are drawn inline, as symbols
  type line landed anywhere     -> the ribbon is located separately from the rules panel
  panels found by row-runs      -> replaced by connected-component detection (panels.py), which
                                   can isolate a rectangle horizontally instead of grabbing the
                                   whole width of the card

Run:  python3 compose_card_v2.py
"""
import glob, pathlib, re
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

import panels

BOLD = "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf"
BODY = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
ITAL = "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf"

SYM_FILL = {"W": (255, 251, 213), "U": (170, 224, 250), "B": (203, 194, 191),
            "R": (249, 170, 143), "G": (155, 211, 174), "C": (204, 194, 192)}
TOKEN = re.compile(r"\{([^}]+)\}")

CARDS = {"craterhoof-behemoth": "Craterhoof Behemoth", "dark-ritual": "Dark Ritual",
         "demonic-tutor": "Demonic Tutor", "birds-of-paradise": "Birds of Paradise"}


def scryfall(name):
    r = requests.get("https://api.scryfall.com/cards/named", params={"exact": name},
                     headers={"User-Agent": "mtg-proxy-evidence/0.2"}, timeout=30)
    r.raise_for_status()
    return r.json()


def ink_for(im, box):
    """Light text on a dark panel, dark text on a light one."""
    v = np.asarray(im.crop(box).convert("L")).mean()
    return ((242, 240, 234), (0, 0, 0)) if v < 120 else ((16, 14, 12), (255, 255, 255))


def draw_symbol(im, sym, x, y, size):
    d = ImageDraw.Draw(im)
    d.ellipse([x + size * .05, y + size * .05, x + size * 1.05, y + size * 1.05],
              fill=(0, 0, 0))
    d.ellipse([x, y, x + size, y + size], fill=SYM_FILL.get(sym, SYM_FILL["C"]),
              outline=(28, 24, 20), width=max(1, size // 18))
    glyph = sym if len(sym) <= 2 else sym[0]
    f = ImageFont.truetype(BOLD, int(size * (0.74 if len(glyph) == 1 else 0.55)))
    d.text((x + size / 2, y + size / 2), glyph, font=f, anchor="mm", fill=(26, 22, 18))


def tokenize(text):
    """Split into paragraphs of ('w', word) / ('s', mana symbol) tokens."""
    paras = []
    for para in text.split("\n"):
        toks, pos = [], 0
        for m in TOKEN.finditer(para):
            toks += [("w", w) for w in para[pos:m.start()].split()]
            toks.append(("s", m.group(1)))
            pos = m.end()
        toks += [("w", w) for w in para[pos:].split()]
        if toks:
            paras.append(toks)
    return paras


def layout(paras, font, symsize, width, draw):
    lines, space = [], draw.textlength(" ", font=font)
    for toks in paras:
        cur, cw = [], 0.0
        for kind, val in toks:
            w = symsize if kind == "s" else draw.textlength(val, font=font)
            step = w + (space if cur else 0)
            if cw + step > width and cur:
                lines.append(cur)
                cur, cw, step = [], 0.0, w
            cur.append((kind, val, w))
            cw += step
        if cur:
            lines.append(cur)
    return lines


def draw_block(im, d, lines, font, symsize, x, y, ink, lead):
    space = d.textlength(" ", font=font)
    for ln in lines:
        cx = x
        for kind, val, w in ln:
            if kind == "s":
                draw_symbol(im, val, int(cx), int(y + font.size * 0.12), symsize)
            else:
                d.text((cx, y), val, font=font, fill=ink)
            cx += w + space
        y += lead
    return y


def compose(img_path, card_name, out_path):
    c = scryfall(card_name)
    im = Image.open(img_path).convert("RGB")
    W, H = im.size
    box = panels.find(im, "rules")
    if not box:
        print(f"  {pathlib.Path(img_path).name}: no rules panel — regenerate this card")
        return False
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(im)
    ink, _ = ink_for(im, box)
    pad = int((x1 - x0) * 0.045)
    tw, th = (x1 - x0) - 2 * pad, (y1 - y0) - 2 * pad

    paras = tokenize(c.get("oracle_text") or "")
    flavour = (c.get("flavor_text") or "").replace("\n", " ")

    size = min(int(th * 0.72), int(W * 0.055))
    while size > 15:
        f = ImageFont.truetype(BODY, size)
        lines = layout(paras, f, int(size * 0.92), tw, d)
        need = len(lines) * size * 1.35 + (size * 2.5 if flavour else 0)
        if need <= th:
            break
        size = int(size * 0.93)
    f = ImageFont.truetype(BODY, size)
    lines = layout(paras, f, int(size * 0.92), tw, d)
    symsize = int(size * 0.92)
    lead = size * 1.35

    used = len(lines) * lead + (size * 2.5 if flavour else 0)
    y = y0 + pad + max(0, (th - used) * 0.4)
    y = draw_block(im, d, lines, f, symsize, x0 + pad, y, ink, lead)

    if flavour:
        fi = ImageFont.truetype(ITAL, int(size * 0.92))
        fl = layout(tokenize(flavour), fi, symsize, int(tw * 0.94), d)
        if y + len(fl) * size * 1.2 < y1 - pad:
            draw_block(im, d, fl, fi, symsize, x0 + pad, y + size * 0.55, ink, size * 1.2)

    ribbon = panels.find(im, "ribbon")
    if ribbon:
        rx0, ry0, rx1, ry1 = ribbon
        rink, rhalo = ink_for(im, ribbon)
        ts = max(int(H * 0.021), int((ry1 - ry0) * 0.80))
        while ts > 16 and d.textlength(c["type_line"],
                                       font=ImageFont.truetype(BOLD, ts)) > (rx1 - rx0) * 0.9:
            ts = int(ts * 0.93)
        d.text(((rx0 + rx1) / 2, (ry0 + ry1) / 2), c["type_line"],
               font=ImageFont.truetype(BOLD, ts), anchor="mm", fill=rink,
               stroke_width=max(1, ts // 20), stroke_fill=rhalo)

    cost = TOKEN.findall(c.get("mana_cost") or "")
    if cost:
        s = int(W * 0.058)
        x = W - int(W * 0.04) - s
        for sym in reversed(cost):
            draw_symbol(im, sym, x, int(H * 0.026), s)
            x -= int(s * 1.1)

    if c.get("power"):
        plaque = panels.find(im, "plaque")
        pt = f"{c['power']}/{c['toughness']}"
        if plaque:
            px0, py0, px1, py1 = plaque
            pink, phalo = ink_for(im, plaque)
            ps = int((py1 - py0) * 0.68)
            while ps > 18 and d.textlength(pt, font=ImageFont.truetype(BOLD, ps)) > (px1 - px0) * .8:
                ps = int(ps * 0.92)
            d.text(((px0 + px1) / 2, (py0 + py1) / 2), pt, font=ImageFont.truetype(BOLD, ps),
                   anchor="mm", fill=pink, stroke_width=max(1, ps // 18), stroke_fill=phalo)
        else:
            d.text((W * 0.87, H * 0.94), pt, font=ImageFont.truetype(BOLD, int(W * 0.05)),
                   anchor="mm", fill=(16, 14, 12), stroke_width=5, stroke_fill=(255, 255, 255))

    im.save(out_path, quality=95)
    print(f"  {out_path.name}: {len(lines)} lines @ {size}px, "
          f"ribbon={'y' if ribbon else 'n'}")
    return True


if __name__ == "__main__":
    out = pathlib.Path("evidence-v2/composed"); out.mkdir(parents=True, exist_ok=True)
    for p in sorted(glob.glob("evidence-v2/*.jpg")):
        stem = pathlib.Path(p).stem
        if stem in CARDS:
            compose(p, CARDS[stem], out / f"{stem}-composed.jpg")
