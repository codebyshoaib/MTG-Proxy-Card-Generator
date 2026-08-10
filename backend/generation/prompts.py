"""Scryfall card data -> the brief the model paints from.

Art Only (BUILD-SPEC §2) is the whole of this file: the AI paints artwork and we composite
nothing, so the brief has exactly two jobs — say what the card is, and forbid everything
that is not art.

The colour-identity sentence is correctness, not styling (BUILD-SPEC §7): it comes from
Scryfall `color_identity`, never from the style, because purple reads as black mana and a
purple-tinted mono-green card misstates its own cost.
"""

COLOURS = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}

# A style label expands into the attributes that produce the look. MEASURED 2026-08-10 (bd
# mtg-8x6): a bare label gives a generic treatment, while the goblin brief the client approved
# named its medium, linework, palette and quality bar as separate attributes and landed the
# look first try. Six entries here because six are what the resample needs; the other 42 are a
# row each when we get to them, which is all BUILD-SPEC §10 ever claimed they were.
#
# A label that is not in this table is passed through verbatim — that is also exactly what the
# "Custom Art Style" free-text field needs, so the fallback is a feature, not a gap.
STYLES = {
    "Rick and Morty": (
        "Rick and Morty cartoon — flat bold cel colour, confident uneven black outlines, "
        "rubber-limbed exaggerated anatomy, wide bulging expressive eyes, acid-bright greens "
        "and cyans, grimy sci-fi clutter behind the subject"
    ),
    "Comic Book": (
        "hand-inked comic book illustration — heavy tapered brush inking, dense cross-hatching "
        "in the shadows, saturated flat colour laid over the ink, halftone dot texture, "
        "high-contrast dramatic lighting, collectible card artwork quality"
    ),
    "Adventure Time": (
        "Adventure Time cartoon — simple rounded shapes, thin even outlines, flat pastel-bright "
        "colour with no rendering, tiny dot eyes, soft noodly limbs, cheerful storybook "
        "landscape behind the subject"
    ),
    "Graffiti": (
        "spray-paint graffiti art — thick black outlines with a bright keyline, aerosol "
        "gradients and overspray, wildstyle energy, drips and splatter, saturated clashing "
        "fluorescents against a concrete wall"
    ),
    # MEASURED 2026-08-10: the first version of this row listed only light and mood — neon rim
    # light, wet surfaces, haze — and Counterspell came back a photoreal cinematic render, which
    # is the exact complaint the client made about the first sample batch. With no medium named
    # the model defaults to photography. Every row here leads with a medium and its linework.
    "Neon Noir": (
        "neon noir graphic-novel illustration — inked linework with heavy black spotting and "
        "flat screen-printed colour, near-black scene cut by luminous neon rim light, wet "
        "reflective surfaces, one glowing colour doing all the lighting"
    ),
    "Anime": (
        "anime illustration — clean confident linework, cel shading with hard-edged shadow "
        "shapes, large expressive eyes, saturated colour, dramatic speed lines and bloom, "
        "detailed painted background"
    ),
    "Fantasy Realistic": (
        "fully rendered digital fantasy painting — volumetric form with specular highlights and "
        "subsurface glow, painterly brushwork, no visible outlines, physically plausible "
        "materials, deep atmospheric background"
    ),
    "Dark Fantasy": (
        "fully rendered dark fantasy painting — heavy chiaroscuro with light carved out of near "
        "black, volumetric form, glowing molten and ember accents, painterly brushwork, grim "
        "atmospheric depth"
    ),
}

# Applied to EVERY brief regardless of style. MEASURED 2026-08-10 against the reference site's
# own output (scratchpad compare_art.jpg, cards pulled from tcggenerator.com/explore at
# 1792x2400 — the same canvas we generate on, so the gap was never the model):
#
# Every card of theirs, in every style, has one dominant subject filling the frame, hard
# directional light, haze separating the planes, and a desaturated background that makes the
# card's colour read hot. None of that is a style name, which is why naming only a style gave us
# flat art — Lightning Bolt under "Graffiti" came back a wall with no subject on it at all.
#
# Deliberately says nothing about medium or realism, so it lifts a flat cartoon without
# contradicting it: the client's own Rick and Morty cards are dense, glowing and high-contrast.
QUALITY = (
    "Quality bar, whatever the style: ONE dominant subject, large in frame, with a silhouette "
    "that reads instantly. Light it hard and from a decided direction — rim light, glow, shafts "
    "through the air. Separate foreground from background with haze, smoke or depth of field. "
    "Keep the background quieter and less saturated than the subject so the card's colour reads "
    "hot against it. Dense detail where the eye lands. Finished collectible-card artwork, not a "
    "sketch and not an empty backdrop."
)

