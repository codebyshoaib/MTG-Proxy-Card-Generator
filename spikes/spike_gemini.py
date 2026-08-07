#!/usr/bin/env python3
"""Week-one spike: can Gemini image models actually do MTG card art?

Answers, with evidence, the four things the onboarding response left open:
  T1  Does this key have image-gen access at all (risk 4: no free tier)?
  T2  Text-to-image from Scryfall card data -> usable art? (the committed approach)
  T3  Original card art as a style reference -> does the model accept it? (risk 9, "untested")
  T4  Aspect ratio / resolution control -> can we get an art-box-shaped image at print DPI?

Run:  python3 spike_gemini.py            # all tests
      python3 spike_gemini.py t3         # one test
Output: spike-out/*.png + spike-out/report.json
"""
import base64, io, json, pathlib, sys, time
import requests
from PIL import Image

API = "https://generativelanguage.googleapis.com/v1beta/models"
KEY = next(l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("GEMINI_API_KEY"))
OUT = pathlib.Path("spike-out"); OUT.mkdir(exist_ok=True)

PRO = "gemini-3-pro-image"        # "Nano Banana Pro" — what the proposal names
FLASH = "gemini-2.5-flash-image"  # cheap tier, for the margin comparison

# ponytail: list prices, unverified against the client's billing account. Confirm in the console
# before any credit pricing goes in the quote — this only exists to keep the spike's spend visible.
PRICE_PER_IMAGE = {(PRO, "4K"): 0.24, (PRO, None): 0.134, (FLASH, None): 0.039}

# One card from the five test cards: red, standard layout, 370 chars oracle. Baseline case.
CARD = "Warp World"

STYLE = ("hand-painted dark fantasy oil painting, visible brush texture, "
         "dramatic rim lighting, muted earthy palette with ember highlights")


def scryfall(name):
    r = requests.get("https://api.scryfall.com/cards/named", params={"exact": name},
                     headers={"User-Agent": "mtg-proxy-spike/0.1", "Accept": "*/*"}, timeout=30)
    r.raise_for_status()
    return r.json()


def prompt_from_card(c):
    """The prompt composer, minimum version: card data in, art brief out."""
    return (
        f"Fantasy trading card illustration. No text, no border, no frame, no logos, "
        f"no card layout — artwork only, filling the whole image.\n"
        f"Subject: {c['name']} — {c['type_line']}.\n"
        f"Scene: {c.get('oracle_text', '')[:400]}\n"
        f"Colour identity: {'/'.join(c.get('colors') or ['colourless'])} "
        f"(let the palette read as this colour).\n"
        f"Style: {STYLE}."
    )


def save(raw, label, mime):
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(mime, "bin")
    path = OUT / f"{label}.{ext}"
    path.write_bytes(raw)
    im = Image.open(io.BytesIO(raw))
    return {"file": str(path), "mime": mime, "kb": len(raw) // 1024,
            "px": f"{im.width}x{im.height}", "dpi_at_art_box": round(im.width / 2.1)}


def generate(model, parts, image_cfg=None, label="out"):
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
    if image_cfg:
        body["generationConfig"]["imageConfig"] = image_cfg
    t0 = time.time()
    r = requests.post(f"{API}/{model}:generateContent", params={"key": KEY},
                      json=body, timeout=300)
    dt = round(time.time() - t0, 1)
    res = {"model": model, "label": label, "http": r.status_code, "seconds": dt,
           "image_config": image_cfg}
    if r.status_code != 200:
        res["error"] = r.text[:600]
        return res
    d = r.json()
    res["usage"] = d.get("usageMetadata", {})
    size = (image_cfg or {}).get("imageSize")
    res["est_usd"] = PRICE_PER_IMAGE.get((model, size)) or PRICE_PER_IMAGE.get((model, None))
    for p in d["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            res.update(save(base64.b64decode(p["inlineData"]["data"]), label,
                            p["inlineData"].get("mimeType", "")))
        elif p.get("text", "").strip():
            res["model_text"] = p["text"].strip()[:400]
    res["got_image"] = "file" in res
    if not res["got_image"]:
        res["error"] = "200 but no image — " + json.dumps(d.get("candidates", [{}])[0].get("finishReason"))
    return res


def img_part(raw, mime="image/jpeg"):
    return {"inlineData": {"mimeType": mime, "data": base64.b64encode(raw).decode()}}


# ---------------- tests ----------------

def t1():
    """Access / billing. Cheapest possible call on both models."""
    return [generate(m, [{"text": "A single red maple leaf on white. Minimal."}],
                     label=f"t1-access-{m}") for m in (PRO, FLASH)]


