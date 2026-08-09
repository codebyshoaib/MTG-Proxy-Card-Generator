"""Decklist -> Scryfall card objects -> the faces we actually generate and composite.

Everything the renderer needs comes from one Scryfall card object (BUILD-SPEC §15), so this
is the front of the pipeline: the prompt builder reads `color_identity` and `name` from a
face here, the compositor reads `type_line`, `oracle_text`, `mana_cost`, `power`,
`toughness` and `loyalty`, and the verify loop compares the finished card back against it.

Two rules here are correctness, not style:

- **A `card_faces[]` array does not mean two-sided.** `split`, `adventure`, `flip` and
  `room` all carry one and are a single physical card, one image, one generation. Only the
  layouts in TWO_SIDED become two records and two generations.
- **Unsupported layouts are rejected here, before any AI call**, so no credit is spent
  (BUILD-SPEC §9, §12.1). A layout we cannot render must surface at resolve time, never as
  a wrong card at the end of a paid job.
"""

import re
import time

import requests
from django.db.models import Q

from .models import Card

API = "https://api.scryfall.com"
# Scryfall requires an identifying User-Agent: without one, /symbology returned a body with
# no 'data' key rather than an error. Same header everywhere we touch the API.
HEADERS = {"User-Agent": "mtg-proxy-generator/0.1", "Accept": "*/*"}
DELAY = 0.1
BATCH = 75  # /cards/collection's documented maximum. A 100-card deck is 2 requests.

TWO_SIDED = {"transform", "modal_dfc", "double_faced_token", "reversible_card"}
"""Layouts that are two physical sides: two faces, two generations, two credits.

`meld` is deliberately absent. A meld card is single-faced in the hand; the melded back is a
separate Scryfall object reached through `all_parts`, which is what makes the pair cost 3.
That pairing is its own piece of work — until it exists, a meld front resolves as an
ordinary single-faced card, which is what it is.
"""

UNSUPPORTED = {"planar", "scheme", "vanguard", "art_series", "emblem", "augment", "host"}
"""Not deck cards (BUILD-SPEC §9). Rejected before generation, so they cost nothing."""

SECTIONS = {"deck", "sideboard", "commander", "companion", "maybeboard", "tokens"}

UB = "universesbeyond"
"""`promo_types` marks a licensed crossover printing per card, not per set.

`Sol Ring` and `Lightning Bolt` both came back from Marvel Super Heroes Commander, and only
the ones carrying this are actually reskinned — which is why the set is not the test.
"""

_LINE = re.compile(
    r"""^
    (?:(?P<qty>\d+)\s*[xX]?\s+)?     # "4 ", "4x ", or nothing
    (?P<name>.+?)                    # the name, shortest that lets the rest match
    (?:\s+\([^)]+\).*)?              # " (MH1) 149", " (MH1) 149 *F*"
    $""",
    re.VERBOSE,
)


def parse_decklist(text):
    """[(quantity, name), ...] in decklist order.

    Accepts what the common exporters emit: "4 Lightning Bolt", "4x Lightning Bolt",
    "1 Craterhoof Behemoth (MH1) 149", a bare name, section headers and comments.
    """
    entries = []
    for raw in text.splitlines():
        line = raw.strip()
        # '//' opens a comment only at the start of a line — it is also the separator
        # inside a card's own name, and "Fire // Ice" is a decklist entry.
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if line.lower().rstrip(":") in SECTIONS:
            continue
        m = _LINE.match(line)
        if m:
            entries.append((int(m["qty"] or 1), m["name"].strip()))
    return entries


def _front(name):
    """The front-face name, which is the only one /cards/collection will match.

    MEASURED 2026-08-07, and it is not in the docs. `/cards/named?exact=Fire // Ice`
    resolves, but the same string as a collection identifier lands in `not_found` — and so
    does "Bonecrusher Giant // Stomp" and "Turntimber Symbiosis // Turntimber, Serpentine
    Wood". Every real exporter (Moxfield, Archidekt, MTGGoldfish) writes the full name, so
    without this every DFC, split and adventure card in an imported decklist fails to
    resolve — precisely the layouts that are priority 1 in the build sequence.
    """
    return name.split(" // ")[0].strip()


def _cached(name):
    """The cached Card for a name as the user wrote it, or None.

    The istartswith arm is what lets "Turntimber Symbiosis" hit a row whose Scryfall name is
    "Turntimber Symbiosis // Turntimber, Serpentine Wood" — decklists name the front face.
    """
    # ponytail: a back-face-only name misses the cache and refetches. Scryfall resolves it
    # anyway, so the cost is one request, never a wrong card. Add a name-alias table if
    # deck imports turn out to write back faces.
    return Card.objects.filter(
        Q(name__iexact=name) | Q(name__istartswith=f"{name} // ")
    ).first()


def _store(data):
    Card.objects.update_or_create(
        scryfall_id=data["id"],
        defaults={"name": data["name"], "layout": data["layout"], "data": data},
    )