# Named individually because the model treats them as separate things: it will happily
# obey "no text" and still paint an empty title banner. Every item here is one that a
# generation actually produced (handover §7, bd mtg-z12, mtg-gni).
FORBIDDEN = (
    "no text, no lettering, no title, no numbers, no mana symbols, no set symbol, "
    "no border, no frame, no panel, no box, no banner, no plaque, no scroll, "
    "no signature, no watermark, no card furniture of any kind"
)


def _subject(face, licensed):
    """The line that says what the picture is of.

    On a card that exists only as a licensed crossover, the proper noun is the whole
    problem. MEASURED 2026-08-09: "Hulk, Bruce Banner" is refused with PROHIBITED_CONTENT
    with the art attached AND without it, while the same card's type line — "Legendary
    Creature — Gamma Berserker Hero", trample, mono-red — generates first try.

    That is not the refusal evaded, it is a different and smaller thing asked for: the
    card's game identity, which is ours to draw, instead of a studio's character, which is
    not. The subtypes are already a character description, so the card loses nothing
    mechanical — same types, same colour, same keywords.
    """
    if not licensed:
        return f"Name: {face['name']}"
    types, dash, subtypes = face["type_line"].partition("—")
    if dash and subtypes.strip():
        legendary = "legendary " if "Legendary" in types else ""
        return f"Subject: a {legendary}{subtypes.strip().lower()}"
    return f"Subject: a {types.strip().lower()}"


def _scrub(text, name):
    """Rules text with a licensed character's name replaced by what it refers to.

    Legendary cards template their own name into their abilities — "Whenever Hulk attacks"
    — so the name survives in the rules text after the Name line is gone, and one occurrence
    is enough to be refused.
    """
    for token in (name, name.split(",")[0].strip()):
        text = text.replace(token, "this creature")
    return text


def _palette(color_identity):
    """Colour identity as the light on the scene, not as paint on the subject.

    MEASURED 2026-08-10 (bd mtg-roq, mtg-prs): "must read as <colour> and nothing else" is
    obeyed literally and repaints the subject. Mono-white Frodo came back greyscale, and
    mono-red Raphael came back a red turtle — Raphael is green.

    But stating it positively as "a luminous red palette in the light, the atmosphere, the ground
    and the accents" over-corrects into the opposite failure. MEASURED 2026-08-10 against four
    reference-site cards of the same names: mean HSV saturation was 195-199 for ours against
    91-133 for theirs, on every card, because that wording tints everything. A red dragon on red
    rock in red haze has no silhouette left.

    The reference site follows the actual Magic convention: the mana colour is EMISSIVE — lava,
    fire, glow, rim light — sitting in a scene whose surfaces stay neutral. Grey stone next to
    orange lava is what makes the orange read hot. So the colour is assigned to the light, and
    surfaces are told to keep their own natural colour.

    The purple ban stays absolute. It is the client's reported bug and the one place where
    "must not appear" is the right strength rather than an over-constraint (BUILD-SPEC §7).
    """
    if not color_identity:
        return (
            "Light this scene as a colourless card — greys, metals, stone. Keep each thing "
            "its own natural colour; do not repaint the subject to match. No one mana colour "
            "may dominate the picture."
        )
    names = " and ".join(COLOURS[c] for c in color_identity if c in COLOURS)
    return (
        f"This card's colour identity is {names}. The {names} belongs to the LIGHT — glows, "
        f"flames, energy, rim light, the hot spots the eye goes to. Surfaces and environment "
        "keep their own natural, largely neutral colour: stone stays grey, steel stays steel, "
        "bone stays bone, smoke stays grey. Do not tint the whole picture one hue and do not "
        f"drain it to monochrome — the {names} must read as the brightest thing in a mostly "
        "neutral scene, which is what makes it read hot. No other mana colour may dominate, "
        "and purple in particular must not appear unless the card is black, because purple "
        "reads as black mana."
    )