def t2(card):
    """Committed approach: art from card data alone. Run on both models for cost/quality."""
    p = prompt_from_card(card)
    (OUT / "t2-prompt.txt").write_text(p)
    return [generate(m, [{"text": p}], {"aspectRatio": "4:3", "imageSize": "2K"},
                     label=f"t2-textonly-{m}") for m in (PRO, FLASH)]


def t3(card):
    """Risk 9: send the real Scryfall art as a style/composition reference."""
    art_url = card["image_uris"]["art_crop"]
    # Scryfall's image CDN 400s without a User-Agent — silently returns an HTML error page.
    ir = requests.get(art_url, headers={"User-Agent": "mtg-proxy-spike/0.1"}, timeout=60)
    ir.raise_for_status()
    raw = ir.content
    assert raw[:3] == b"\xff\xd8\xff", f"reference art is not JPEG: {raw[:40]!r}"
    (OUT / "t3-reference-input.jpg").write_bytes(raw)
    out = []
    # 3a: reinterpret the existing composition in our style
    out.append(generate(PRO, [
        img_part(raw),
        {"text": f"Reinterpret this artwork as a new original illustration in a different style. "
                 f"Keep the composition, subject and mood; change the rendering completely.\n"
                 f"Style: {STYLE}.\nNo text, no frame, artwork only."}],
        {"aspectRatio": "4:3", "imageSize": "2K"}, label="t3a-restyle-composition"))
    # 3b: use it only as a palette/mood reference for a prompt-built scene
    out.append(generate(PRO, [
        img_part(raw),
        {"text": "Use the attached image ONLY as a colour-and-mood reference. Do not copy its "
                 "composition.\n" + prompt_from_card(card)}],
        {"aspectRatio": "4:3", "imageSize": "2K"}, label="t3b-mood-reference-only"))
    return out


def t4(card):
    """Resolution / ratio control. Is a 2K art box enough for 300 DPI, and is 4K honoured?"""
    p = prompt_from_card(card)
    return [generate(PRO, [{"text": p}], cfg, label=f"t4-{cfg['aspectRatio'].replace(':','x')}-{cfg['imageSize']}")
            for cfg in ({"aspectRatio": "4:3", "imageSize": "1K"},
                        {"aspectRatio": "4:3", "imageSize": "4K"},
                        {"aspectRatio": "5:4", "imageSize": "2K"})]


def t5(card):
    """Can a negative instruction suppress the fake artist signature T3 produced?"""
    raw = (OUT / "t3-reference-input.jpg").read_bytes()
    return [generate(PRO, [
        img_part(raw),
        {"text": "Use the attached image ONLY as a colour-and-mood reference. Do not copy its "
                 "composition.\n" + prompt_from_card(card) +
                 "\nCRITICAL: no artist signature, no watermark, no initials, no date, no text "
                 "anywhere in the image. Corners and edges must be clean painting only."}],
        {"aspectRatio": "4:3", "imageSize": "2K"}, label="t5-no-signature")]


if __name__ == "__main__":
    which = set(sys.argv[1:]) or {"t1", "t2", "t3", "t4", "t5"}
    card = scryfall(CARD)
    print(f"card: {card['name']} | {card['type_line']} | colors={card.get('colors')}")
    rp = OUT / "report.json"   # merge, so partial runs don't clobber earlier results
    report = json.loads(rp.read_text()) if rp.exists() else {"card": CARD, "tests": {}}
    for name, fn in (("t1", t1), ("t2", lambda: t2(card)), ("t3", lambda: t3(card)),
                     ("t4", lambda: t4(card)), ("t5", lambda: t5(card))):
        if name not in which:
            continue
        print(f"\n=== {name} {fn.__doc__ or ''}")
        rows = fn()
        report["tests"][name] = rows
        for r in rows:
            ok = "OK " if r.get("got_image") else "FAIL"
            print(f"  {ok} {r['label']:34s} http={r['http']} {r['seconds']:>5}s "
                  f"{r.get('px','-'):>10} {r.get('kb','-')}kb"
                  + (f"\n       {r.get('error','')[:300]}" if r.get("error") else ""))
    rp.write_text(json.dumps(report, indent=2))
    got = [r for rows in report["tests"].values() for r in rows]
    print(f"\n{sum(r.get('got_image', False) for r in got)}/{len(got)} images, "
          f"est ${sum(r.get('est_usd') or 0 for r in got):.2f} -> spike-out/report.json")
