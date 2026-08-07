#!/usr/bin/env python3
"""Let the AI letter the whole card — then check its work and make it try again if it's wrong.

Hand-lettering by the model looks far better than printing a font on top: the words belong to
the drawing. The objection was always accuracy. This closes that by checking, not by trusting:

  generate -> read the finished card back with a second model -> compare against the real card
           -> if anything is wrong, generate again (up to N times)

The read-back costs a fraction of a cent against ~13c a generation, so checking every card is
cheap. What it catches, on the first run of four cards: a missing card name, a mana cost with a
pip too few, and a card rendered as a photograph of a card held in someone's hand.

Run:  python3 verify_and_retry.py
Out:  evidence-v3/final/*.jpg + evidence-v3/verify-log.json
"""
import json, pathlib, re, difflib
import evidence_v3_ai_text as g

READER = "gemini-3.6-flash"
MAX_TRIES = 3
PASS = 92                      # per-field match %, below which the card is rejected

FIELDS = {"name": "name", "type_line": "type_line", "rules_text": "oracle_text"}


def read_back(path):
    import base64, requests
    raw = base64.b64encode(path.read_bytes()).decode()
    body = {"contents": [{"parts": [
        {"inline_data": {"mime_type": "image/jpeg", "data": raw}},
        {"text": "Transcribe the text printed on this trading card exactly as it appears. Do not "
                 "correct or complete anything. If a field is not visible, use an empty string. "
                 "Reply as JSON only: {\"name\":\"\",\"type_line\":\"\",\"rules_text\":\"\","
                 "\"pt\":\"\",\"mana_symbol_count\":0,\"is_photo_of_a_card\":false} "
                 "mana_symbol_count is how many round mana symbols appear in the top corner. "
                 "is_photo_of_a_card is true if a hand, table or camera shot is visible."}]}],
        "generationConfig": {"responseMimeType": "application/json"}}
    r = requests.post(f"{g.API}/{READER}:generateContent", params={"key": g.KEY},
                      json=body, timeout=180)
    if r.status_code != 200:
        return {"error": r.text[:200]}
    try:
        return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as e:
        return {"error": str(e)}


def check(card, seen):
    """Every way this card can be wrong, with the reason spelled out."""
    fails, scores = [], {}
    for field, source in FIELDS.items():
        want = card.get(source) or ""
        scores[field] = g.score(want, seen.get(field))
        if want and scores[field] < PASS:
            fails.append(f"{field} reads {seen.get(field)!r}, expected {want!r}")
    want_pips = len(re.findall(r"\{([^}]+)\}", card.get("mana_cost") or ""))
    got_pips = seen.get("mana_symbol_count") or 0
    if want_pips and got_pips != want_pips:
        fails.append(f"mana cost shows {got_pips} symbols, expected {want_pips}")
    if card.get("power"):
        pt = f"{card['power']}/{card['toughness']}"
        if g.score(pt, seen.get("pt")) < PASS:
            fails.append(f"power/toughness reads {seen.get('pt')!r}, expected {pt!r}")
    if seen.get("is_photo_of_a_card"):
        fails.append("rendered as a photograph of a card rather than the card itself")
    return fails, scores


if __name__ == "__main__":
    out = pathlib.Path("evidence-v3/final"); out.mkdir(parents=True, exist_ok=True)
    log, spend = [], 0.0
    for name in g.CARDS:
        c = g.scryfall(name)
        slug = name.lower().replace(" ", "-").replace(",", "")
        for attempt in range(1, MAX_TRIES + 1):
            path = g.generate(g.prompt_v3(c), f"{slug}-try{attempt}")
            spend += 0.134
            if not path:
                continue
            seen = read_back(path)
            if seen.get("error"):
                print(f"       reader failed: {str(seen['error'])[:90]}"); break
            fails, scores = check(c, seen)
            log.append({"card": name, "attempt": attempt, "scores": scores,
                        "failures": fails, "file": str(path)})
            if not fails:
                path.replace(out / f"{slug}.jpg")
                print(f"       PASS on attempt {attempt}")
                break
            print(f"       reject: {'; '.join(fails)[:150]}")
    json.dump({"log": log, "est_usd": round(spend, 2)},
              open("evidence-v3/verify-log.json", "w"), indent=2)
    passed = len(list(pathlib.Path("evidence-v3/final").glob("*.jpg")))
    print(f"\n{passed}/{len(g.CARDS)} cards passed, {len(log)} generations, ~${spend:.2f}")