def creative_full(face, style=None, reference=True, licensed=False, direction=None, palette=None):
    """The Creative Full brief: art AND the card's furniture, with every panel left EMPTY.

    This is the inversion of Art Only. There, painted furniture is the defect `FORBIDDEN` exists
    to suppress; here it is the deliverable, and lettering is the defect.

    Why this shape rather than the two obvious ones (bd mtg-yp3, mtg-9pi):

    - Letting the model write the text scores 1/3. Swords to Plowshares printed
      "Instant — <runic script>" — a fabricated subtype, right font, right place. Invisible.
    - A fixed frame asset over a fixed art window scores 0/3 and looks like art in a box.
    - The reference site does neither. Across 24 gallery cards, with one card appearing ~10
      times, the painted panels land anywhere from y≈0.20 to y≈0.85 — full width, narrow float,
      sometimes two — while the text is always uniform serif with identical wording. They paint
      the furniture per card and fit composited text into whatever came back.

    So we ask for empty furniture and composite into it. The model already wants to do this: the
    `FORBIDDEN` comment records that it paints empty banners even when told not to.
    """
    # MEASURED 2026-08-10: given the name and the rules text, the model paints them. Atraxa came
    # back fully lettered — its own name in the top plate, "Legendary Phyrexian Angel Horror" in
    # the strip, mana symbols, a Phyrexian watermark — and Terror printed a literal "P/T".
    #
    # So Creative Full is briefed the way a licensed crossover is: subject from the type line, no
    # proper noun, and the rules text never shown at all — only its LENGTH, which is the single
    # thing the model needs in order to size the slab. You cannot paint text you were never given.
    # The attached official art carries the likeness, so nothing is lost by withholding the name.
    lines = [
        "You are a senior Magic: The Gathering card artist.",
        "",
        "Paint a COMPLETE fantasy trading card face — the artwork and the card's raised surfaces "
        "together, as one integrated illustration, with NO writing anywhere on it.",
        "",
        "The card:",
        _subject(face, licensed=True),
    ]
    if face.get("oracle_text"):
        lines.append(
            f"Leave room for about {len(face['oracle_text'])} characters of text in the lower "
            "slab — size it to hold that comfortably and no larger."
        )
    lines += ["", _palette(face.get("color_identity") or [])]

    if reference:
        lines += [
            "",
            "The attached image is the card's official artwork. Take from it ONLY what is "
            "depicted — who or what is in it, and what they are doing. Take nothing of how it "
            "is drawn. Where the reference and the art style disagree, the art style wins.",
        ]
    if style:
        lines += [
            "",
            f"Art style: {STYLES.get(style, style)}. This governs the whole picture — the "
            "furniture as much as the art.",
        ]
    if direction:
        lines += ["", f"Composition: {direction}."]
    if palette:
        lines += ["", f"Colour treatment: {palette}, within the colour identity above."]

    # Described as SHAPES, never as fields. "Title banner" and "plaque for power/toughness" are
    # invitations: a banner carries a title, so the model wrote one. A ledge is just a ledge.
    furniture = [
        "a raised horizontal ledge across the very top, no taller than 1/10th of the card",
        "a NARROW horizontal strip lower down, about 1/16th of the card's height, sitting "
        "directly on top of the broad slab below it. Do not omit this piece",
        "a broad rectangular slab across the lower third",
    ]
    if face.get("power") is not None:
        furniture.append(
            "a small shield-shaped boss overlapping the slab's bottom-right corner"
        )
    lines += [
        "",
        "The raised surfaces, and they are the point of the card:",
        "Build them out of the SAME MATERIAL as the art — if the scene is lava and obsidian they "
        "are cracked obsidian veined with lava; if it is a forest they are living wood and vine. "
        "They must look carved out of the world, never like a border laid on top of a picture. "
        "Let the art bleed past and behind them.",
        f"Paint exactly these {len(furniture)} raised surfaces and no others: "
        + "; ".join(furniture)
        + ".",
        "",
        # MEASURED 2026-08-10, first three generations: the slab came back eating ~40% of the card
        # on all three and the narrow strip was omitted on all three. The art has to be told it
        # outranks the furniture.
        "THE ARTWORK DOMINATES THE CARD. It is a full-bleed painting covering the entire canvas "
        "and the raised surfaces sit on top of it. All of them together may cover no more than a "
        "third of the card's height — the lower slab is a BAND across the lower third, never half "
        "the card.",
        "No raised surface may cover the subject's head, face or silhouette.",
        "Each surface must be quiet enough to read text on: low contrast, low detail, no busy "
        "texture and no bright hotspot inside it. Quiet, not blank — let the material and its "
        "lighting continue across it rather than leaving a flat empty rectangle.",
        "",
        QUALITY,
        "",
        "Put the subject's face and focal point in the UPPER-MIDDLE of the card, clear of the "
        "lower slab. Nothing that matters may sit in the lower third.",
        "Keep every raised surface and every important detail inside the middle 92% of the "
        "canvas — the outer edge is trimmed off when the card is cut.",
        "Output ONE image filling the entire frame, edge to edge.",
        "",
        # Last, deliberately. Stated earlier in the brief it lost to the furniture description on
        # 2 of 3 cards; the ban has to be the final thing read.
        "ABSOLUTE REQUIREMENT, overriding everything above: there is NO WRITING ANYWHERE ON THIS "
        "IMAGE. Every raised surface is bare stone, bare wood, bare metal — blank. No letters, no "
        "words, no names, no titles, no numbers, no runes, no glyphs, no decorative script, no "
        "fake writing, no watermark, no emblem, no mana symbols, no set symbol. If you are "
        "tempted to label a surface, leave it empty instead. Real text is printed onto these "
        "surfaces afterwards and anything you paint on them will collide with it.",
    ]
    return "\n".join(lines)


