"""Scryfall card data -> the brief the model paints from.

Art Only (BUILD-SPEC §2) is the whole of this file: the AI paints artwork and we composite
nothing, so the brief has exactly two jobs — say what the card is, and forbid everything
that is not art.

The colour-identity sentence is correctness, not styling (BUILD-SPEC §7): it comes from
Scryfall `color_identity`, never from the style, because purple reads as black mana and a
purple-tinted mono-green card misstates its own cost.
"""

COLOURS = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}

# Named individually because the model treats them as separate things: it will happily
# obey "no text" and still paint an empty title banner. Every item here is one that a
# generation actually produced (handover §7, bd mtg-z12, mtg-gni).
FORBIDDEN = (
    "no text, no lettering, no title, no numbers, no mana symbols, no set symbol, "
    "no border, no frame, no panel, no box, no banner, no plaque, no scroll, "
    "no signature, no watermark, no card furniture of any kind"
)


def _palette(color_identity):
    if not color_identity:
        return (
            "This is a colourless card. The palette must read as colourless — greys, "
            "metals, stone. Do not let any one mana colour dominate."
        )
    names = [COLOURS[c] for c in color_identity if c in COLOURS]
    return (
        f"This card's colour identity is {' and '.join(names)}. The palette must read as "
        f"{' and '.join(names)} and nothing else — no other mana colour may dominate, and "
        "purple in particular is forbidden unless the card is black, because purple reads "
        "as black mana."
    )


def art_only(face, style=None, reference=True):
    """The Art Only brief for one face (`cards.scryfall.faces()` produces the face).

    `style` is the user's chosen look, passed through verbatim. Omitted, the model is left
    to pick a treatment that suits the card.

    `reference` says whether the caller is attaching the official art. It is the caller's
    call and not the face's, because `scryfall.art_reference()` withholds the attachment on
    a crossover-only card — and a brief that describes an attachment that is not there sends
    the model looking for an image it cannot see.
    """
    lines = [
        "You are a senior Magic: The Gathering card artist.",
        "",
        "Paint the artwork for this card:",
        f"Name: {face['name']}",
        f"Type: {face['type_line']}",
    ]
    if face.get("oracle_text"):
        lines.append(f"Rules text: {face['oracle_text']}")
    if face.get("flavor_text"):
        lines.append(f"Flavour text: {face['flavor_text']}")
    lines += ["", _palette(face.get("color_identity") or [])]

    if reference:
        lines += [
            "",
            "The attached image is the card's official artwork. Take from it ONLY what is "
            "depicted — who or what is in it, and what they are doing. Take nothing of how "
            "it is drawn: not its palette, not its lighting, not its period, not its level "
            "of realism, not its setting. Where the reference and the art style disagree, "
            "the art style wins.",
        ]
    if style:
        lines += [
            "",
            f"Art style: {style}. This governs the whole picture — the world it is set in, "
            "the light, the palette and the finish.",
        ]

    lines += [
        "",
        "Output ONE full-bleed illustration that fills the entire frame, edge to edge, "
        "with the subject clear of the edges.",
        f"Paint the art and nothing else: {FORBIDDEN}.",
    ]
    return "\n".join(lines)
