#!/usr/bin/env python3
"""Match test: can Gemini reproduce the client's own deck cards?

Unlike the first spike (one card, art only, no frame), this generates FULL CARDS in the
client's own style, for cards taken from the client's own Drive deck (SKU - HARRY-017),
so every output has a real card to sit next to.

  A1-A4  full card, four cards, two colour identities  -> does colour identity hold?
  B      Craterhoof again, second run                  -> how much does layout vary run to run?
  C      dark ritual with colour identity removed      -> the "green goblin" control

Run:  python3 evidence_gemini.py
Out:  evidence/*.png + evidence/report.json
"""
import base64, io, json, pathlib, time
import requests
from PIL import Image

API = "https://generativelanguage.googleapis.com/v1beta/models"
KEY = next(l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("GEMINI_API_KEY"))
OUT = pathlib.Path("evidence"); OUT.mkdir(exist_ok=True)

PRO = "gemini-3-pro-image"
USD_PER_IMAGE = 0.134  # list price, 2K. Unverified against the client's console.

# Read off the client's deck: heavy black ink outlines, acid green + violet neon, slime,
# glowing alien glyphs. Named franchises deliberately avoided — see the IP note in the brief.
STYLE = ("toxic neon adult-cartoon illustration, heavy black ink outlines, "
         "acid green and violet glow, psychedelic slime and vapour, glowing alien glyphs, "
         "high saturation, flat cel shading with airbrushed neon rim light")

CARDS = ["Dark Ritual", "Craterhoof Behemoth", "Birds of Paradise", "Demonic Tutor"]

COLOUR_WORDS = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}


def scryfall(name):
    r = requests.get("https://api.scryfall.com/cards/named", params={"exact": name},
                     headers={"User-Agent": "mtg-proxy-evidence/0.1"}, timeout=30)
    r.raise_for_status()
    return r.json()


def full_card_prompt(c, honour_colour=True):
    """Creative Full: the model paints art AND the decorative furniture AND the card name.
    The rules panel is left deliberately blank -- we print the real oracle text into it."""
    colours = [COLOUR_WORDS[x] for x in (c.get("colors") or [])] or ["colourless"]
    is_creature = "Creature" in c["type_line"]
    palette = (f"Palette must read as a {'/'.join(colours)} Magic card. "
               if honour_colour else
               "Palette is entirely up to the chosen art style. ")
    return (
        "A complete fantasy trading card, portrait, full bleed, art running to every edge.\n"
        f"CARD NAME, painted into the scene as ornate hand-lettering on a decorative banner "
        f"at the top: {c['name']}\n"
        f"SUBJECT: {c['type_line']}. {c.get('oracle_text', '')[:300]}\n"
        "LAYOUT the illustration must paint itself:\n"
        "  - an ornate banner across the top carrying the card name\n"
        "  - a decorative ribbon across the middle for a type line, left EMPTY\n"
        "  - a large decorative panel or scroll in the lower half for rules text, left "
        "COMPLETELY EMPTY and flat enough to print text onto\n"
        + ("  - a small plaque in the bottom right corner, left EMPTY\n" if is_creature else "")
        + "Write NO words anywhere except the card name. The ribbon and the panel must contain "
        "no letters, no runes, no glyphs — blank surfaces.\n"
        f"{palette}"
        f"STYLE: {STYLE}.\n"
        "No artist signature, no watermark, no initials, no date, no logos anywhere."
    )


def generate(prompt, label):
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
                                 "imageConfig": {"aspectRatio": "3:4", "imageSize": "2K"}}}
    t0 = time.time()
    r = requests.post(f"{API}/{PRO}:generateContent", params={"key": KEY}, json=body, timeout=420)
    res = {"label": label, "http": r.status_code, "seconds": round(time.time() - t0, 1),
           "est_usd": USD_PER_IMAGE}
    if r.status_code != 200:
        res["error"] = r.text[:500]
        print(f"  FAIL {label}: {r.status_code}")
        return res
    for p in r.json()["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            raw = base64.b64decode(p["inlineData"]["data"])
            mime = p["inlineData"].get("mimeType", "")
            ext = {"image/jpeg": "jpg", "image/png": "png"}.get(mime, "bin")
            path = OUT / f"{label}.{ext}"
            path.write_bytes(raw)
            im = Image.open(io.BytesIO(raw))
            res |= {"file": str(path), "mime": mime, "mb": round(len(raw) / 1e6, 2),
                    "px": f"{im.width}x{im.height}"}
    print(f"  ok   {label}  {res.get('px')}  {res['seconds']}s  {res.get('mb')}MB")
    return res


if __name__ == "__main__":
    runs, spend = [], 0.0
    for name in CARDS:
        c = scryfall(name)
        slug = name.lower().replace(" ", "-").replace(",", "")
        runs.append(generate(full_card_prompt(c), f"A-{slug}"))
        if name == "Craterhoof Behemoth":                      # B: run-to-run variation
            runs.append(generate(full_card_prompt(c), f"B-{slug}-run2"))
        if name == "Dark Ritual":                              # C: colour-identity control
            runs.append(generate(full_card_prompt(c, honour_colour=False),
                                 f"C-{slug}-no-colour-rule"))
    spend = sum(r["est_usd"] for r in runs if r.get("file"))
    json.dump({"runs": runs, "images": sum(1 for r in runs if r.get("file")),
               "est_usd_total": round(spend, 2)}, open(OUT / "report.json", "w"), indent=2)
    print(f"\n{sum(1 for r in runs if r.get('file'))}/{len(runs)} images, ~${spend:.2f}")
