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


def _palette(color_identity, strict=False):
    """Colour identity as the light on the scene, not as paint on the subject.

    `strict` names each of the five colours in the ban rather than saying "no one mana colour
    may dominate". It is on for Creative Full and off for Art Only, and the split is forced by
    what the two modes can survive. In Creative Full the edge material and the plates are built
    out of the scene, so a warm scene tints the furniture too and the miss doubles: Sol Ring
    under Comic Book came back a fire-red card with an orange ring — a colourless card reading
    as red, which is a BUILD-SPEC §7 failure. Art Only has no furniture to tint, and naming
    "red" positively in a brief that must not suggest red is the more expensive mistake there.

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
    if not color_identity and not strict:
        return (
            "Light this scene as a colourless card — greys, metals, stone. Keep each thing "
            "its own natural colour; do not repaint the subject to match. No one mana colour "
            "may dominate the picture."
        )
    if not color_identity:
        return (
            "This card is COLOURLESS, and that is a fact about the card, not a mood. Light it "
            "with grey, steel, stone, dust and cold white — the glow is white or pale silver. "
            "Keep each thing its own natural colour; do not repaint the subject to match. No "
            "red fire, no green growth, no blue water, no white radiance, no black rot, and no "
            "purple: each of those five reads as a mana colour this card does not have, on the "
            "edge material and the raised surfaces as much as in the scene."
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

    REVISED 2026-08-10, second gallery pull: asking only for floating panels was half the job.
    ~20 of the 24 cards build the card's outer EDGE out of the scene's material and hang the
    plates off it, and the two display plates are dark with gold lettering while only the rules
    slab is light. Our first version asked for neither, and got three identical cream rectangles
    on every card whatever the style — the client's "flat and pasted-on" report. Both are fixed
    below, in the brief only; the compositor needed no change, because `panel_palette` already
    derives ink from the surface it is printing on.
    """
    # MEASURED 2026-08-10: given the name and the rules text, the model paints them. Atraxa came
    # back fully lettered — its own name in the top plate, "Legendary Phyrexian Angel Horror" in
    # the strip, mana symbols, a Phyrexian watermark — and Terror printed a literal "P/T".
    #
    # So Creative Full is briefed the way a licensed crossover is: subject from the type line, no
    # proper noun, and the rules text never shown at all — only its LENGTH, which is the single
    # thing the model needs in order to size the slab. You cannot paint text you were never given.
    # The attached official art carries the likeness, so nothing is lost by withholding the name.
    abilities = [p for p in (face.get("oracle_text") or "").split("\n") if p.strip()]
    # ONE strip, MEASURED 2026-08-10 on a four-card batch — and this reverses the multi-strip
    # change made earlier the same day. The reference site sets one pale strip per ability and it
    # works for them; asked of our model it does not. Vampiric Tutor and Sol Ring (one ability,
    # one strip) came back with large readable text filling the panel; Terror of the Peaks and
    # Craterhoof (three and two) came back with tiny text in half-empty strips, and Craterhoof
    # inverted the requested height ratio outright — a huge empty "Haste" strip above a cramped
    # one holding its long ability.
    #
    # The mechanism was in cards/tests/test_compositor.py before the first strip was painted:
    # every strip shares one type size, so the size is capped by the WORST-fitting strip, while
    # one slab lends spare height between paragraphs. At equal area a slab fits at 115px and
    # equal strips at 97px. Explicit height ratios did not fix it — the model does not execute
    # them. `panels.detect` and `compositor._rules` still handle a list, and that stays: it costs
    # nothing and the model paints two anyway on a fair share of cards.
    strips = 1

    lines = [
        "You are a senior Magic: The Gathering card artist.",
        "",
        "Paint a COMPLETE fantasy trading card face — the artwork and the card's raised surfaces "
        "together, as one integrated illustration, with NO writing anywhere on it.",
        "",
        "The card:",
        _subject(face, licensed=True),
    ]
    if abilities:
        # Only the LENGTH, never the text: the model paints any rules text it is shown, and
        # Atraxa came back fully lettered from exactly this line's predecessor.
        total_chars = sum(len(paragraph) for paragraph in abilities)
        lines.append(
            f"Leave room for about {total_chars} characters of text, in "
            f"{len(abilities)} separate {'paragraph' if len(abilities) == 1 else 'paragraphs'}, "
            "in the broad pale strip low on the card. Size that strip to hold it comfortably."
        )
    lines += ["", _palette(face.get("color_identity") or [], strict=True)]

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
    # MEASURED 2026-08-10 on tcggenerator.com's own FULL-RESOLUTION Terror of the Peaks (their
    # originals are public at cdn.proxyprintery.de/ai_proxy_cards/<uuid>.png, and the canvas is
    # 1792x2400 — identical to ours, so the gap was never the model or the resolution): they set
    # the card's three abilities on THREE separate pale strips, not one slab.
    #
    # That is why their body text is 1.4x ours — x-height 34px against our 24px on the same
    # canvas. A strip holding two lines can be set far larger than a slab holding five, and our
    # single slab is what forced `textlayout.fit` down to 55px. bd mtg-yp3 saw a second panel and
    # filed it as variance; across their gallery it is the norm.
    surfaces = [
        "a plate across the very top, no taller than 1/10th of the card, held at both ends by "
        "the edge material. Do not omit this piece — every card has one",
        "a NARROW horizontal strip lower down, about 1/16th of the card's height, sitting "
        "directly above the broad pale strip below it. Do not omit this piece",
    ]
    surfaces.append(
        "ONE broad pale strip across the lower third, tall enough to hold every line of text "
        "comfortably with a margin. This is the single most important surface on the card: it "
        "must not be cramped, and nothing else may crowd it"
    )
    if face.get("power") is not None:
        surfaces.append(
            "a small shield-shaped boss overlapping the bottom-right corner of the lowest strip"
        )
    total = len(surfaces)
    lines += [
        "",
        # MEASURED 2026-08-10, 24 cards pulled from tcggenerator.com/explore: ~20 of them build
        # the card's outer edge out of the scene's own material and hang the plates off it. That
        # is the whole gap. Ours were three cream rectangles floating on a painting with nothing
        # anchoring them, which is why every card in a batch looked like the same sticker set.
        #
        # bd mtg-z12 logged "a literal rectangular carved frame with a MOUNT, art inset inside
        # it" as a failure. It was right about the word and wrong about the thing. "Border" and
        # "frame" name an object that surrounds a picture, and the model duly supplies a gallery
        # mount. Asked for as material closing in around the scene, the same request produces
        # what their gallery has. So the shape is asked for and the noun is never used.
        "THE CARD'S EDGE — this is what makes it a card and not a picture:",
        "The world's own material closes in around the scene at the card's edge — thick at the "
        "corners, thinner along the sides, never an even width and never a clean rectangle. "
        "Build it from whatever this scene is made of: cracked stone, living wood and root and "
        "vine, corroded iron and gears, bone, coral, ice.",
        # MEASURED 2026-08-10, ours beside the reference site's own Terror of the Peaks: theirs
        # is a hot orange ribbon of lava and ours came back near-black rock, which is what makes
        # the whole card read dark and muddy against theirs. The emissive convention `_palette`
        # already enforces for the scene had never been stated for the edge, and the material
        # list led with "cracked obsidian" — a dark descriptor — so the model painted a dark rim.
        "Run the card's colour through it as LIGHT: molten veins in the stone, sap glowing in "
        "the wood, current in the metal, frost-fire in the ice. It is lit from within, not a "
        "dark rim around a bright picture — after the subject it is the brightest thing on the "
        "card, and it is where the card's colour reads from across a table.",
        "It is grown, not laid on. The scene continues behind it, breaks through where it is "
        "thin, and at one or two points something from the scene — a claw, a tail, a wingtip, a "
        "curl of smoke — crosses in FRONT of it. It runs off all four edges of the image.",
        # MEASURED 2026-08-10, first generation under this brief: the model enclosed the ARTWORK
        # and stopped. Both side members died where the lower surfaces began, the bottom never
        # closed, and the two bottom corners came back as dead black wedges. It encloses the
        # card, and the surfaces are inside it — that has to be said, because "the card's edge"
        # and "around the scene" are the same sentence to a model painting a picture.
        "It encloses the whole CARD, not just the picture: it runs unbroken down both sides all "
        "the way past the lower surfaces and closes across the bottom underneath them, so all "
        "four corners are made of it. The raised surfaces sit INSIDE it and overlap it at their "
        "ends. No corner and no edge of this card is left as empty dark space.",
        "",
        "THE RAISED SURFACES, built from that same material and joined to it:",
        "They must look carved out of the world, out of the SAME MATERIAL as the art, never "
        "like a panel laid on top of a picture. Let the art bleed past and behind them.",
        f"Paint exactly these {total} raised surfaces and no others: "
        + "; ".join(surfaces)
        + ".",
        # MEASURED 2026-08-10, the generation after "the surfaces sit INSIDE it" was added: the
        # model read that as permission and painted a ROW OF THREE extra glowing slabs between
        # the picture and the type strip. They also stole the slab's height, so the rules text
        # genuinely overflowed. "and no others" was already in the sentence above and lost to the
        # sentence describing them, so the count is restated as its own instruction, with the
        # in-between space explicitly assigned to something that is not a surface.
        # MEASURED 2026-08-10 across ten generations of ONE card at identical settings
        # (Project Material/evidence-reference-pipeline-2026-08-10/): the surfaces move around
        # their gallery a great deal — the type plate sits under the title on some cards and
        # halfway down on others, the rules panel is a full-width band on some and a narrow
        # right-hand float on others — but the vertical ORDER never changes on any of the ten.
        # Ours listed the surfaces without ever saying that order was a requirement, and two
        # consecutive generations put the name plate down in the lower third.
        "Their order down the card is fixed and is not a suggestion: the top plate is the "
        "TOPMOST thing on the card and touches its upper edge; the narrow strip is below the "
        "picture; the broad pale strip is below the narrow strip; the shield, if there is one, "
        "is at the bottom right. Nothing may be painted above the top plate.",
        f"That is {total} and only {total}. Do not add one more, do not repeat one, and do not "
        "split a surface into a row of smaller ones — the one broad pale strip is the only place "
        "the rules text goes. Everything between the picture and these surfaces is scene or edge "
        "material — never another plate, tablet, ingot, cartouche or panel.",
        "",
        # MEASURED 2026-08-10 against the reference site's own Terror of the Peaks. The earlier
        # reading of this evidence — "their text surfaces are PALE" — was taken from the rules
        # slab alone and applied to all three, which flattened the card: cream plate, cream
        # strip, cream slab, black text on every one, no hierarchy anywhere. Across their
        # gallery the two display surfaces are DARK with warm gold lettering and only the rules
        # slab is light. compositor.panel_palette already picks gold-on-dark or ink-on-light
        # from the pixels, so the value split costs nothing on our side and is pure gain.
        "VALUE, and getting this wrong is what makes a card read as a mock-up:",
        "The top plate and the narrow strip are DARK — near-black obsidian, blackened iron, "
        "deep oxblood, weathered bronze — because warm gold lettering is printed on them "
        "afterwards.",
        "The broad strip is LIGHT — warm cream parchment, glowing amber stone, bleached bone, "
        "aged ivory, lit from within — because near-black lettering is printed on it afterwards. "
        "Even on a night scene or a lava scene it stays light.",
        "Dark, dark, then light going down the card. Do not paint all three the same value.",
        "",
        # The previous wording here — "quiet: low contrast, low detail, no busy texture and no
        # bright hotspot" — is what produced dead flat beige. Their slab on Terror of the Peaks
        # is glowing lava with cracks running through it and the black text still reads, because
        # what legibility needs is an EVEN MIDDLE, not an empty surface.
        "Every surface carries its own material and light — grain, cracks, veins of glow, a rim "
        "that catches the light unevenly along its length. What it must not carry is a hard "
        "mark, a seam or a bright hotspot across its middle, where the text lands: keep that "
        "band even in value so printed letters stay readable. Material and light, yes; incident "
        "and clutter, no.",
        "No surface is a plain rectangle with an even bevel. Each has a carved silhouette — "
        "chipped or torn ends, a notched corner, a curled rod at each end of a scroll, a rim "
        "that thickens and thins. But the long upper and lower edges of each surface stay "
        "roughly straight and level, because straight lines of text are printed across them.",
        "",
        # MEASURED 2026-08-10, first three generations: the slab came back eating ~40% of the card
        # on all three and the narrow strip was omitted on all three. The art has to be told it
        # outranks the furniture.
        "THE ARTWORK DOMINATES THE CARD. The picture is the largest thing on it and everything "
        "above sits on top of the picture. The edge material is a narrow margin — no thicker "
        "than 1/12th of the card where it is thickest, and thinner than that along the sides. "
        "The raised surfaces together may cover no more than a third of the card's height, "
        "and the strip is a BAND across the lower third — never half the card.",
        "Neither the raised surfaces nor the edge material may cover the subject's head, face "
        "or silhouette.",
        "",
        QUALITY,
        "",
        "Put the subject's face and focal point in the UPPER-MIDDLE of the card, clear of the "
        "lower strip. Nothing that matters may sit in the lower third.",
        "Keep every raised surface and every important detail inside the middle 92% of the "
        "canvas — the outer edge is trimmed off when the card is cut.",
        "Output ONE image filling the entire frame, edge to edge.",
        "",
        # Last, deliberately. Stated earlier in the brief it lost to the furniture description on
        # 2 of 3 cards; the ban has to be the final thing read. The edge material is named
        # separately because it is new and because carved runes along a border are exactly the
        # decoration a model reaches for — Twinflame Tyrant on their own site has painted fake
        # runes sitting beside its real composited rules text.
        "ABSOLUTE REQUIREMENT, overriding everything above: there is NO WRITING ANYWHERE ON THIS "
        "IMAGE — not on the raised surfaces and not on the edge material. Every raised surface "
        "is bare stone, bare wood, bare metal — blank. No letters, no words, no names, no "
        "titles, no numbers, no runes, no glyphs, no decorative script, no fake writing, no "
        "watermark, no emblem, no mana symbols, no set symbol. If you are tempted to label a "
        "surface or carve script into the edge, leave it empty instead. Real text is printed "
        "onto these surfaces afterwards and anything you paint on them will collide with it.",
    ]
    # MEASURED 2026-08-10, eight-card batch: mono-green Craterhoof came back with magenta crystal
    # growths through the art. The ban was already in `_palette` near the top of the brief, and
    # this file has learned twice that a ban stated early loses to the description after it.
    # Purple reading as black mana is the client's reported bug and a BUILD-SPEC §7 correctness
    # failure, so it is repeated late instead of trusted to survive at distance.
    #
    # Inserted BEFORE the writing ban, never after it. That ban's last position is itself
    # measured — stated mid-brief it lost on 2 of 3 cards — and lettering is the worse failure of
    # the two: painted text collides with the text we composite and makes the card unusable,
    # while a purple tint misstates the colour identity of a card that still works.
    if "B" not in (face.get("color_identity") or []):
        lines.insert(
            len(lines) - 1,
            "AND: no purple, violet, magenta or lilac anywhere in this image — not in the art, "
            "not in the light, not in the edge material, not in any surface. Purple reads as "
            "black mana and this card is not black.",
        )
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
