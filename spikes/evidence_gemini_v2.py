#!/usr/bin/env python3
"""Second attempt. Same four cards, rewritten instructions.

What went wrong the first time, and what changed here:

  art was empty, panels were huge   -> the scene now leads the instruction and gets the most
                                       weight; the furniture is demoted to a short closing note
  no clear subject in spell cards   -> spells get an explicit "invent a dramatic scene depicting
                                       this" line, since "Add {B}{B}{B}" is not a scene
  pale blank parchment panels       -> panels must be tinted to the scene, heavy black outline,
                                       neon rim light, sitting ON TOP of art that runs underneath
  colour identity too weak          -> stated twice, once as palette and once as a hard negative

Run:  python3 evidence_gemini_v2.py
Out:  evidence-v2/*.jpg + evidence-v2/report.json
"""
import base64, io, json, pathlib, time
import requests
from PIL import Image

API = "https://generativelanguage.googleapis.com/v1beta/models"
KEY = next(l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("GEMINI_API_KEY"))
OUT = pathlib.Path("evidence-v2"); OUT.mkdir(exist_ok=True)
PRO = "gemini-3-pro-image"
USD_PER_IMAGE = 0.134

STYLE = ("toxic neon adult-cartoon illustration, bold heavy black ink outlines on every shape, "
         "acid green and violet neon glow, psychedelic slime and vapour, flat cel shading with "
         "airbrushed neon rim light, dense detail edge to edge, high contrast, no empty space")

CARDS = ["Craterhoof Behemoth", "Dark Ritual", "Demonic Tutor", "Birds of Paradise"]

COLOUR = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}
# What each colour should actually look like, so "black" is not read as "the colour black".
PALETTE = {"white": "ivory, gold and pale cream light",
           "blue": "deep blues and cyans", "black": "deep violet, magenta and bruised purple",
           "red": "molten orange, crimson and ember", "green": "verdant greens and moss",
           "colourless": "cold grey stone and steel"}


def scryfall(name):
    r = requests.get("https://api.scryfall.com/cards/named", params={"exact": name},
                     headers={"User-Agent": "mtg-proxy-evidence/0.2"}, timeout=30)
    r.raise_for_status()
    return r.json()


def prompt_v2(c):
    colours = [COLOUR[x] for x in (c.get("colors") or [])] or ["colourless"]
    pal = ", ".join(PALETTE[x] for x in colours)
    other = [v for k, v in PALETTE.items() if k not in colours and k != "colourless"]
    is_creature = "Creature" in c["type_line"]
    subject = (f"a single {c['type_line'].split('—')[-1].strip()} as the hero of the image, "
               "rendered large, detailed and unmistakable"
               if is_creature else
               "a dramatic moment showing this spell being cast — invent a scene with a clear "
               "central figure or event, never an empty background")

    return f"""A complete fantasy trading card, portrait orientation, full bleed.

THE ARTWORK IS THE POINT. It runs edge to edge, corner to corner, and fills the whole card.
Scene: {c['name']} — {subject}.
What is happening: {(c.get('oracle_text') or '')[:260]}
{('Mood: ' + c['flavor_text'][:160]) if c.get('flavor_text') else ''}
The upper two thirds must be a dense, detailed, dramatic illustration with a clear central
subject. Nothing may be flat, empty, or decorative filler.

COLOUR: the palette is {pal}. This is a {'/'.join(colours)} card and must read as one at a
glance. Do not let it drift towards {other[0]} or {other[1]}.

STYLE: {STYLE}

Last, and smaller than the artwork, paint the card furniture ON TOP of the illustration, so the
art continues underneath and around it:
  - a compact ornate banner across the very top carrying the card name in ornate hand-lettering:
    {c['name']}
  - a slim blank ribbon a little above the halfway line, for a type line
  - one compact blank panel across the lower quarter for rules text — no taller than a quarter
    of the card
{'  - a small blank plaque in the bottom-right corner' if is_creature else ''}
These panels must be tinted to the scene with heavy black outlines and neon rim light, like
stained glass lit from behind — never pale parchment, never plain, never larger than they need
to be. The ribbon, the panel{' and the plaque' if is_creature else ''} must be completely blank:
no letters, no numbers, no runes, no glyphs, no scribbles. The card name is the only text
anywhere on the image. No artist signature, no watermark, no initials, no date, no logo."""


def generate(prompt, label):
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
                                 "imageConfig": {"aspectRatio": "3:4", "imageSize": "2K"}}}
    t0 = time.time()
    r = requests.post(f"{API}/{PRO}:generateContent", params={"key": KEY}, json=body, timeout=420)
    res = {"label": label, "http": r.status_code, "seconds": round(time.time() - t0, 1),
           "est_usd": USD_PER_IMAGE}
    if r.status_code != 200:
        res["error"] = r.text[:500]; print(f"  FAIL {label}: {r.status_code}"); return res
    for p in r.json()["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            raw = base64.b64decode(p["inlineData"]["data"])
            ext = {"image/jpeg": "jpg", "image/png": "png"}.get(
                p["inlineData"].get("mimeType", ""), "bin")
            path = OUT / f"{label}.{ext}"; path.write_bytes(raw)
            im = Image.open(io.BytesIO(raw))
            res |= {"file": str(path), "mb": round(len(raw) / 1e6, 2), "px": f"{im.width}x{im.height}"}
    print(f"  ok   {label}  {res.get('px')}  {res['seconds']}s")
    return res


if __name__ == "__main__":
    runs = []
    for name in CARDS:
        c = scryfall(name)
        runs.append(generate(prompt_v2(c), name.lower().replace(" ", "-").replace(",", "")))
    spend = sum(r["est_usd"] for r in runs if r.get("file"))
    json.dump({"runs": runs, "est_usd_total": round(spend, 2)},
              open(OUT / "report.json", "w"), indent=2)
    print(f"\n{sum(1 for r in runs if r.get('file'))}/{len(runs)} images, ~${spend:.2f}")