def art_only(face, style=None, reference=True, licensed=False, direction=None, palette=None):
    """The Art Only brief for one face (`cards.scryfall.faces()` produces the face).

    `style` is the user's chosen look. A label in `STYLES` expands into its attributes; anything
    else passes through verbatim, which is what the "Custom Art Style" free-text field needs.

    `direction` and `palette` are the other two option groups the reference site ships and we
    had not wired up at all — Art Direction (21) and Colour Palette (20), BUILD-SPEC §10. Both
    are prompt text like the styles. They are what produces the reference site's composition:
    "Dynamic", "Cinematic" and "Epic" are the difference between a subject and a backdrop.

    `reference` says whether the caller is attaching the official art. It is the caller's
    call and not the face's, because `scryfall.art_reference()` withholds the attachment on
    a crossover-only card — and a brief that describes an attachment that is not there sends
    the model looking for an image it cannot see.

    `licensed` says the card exists ONLY as a licensed crossover, so its name belongs to a
    studio rather than to Magic. See `_subject()` for what that changes and why.
    """
    lines = [
        "You are a senior Magic: The Gathering card artist.",
        "",
        "Paint the artwork for this card:",
        _subject(face, licensed),
        f"Type: {face['type_line']}",
    ]
    if face.get("oracle_text"):
        text = face["oracle_text"]
        lines.append(f"Rules text: {_scrub(text, face['name']) if licensed else text}")
    # Flavour text is dropped entirely on a licensed card rather than scrubbed: it is the
    # character's own voice ("Hulk smash!") and nothing survives taking the name out of it.
    if face.get("flavor_text") and not licensed:
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
            f"Art style: {STYLES.get(style, style)}. This governs the whole picture — the "
            "world it is set in, the light, the palette and the finish.",
        ]
    if direction:
        lines += ["", f"Composition: {direction}."]
    if palette:
        lines += ["", f"Colour treatment: {palette}, within the colour identity above."]

    lines += [
        "",
        QUALITY,
        "",
        "Output ONE full-bleed illustration that fills the entire frame, edge to edge, "
        "with the subject clear of the edges.",
        f"Paint the art and nothing else: {FORBIDDEN}.",
    ]
    return "\n".join(lines)
