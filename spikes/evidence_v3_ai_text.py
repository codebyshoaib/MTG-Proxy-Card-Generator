#!/usr/bin/env python3
"""Third test: let the AI letter the whole card, then check whether the text is correct.

Our composited text is accurate but stiff — it reads like a font dropped onto a painting, while
the client's cards read as one drawing. Their rules text is hand-lettered and the lettering
changes per card, which a font overlay cannot do. So the question is not "does it look better"
(it does) but "how often is the game text wrong".

  step 1  generate the card with every word painted by the AI
  step 2  read the rules text back off the picture, using the model as a reader
  step 3  compare that against the real card and score it

Run:  python3 evidence_v3_ai_text.py
Out:  evidence-v3/*.jpg + evidence-v3/accuracy.json
"""
import base64, difflib, io, json, pathlib, re, time
import requests
from PIL import Image

API = "https://generativelanguage.googleapis.com/v1beta/models"
KEY = next(l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("GEMINI_API_KEY"))
OUT = pathlib.Path("evidence-v3"); OUT.mkdir(exist_ok=True)
PRO, READER = "gemini-3-pro-image", "gemini-3.6-flash"

STYLE = ("toxic neon adult-cartoon illustration, bold heavy black ink outlines on every shape, "
         "acid green and violet neon glow, psychedelic slime and vapour, flat cel shading with "
         "airbrushed neon rim light, dense detail edge to edge, high contrast")

CARDS = ["Craterhoof Behemoth", "Dark Ritual", "Demonic Tutor", "Birds of Paradise"]
COLOUR = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}
PALETTE = {"white": "ivory and gold", "blue": "deep blues and cyans",
           "black": "deep violet, magenta and bruised purple",
           "red": "molten orange and crimson", "green": "verdant greens and moss",
           "colourless": "cold grey stone and steel"}


def scryfall(name):
    r = requests.get("https://api.scryfall.com/cards/named", params={"exact": name},
                     headers={"User-Agent": "mtg-proxy-evidence/0.3"}, timeout=30)
    r.raise_for_status()
    return r.json()


def spell_out(mana):
    """{5}{G}{G}{G} -> '5 generic and three green' — words the model letters more reliably."""
    return " ".join(f"[{s}]" for s in re.findall(r"\{([^}]+)\}", mana or ""))


def prompt_v3(c):
    colours = [COLOUR[x] for x in (c.get("colors") or [])] or ["colourless"]
    pal = ", ".join(PALETTE[x] for x in colours)
    is_creature = "Creature" in c["type_line"]
    rules = (c.get("oracle_text") or "").replace("\n", " / ")
    return f"""A complete fantasy trading card, portrait, full bleed, art to every edge.

Scene: {c['name']} — a dense, dramatic illustration with one clear central subject filling the
upper two thirds. What is happening: {rules[:240]}

COLOUR: the palette is {pal}. This is a {'/'.join(colours)} card and must read as one at a glance.

STYLE: {STYLE}

ALL TEXT IS PAINTED BY YOU, hand-lettered as part of the artwork, on decorative surfaces that
belong to the scene. Every word below must appear EXACTLY as written, spelled letter for letter,
with nothing added, nothing left out and nothing reworded. Make the lettering large, bold and
easy to read — it is part of the design, not a caption.

  Card name, across the top:
    {c['name']}
  Type line, on a ribbon below the artwork:
    {c['type_line']}
  Rules text, in a panel across the lower part of the card:
    {(c.get('oracle_text') or '').strip()}
  Mana cost, as round mana symbols in the top right corner:
    {spell_out(c.get('mana_cost'))}
{f"  Power and toughness, in a plaque in the bottom right corner:{chr(10)}    {c['power']}/{c['toughness']}" if is_creature else ""}

Write no other words anywhere — no runes, no invented glyphs, no flavour text, no artist
signature, no watermark, no initials, no date, no logo."""


def generate(prompt, label):
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
                                 "imageConfig": {"aspectRatio": "3:4", "imageSize": "2K"}}}
    t0 = time.time()
    r = requests.post(f"{API}/{PRO}:generateContent", params={"key": KEY}, json=body, timeout=420)
    if r.status_code != 200:
        print(f"  FAIL {label}: {r.status_code} {r.text[:200]}")
        return None
    for p in r.json()["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            raw = base64.b64decode(p["inlineData"]["data"])
            ext = {"image/jpeg": "jpg", "image/png": "png"}.get(
                p["inlineData"].get("mimeType", ""), "bin")
            path = OUT / f"{label}.{ext}"
            path.write_bytes(raw)
            print(f"  ok   {label}  {round(time.time() - t0, 1)}s")
            return path
    return None


def read_back(path):
    """Ask the model to transcribe what it can actually see on the finished card."""
    raw = base64.b64encode(path.read_bytes()).decode()
    body = {"contents": [{"parts": [
        {"inline_data": {"mime_type": "image/jpeg", "data": raw}},
        {"text": "Transcribe the text printed on this trading card, exactly as it appears, with "
                 "no correction or interpretation. Reply as JSON only: "
                 '{"name": "...", "type_line": "...", "rules_text": "...", "pt": "..."} '
                 "Use an empty string for anything not visible."}]}],
        "generationConfig": {"responseMimeType": "application/json"}}
    r = requests.post(f"{API}/{READER}:generateContent", params={"key": KEY}, json=body, timeout=180)
    if r.status_code != 200:
        return {"error": r.text[:200]}
    try:
        return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as e:
        return {"error": str(e)}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def score(expected, seen):
    return round(difflib.SequenceMatcher(None, norm(expected), norm(seen)).ratio() * 100)


if __name__ == "__main__":
    results = []
    for name in CARDS:
        c = scryfall(name)
        path = generate(prompt_v3(c), name.lower().replace(" ", "-").replace(",", ""))
        if not path:
            continue
        got = read_back(path)
        row = {"card": name, "file": str(path),
               "name_pct": score(c["name"], got.get("name")),
               "type_pct": score(c["type_line"], got.get("type_line")),
               "rules_pct": score(c.get("oracle_text"), got.get("rules_text")),
               "expected_rules": (c.get("oracle_text") or "").replace("\n", " "),
               "read_back_rules": got.get("rules_text", ""), "reader_error": got.get("error")}
        results.append(row)
        print(f"       name {row['name_pct']}%  type {row['type_pct']}%  "
              f"rules {row['rules_pct']}%")
    json.dump(results, open(OUT / "accuracy.json", "w"), indent=2)
    if results:
        avg = sum(r["rules_pct"] for r in results) / len(results)
        exact = sum(1 for r in results if r["rules_pct"] == 100)
        print(f"\nrules text: {exact}/{len(results)} exact, {avg:.0f}% average match")