def resolve(names):
    """Resolve card names to cached Cards. Returns (found, not_found).

    `found` is keyed by the name as asked, so the caller can match results back to its own
    decklist lines. `not_found` is returned rather than dropped: a name Scryfall does not
    know must surface to the user, not silently shrink their deck.
    """
    found, misses = {}, []
    for name in dict.fromkeys(names):  # de-duped, order preserved
        card = _cached(name)
        if card:
            found[name] = card
        else:
            misses.append(name)

    not_found = []
    for i in range(0, len(misses), BATCH):
        chunk = misses[i : i + BATCH]
        if i:
            time.sleep(DELAY)
        response = requests.post(
            f"{API}/cards/collection",
            json={"identifiers": [{"name": _front(n)} for n in chunk]},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        for data in response.json()["data"]:
            _store(data)
        # Re-read through the cache instead of trusting the response order or its
        # `not_found` echo: the same name-matching rule then decides both paths.
        for name in chunk:
            card = _cached(name)
            if card:
                found[name] = card
            else:
                not_found.append(name)
    return found, not_found


def _pick(face, data, key, default=None):
    """A face's value for `key`, falling back to the card's.

    Scryfall keeps shared values at the top level and omits them from the face, and on a DFC
    the reverse is true for the printed ones — top-level `oracle_text` is absent entirely
    and `type_line` is the two faces joined with "//".
    """
    if key in face:
        return face[key]
    return data.get(key, default)


def _face(data, face, position):
    """One face flattened to the fields the prompt builder and the compositor read."""
    face = face or {}
    images = face.get("image_uris") or data.get("image_uris") or {}
    return {
        "scryfall_id": data["id"],
        "face_position": position,
        "is_dfc": position != "SINGLE",
        "layout": data["layout"],
        # The AI paints this, and only this. Note that on a split or adventure card it is
        # the joined "Fire // Ice", which is NOT what is printed on either half — the
        # prompt builder must letter the halves from `parts`, not paint this string.
        "name": _pick(face, data, "name"),
        "display_name": data["name"],  # "Front // Back" — what the UI labels the pair
        "mana_cost": _pick(face, data, "mana_cost", ""),
        "type_line": _pick(face, data, "type_line", ""),
        "oracle_text": _pick(face, data, "oracle_text", ""),
        "flavor_text": _pick(face, data, "flavor_text", ""),
        "power": _pick(face, data, "power"),
        "toughness": _pick(face, data, "toughness"),
        "loyalty": _pick(face, data, "loyalty"),
        "colors": _pick(face, data, "colors", []),
        # Top level ONLY, never the face's own. This fallback is required, not defensive:
        # "Turntimber, Serpentine Wood" is a Land back face with colors:[] on a green card,
        # and taking the face's colours renders it colourless and breaks the pair
        # (BUILD-SPEC §9.2). Colour identity is the card's, not the side's.
        "color_identity": data.get("color_identity", []),
        "art_crop": images.get("art_crop"),
        # Whether the art above is a licensed crossover rather than the card's own.
        # `art_reference()` is what acts on it; see the measurement in its docstring.
        "is_crossover": UB in (data.get("promo_types") or []),
        # Both halves of a split/adventure/room, which print on this one face. None when
        # the card has no halves, and unused on a two-sided card where each side is its own
        # face record.
        "parts": data.get("card_faces") if position == "SINGLE" else None,
    }


def faces(card):
    """The faces to generate for a card: two for a two-sided card, one for anything else.

    This is the generation plan for one decklist line, and therefore what credits are
    counted from — one credit per face, per BUILD-SPEC §12.1.
    """
    return _faces(card.data)


def _faces(data):
    if data["layout"] in TWO_SIDED:
        return [
            _face(data, f, position)
            for f, position in zip(data["card_faces"], ("FRONT", "BACK"))
        ]
    return [_face(data, None, "SINGLE")]


def art_reference(face):
    """The art to show the model as this card's own artwork, or None to show it nothing.

    `/cards/collection` answers a bare name with the newest printing, and since June 2026
    that is a licensed crossover for a lot of staples. MEASURED 2026-08-09: `Lightning Bolt`
    resolved to Marvel Super Heroes Commander, whose art is Thor — the image model refuses
    it outright with `PROHIBITED_CONTENT`, so the card cannot be generated at all — and
    `Swords to Plowshares` resolved to the same set and quietly painted Hawkeye's farm under
    a dark-fantasy brief. Both look like prompt failures and neither is one.

    A crossover is a skin, not the card's identity, so we ask for the oldest printing that
    is not one. Lightning Bolt then gets Christopher Rush's Alpha bolt, which is what the
    proposal means by "the recognizable identity of the original card".

    One request, and only for the cards that need it — the batch resolve is untouched.
    """
    if not face["is_crossover"]:
        return face["art_crop"]

    time.sleep(DELAY)
    response = requests.get(
        f"{API}/cards/search",
        params={
            "q": f'!"{face["display_name"]}" not:ub game:paper',
            "order": "released",
            "dir": "asc",
            "unique": "art",
        },
        headers=HEADERS,
        timeout=30,
    )
    # 404 is Scryfall's empty result: the card exists ONLY as a crossover, so there is no
    # earlier art to fall back to. Send no reference rather than the one we know is refused
    # — the brief still carries the card's own text, which generates fine.
    if response.status_code == 404:
        return None
    response.raise_for_status()

    for candidate in _faces(response.json()["data"][0]):
        if candidate["face_position"] == face["face_position"]:
            return candidate["art_crop"]
    return None


def resolve_decklist(text):
    """Parse and resolve a decklist into a generation plan.

    Returns {"entries", "unresolved", "unsupported"}. `entries` are the cards we will
    generate, each with its quantity and its faces. The other two are reported so the
    confirm screen can show them: neither costs a credit, because neither reaches the AI.
    """
    lines = parse_decklist(text)
    found, not_found = resolve([name for _, name in lines])

    entries, unsupported = [], []
    for quantity, name in lines:
        card = found.get(name)
        if card is None:
            continue
        if card.layout in UNSUPPORTED:
            unsupported.append({"name": name, "layout": card.layout})
            continue
        entries.append({"quantity": quantity, "card": card, "faces": faces(card)})

    return {"entries": entries, "unresolved": not_found, "unsupported": unsupported}
