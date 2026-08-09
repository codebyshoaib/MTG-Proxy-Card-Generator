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


def art_only(face, style=None):
    """The Art Only brief for one face (`cards.scryfall.faces()` produces the face).

    `style` is the user's chosen look, passed through verbatim. Omitted, the model is left
    to pick a treatment that suits the card.
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

    if face.get("art_crop"):
        lines += [
            "",
            "The attached image is the card's official artwork. Keep the subject, the "
            "action and the setting recognisably the same card — reinterpret it, do not "
            "replace it.",
        ]
    if style:
        lines += ["", f"Art style: {style}"]

    lines += [
        "",
        "Output ONE full-bleed illustration that fills the entire frame, edge to edge, "
        "with the subject clear of the edges.",
        f"Paint the art and nothing else: {FORBIDDEN}.",
    ]
    return "\n".join(lines)
