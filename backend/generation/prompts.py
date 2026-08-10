"""Scryfall card data -> the brief the model paints from.

Art Only (BUILD-SPEC §2) is the whole of this file: the AI paints artwork and we composite
nothing, so the brief has exactly two jobs — say what the card is, and forbid everything
that is not art.

The colour-identity sentence is correctness, not styling (BUILD-SPEC §7): it comes from
Scryfall `color_identity`, never from the style, because purple reads as black mana and a
purple-tinted mono-green card misstates its own cost.
"""

COLOURS = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}

# Longest rules text that may be offered the narrow side-panel layout. Above this a column has to
# wrap so hard that the shared type size drops below what reads across a table. See the comment
# where it is used.
FLOAT_MAX_CHARS = 110

# The reference site's own 48 styles, keyed by the exact value its API sends (`art_style` in
# POST /api/ai-proxies/generate/), so the frontend can pass a value straight through. Labels are
# accepted too — see `_style_text`.
#
# EVERY row leads with a MEDIUM and its mark-making, and that is measured, not taste (bd mtg-8x6).
# A bare label gives a generic treatment: the first "Neon Noir" row listed only light and mood —
# neon rim light, wet surfaces, haze — and Counterspell came back a photoreal cinematic render,
# which is the exact complaint the client made about the first sample batch. With no medium named
# the model defaults to photography. A row that names medium, linework, palette and finish landed
# the client-approved goblin look first try.
#
# The `artists` rows describe what the work LOOKS like rather than leaning on the name alone.
# That is better prompting by the same rule — attributes beat labels — and it also means the row
# still works if a name is ever a problem to ship.
STYLES = {
    # classic
    "fantasy_realistic": (
        "fully rendered digital fantasy painting — volumetric form with specular highlights and "
        "subsurface glow, painterly brushwork, no visible outlines, physically plausible "
        "materials, deep atmospheric background"
    ),
    "oil_painting": (
        "traditional oil painting on canvas — visible loaded brushwork and impasto ridges, warm "
        "glazed shadows, canvas tooth showing through thin passages, old-master chiaroscuro, "
        "muted earth palette lifted by one saturated accent"
    ),
    "watercolor": (
        "watercolour painting on cold-press paper — transparent washes with hard blooming edges, "
        "pigment granulating in the valleys of the paper, white of the page left as the "
        "highlights, soft wet-in-wet bleeds, delicate and luminous"
    ),
    "digital_art": (
        "polished digital illustration — clean airbrushed rendering, crisp edge control, strong "
        "rim lighting, subtle chromatic aberration and bloom, saturated contemporary palette, "
        "concept-art finish"
    ),
    "sketch": (
        "graphite pencil sketch on toned paper — confident construction lines left visible, "
        "hatched and smudged shading, white chalk highlights, unfinished edges fading into the "
        "paper, drawn rather than painted"
    ),
    "ink_drawing": (
        "pen and ink drawing — fine nib linework, dense cross-hatching and stippling carrying all "
        "the shading, pure black on cream paper with at most one spot colour, engraved-plate "
        "precision"
    ),
    "vintage_mtg": (
        "1990s fantasy trading-card painting — traditional acrylic and gouache on board, slightly "
        "muted printed colour, soft airbrushed gradients, painterly but tightly rendered, the "
        "look of early collectible card art scanned from the original board"
    ),
    # animated
    "anime": (
        "anime illustration — clean confident linework, cel shading with hard-edged shadow "
        "shapes, large expressive eyes, saturated colour, dramatic speed lines and bloom, "
        "detailed painted background"
    ),
    "studio_ghibli": (
        "hand-painted animation background in the Ghibli tradition — soft gouache skies, lush "
        "layered foliage, gentle naturalistic light, understated character linework, warm "
        "nostalgic palette, quiet and unhurried"
    ),
    "disney": (
        "classic hand-drawn animation cel — smooth tapering ink outlines, flat bright cel colour "
        "with simple shadow shapes, rounded appealing shapes and squash-and-stretch anatomy, "
        "painted storybook background"
    ),
    "pixar": (
        "stylised 3D animated render — soft global illumination and bounce light, subsurface "
        "scattering in skin, rounded exaggerated proportions with large eyes, glossy tactile "
        "materials, warm cinematic key light"
    ),
    "rick_and_morty": (
        "Rick and Morty cartoon — flat bold cel colour, confident uneven black outlines, "
        "rubber-limbed exaggerated anatomy, wide bulging expressive eyes, acid-bright greens "
        "and cyans, grimy sci-fi clutter behind the subject"
    ),
    "adventure_time": (
        "Adventure Time cartoon — simple rounded shapes, thin even outlines, flat pastel-bright "
        "colour with no rendering, tiny dot eyes, soft noodly limbs, cheerful storybook "
        "landscape behind the subject"
    ),
    "comic_book": (
        "hand-inked comic book illustration — heavy tapered brush inking, dense cross-hatching "
        "in the shadows, saturated flat colour laid over the ink, halftone dot texture, "
        "high-contrast dramatic lighting, collectible card artwork quality"
    ),
    "manga": (
        "black and white manga illustration — sharp varied-weight ink linework, screentone dots "
        "and gradients doing all the shading, dramatic speed lines and focus lines, high "
        "contrast with pure blacks, at most a single spot colour"
    ),
    # modern
    "cyberpunk": (
        "cyberpunk digital illustration — hard-edged rendering under saturated magenta and cyan "
        "neon, rain-slick reflective surfaces, holographic signage and volumetric haze, dense "
        "industrial detail, near-black shadows cut by luminous accents"
    ),
    "vaporwave": (
        "vaporwave digital collage — flat pastel pink and cyan gradients, chrome and glass "
        "surfaces, grid horizons and Roman-bust statuary, VHS scanlines and chromatic offset, "
        "deliberately artificial and dreamlike"
    ),
    "synthwave": (
        "synthwave illustration — airbrushed chrome and neon outline art, magenta-to-cyan "
        "gradient sky, glowing perspective grid, sun with horizontal slats, heavy bloom and lens "
        "flare, retro-futurist eighties poster finish"
    ),
    "pixel_art": (
        "pixel art sprite — a strictly limited palette, hard aliased pixel edges with no "
        "antialiasing, deliberate dithering for gradients, chunky readable silhouette, drawn on "
        "an obvious pixel grid like a 16-bit game"
    ),
    "low_poly": (
        "low-poly 3D render — visible flat triangular facets, faceted flat shading with hard "
        "value steps between planes, simple geometric forms, clean gradient background, no "
        "texture detail"
    ),
    "neon_noir": (
        "neon noir graphic-novel illustration — inked linework with heavy black spotting and "
        "flat screen-printed colour, near-black scene cut by luminous neon rim light, wet "
        "reflective surfaces, one glowing colour doing all the lighting"
    ),
    # artistic
    "impressionist": (
        "impressionist oil painting — broken dabs of unmixed colour laid side by side, visible "
        "directional brushstrokes, no hard outlines, colour in the shadows rather than grey, "
        "bright natural daylight, form dissolving at the edges"
    ),
    "art_nouveau": (
        "art nouveau decorative panel — flowing whiplash linework, flat ornamental colour with "
        "gold leaf, stylised botanical borders and halo motifs, muted jewel palette, poster "
        "lithograph finish"
    ),
    "art_deco": (
        "art deco poster illustration — bold geometric stylisation, symmetrical stepped forms, "
        "flat blocked colour with metallic gold and black, strong verticals and sunburst motifs, "
        "airbrushed machine-age elegance"
    ),
    "surrealism": (
        "surrealist oil painting — meticulous realist rendering of impossible things, dreamlike "
        "juxtaposition and impossible scale, long raking light and deep empty space, smooth "
        "invisible brushwork, unsettling calm"
    ),
    "expressionism": (
        "expressionist painting — violent visible brushwork and distorted anatomy, arbitrary "
        "emotional colour rather than natural colour, heavy outlines, raw texture, unsettled and "
        "intense"
    ),
    "baroque": (
        "baroque oil painting — extreme chiaroscuro with a single dramatic light source, deep "
        "shadow swallowing most of the frame, rich crimson and gold, dynamic diagonal "
        "composition, heavy fabric and gleaming metal, old-master varnish"
    ),
    # dark
    "dark_fantasy": (
        "fully rendered dark fantasy painting — heavy chiaroscuro with light carved out of near "
        "black, volumetric form, glowing molten and ember accents, painterly brushwork, grim "
        "atmospheric depth"
    ),
    "gothic": (
        "gothic painting — cold moonlit palette of slate, bone and deep violet-black, ornate "
        "stone tracery and wrought iron, mist and guttering candlelight, tall oppressive "
        "verticals, painterly and funereal"
    ),
    "lovecraftian": (
        "cosmic horror illustration — sickly green and bruised violet against black, impossible "
        "non-euclidean geometry, writhing tentacular mass half-hidden in fog, fine ink detail "
        "under painted glazes, a sense of scale that dwarfs the viewer"
    ),
    "grimdark": (
        "grimdark painted illustration — desaturated mud, rust and ash, brutal battered armour "
        "and industrial gothic ornament, harsh overcast light with hard specular hits, blood and "
        "smoke, heavy impasto texture, no beauty and no relief"
    ),
    "body_horror": (
        "body horror painting — wet organic detail, fused bone and flesh and metal, distended "
        "asymmetric anatomy, clammy pallid skin under cold light, meticulous realist rendering "
        "that makes the wrongness legible"
    ),
    # light
    "ethereal": (
        "ethereal luminous painting — soft diffuse light with no hard shadows, translucent "
        "layered veils and drifting motes, pale opalescent palette, edges dissolving into glow, "
        "weightless and serene"
    ),
    "celestial": (
        "celestial illustration — deep indigo star-field with nebula colour, gold constellation "
        "linework and astrolabe geometry, radiant haloed light, polished and reverent, cosmic "
        "scale behind an intimate subject"
    ),
    "pastel_fantasy": (
        "pastel fantasy illustration — soft chalk-pastel colour in mint, rose and lavender, "
        "gentle gradients with no harsh contrast, rounded friendly shapes, light airy background, "
        "storybook warmth"
    ),
    "kawaii": (
        "kawaii illustration — thick soft outlines, flat candy-bright colour, oversized head and "
        "huge glossy eyes, tiny simplified limbs, blush marks and sparkle accents, cheerful and "
        "rounded with no sharp edges"
    ),
    "fairy_tale": (
        "golden-age fairy-tale book illustration — fine pen linework under delicate watercolour "
        "washes, decorative borders, warm amber and moss palette, gnarled storybook forest, "
        "printed-plate texture"
    ),
    # artists
    "mtg_seb_mckinnon": (
        "melancholic ink-and-wash fantasy painting — heavy black silhouettes against pale washed "
        "ground, scratchy expressive linework, muted grey-green and dried-blood red, spectral "
        "elongated figures, funereal romantic atmosphere"
    ),
    "mtg_rebecca_guay": (
        "pre-Raphaelite watercolour and gouache fantasy painting — flowing decorative linework, "
        "soft luminous washes over gold-leaf ornament, willowy graceful figures, tapestry-like "
        "flattened depth, warm amber and sage palette"
    ),
    "mtg_john_avon": (
        "luminous fantasy landscape painting — vast atmospheric vista with tiny human scale, "
        "airbrushed gradient skies at dawn or dusk, floating islands and impossible geology, "
        "jewel-bright saturated colour, serene and expansive"
    ),
    "alphonse_mucha": (
        "art nouveau lithograph poster — flowing organic linework, ornamental circular halo "
        "behind the subject, flat muted pastel colour with gold, decorative botanical framing, "
        "printed-poster texture"
    ),
    "hr_giger": (
        "biomechanical airbrush painting — fused bone, sinew and machined metal in monochrome "
        "grey-green, ribbed tubular structures, glistening wet surfaces, obsessive fine "
        "airbrushed gradients, cold and claustrophobic"
    ),
    "moebius": (
        "clear-line bande dessinée illustration — even-weight ink outlines with no hatching, flat "
        "unshaded colour in unexpected pastel combinations, vast serene desert vistas, precise "
        "delicate detail, dreamlike and weightless"
    ),
    # other
    "stained_glass": (
        "stained glass window — flat jewel-bright panes of pure colour separated by heavy black "
        "leading, simplified iconic shapes, radiant backlight blowing through the glass, stone "
        "tracery border, no gradients"
    ),
    "paper_cut": (
        "layered paper-cut diorama — flat shapes cut from coloured paper stacked in receding "
        "planes, crisp scissor edges with visible paper thickness and soft drop shadows between "
        "layers, limited palette, tactile and handmade"
    ),
    "graffiti": (
        "spray-paint graffiti art — thick black outlines with a bright keyline, aerosol "
        "gradients and overspray, wildstyle energy, drips and splatter, saturated clashing "
        "fluorescents against a concrete wall"
    ),
    "propaganda_poster": (
        "mid-century propaganda poster — bold flat blocked colour in red, cream and black, heavy "
        "stencil-like shapes, low heroic angle on the subject, screen-printed grain and "
        "misregistration, stark graphic simplification"
    ),
    "tarot_card": (
        "medieval tarot card illustration — flat symbolic figures with black outlines, limited "
        "palette of ochre, madder red and slate blue, gold ornament and celestial symbols, "
        "hand-printed woodblock texture, rigidly symmetrical"
    ),
}

# Their label for each key, so a frontend can send either form. Built from the same extraction as
# STYLES (their bundle groups these as classic / animated / modern / artistic / dark / light /
# artists / other, which is presentation only and does not change the brief).
STYLE_LABELS = {
    "fantasy_realistic": "Fantasy Realistic", "oil_painting": "Oil Painting",
    "watercolor": "Watercolor", "digital_art": "Digital Art", "sketch": "Sketch",
    "ink_drawing": "Ink Drawing", "vintage_mtg": "Vintage MTG", "anime": "Anime",
    "studio_ghibli": "Studio Ghibli", "disney": "Disney", "pixar": "Pixar",
    "rick_and_morty": "Rick and Morty", "adventure_time": "Adventure Time",
    "comic_book": "Comic Book", "manga": "Manga", "cyberpunk": "Cyberpunk",
    "vaporwave": "Vaporwave", "synthwave": "Synthwave", "pixel_art": "Pixel Art",
    "low_poly": "Low Poly", "neon_noir": "Neon Noir", "impressionist": "Impressionist",
    "art_nouveau": "Art Nouveau", "art_deco": "Art Deco", "surrealism": "Surrealism",
    "expressionism": "Expressionism", "baroque": "Baroque", "dark_fantasy": "Dark Fantasy",
    "gothic": "Gothic", "lovecraftian": "Lovecraftian", "grimdark": "Grimdark",
    "body_horror": "Body Horror", "ethereal": "Ethereal", "celestial": "Celestial",
    "pastel_fantasy": "Pastel Fantasy", "kawaii": "Kawaii", "fairy_tale": "Fairy Tale",
    "mtg_seb_mckinnon": "MTG: Seb McKinnon", "mtg_rebecca_guay": "MTG: Rebecca Guay",
    "mtg_john_avon": "MTG: John Avon", "alphonse_mucha": "Alphonse Mucha",
    "hr_giger": "H.R. Giger", "moebius": "Moebius", "stained_glass": "Stained Glass",
    "paper_cut": "Paper Cut", "graffiti": "Graffiti",
    "propaganda_poster": "Propaganda Poster", "tarot_card": "Tarot Card",
}
_BY_LABEL = {label.lower(): key for key, label in STYLE_LABELS.items()}


def _style_text(style):
    """A style key, a style label, or free text -> the attributes to paint from.

    Anything unrecognised passes through verbatim, which is exactly what the "Custom Art Style"
    free-text field needs, so the fallback is a feature rather than a gap.
    """
    if not style:
        return None
    key = str(style).strip()
    if key in STYLES:
        return STYLES[key]
    return STYLES.get(_BY_LABEL.get(key.lower(), ""), key)


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
        "bone stays bone, smoke stays grey. "
        # MEASURED 2026-08-11: this paragraph named only NEUTRAL things that keep their colour —
        # stone, steel, bone, smoke — so nothing in it told the model that a subject with a
        # colour of its own may keep it. Mono-red Raphael came back a red turtle again, shell and
        # all, on a card whose whole point is that he is green. The reference site's own Raphael
        # is green on the same red card, so their brief evidently permits it and ours did not.
        "THE SUBJECT KEEPS ITS OWN COLOUR even when that colour is not the card's: a green "
        f"turtle on a {names} card stays green, a blue dragon stays blue, a white robe stays "
        f"white. The {names} is the light falling ON the subject and the world around it, never "
        "paint applied to the subject itself. "
        f"Do not tint the whole picture one hue and do not drain it to monochrome — the {names} "
        "must read as the brightest thing in a mostly neutral scene, which is what makes it read "
        "hot. No other mana colour may dominate, and purple in particular must not appear unless "
        "the card is black, because purple reads as black mana."
    )


def creative_full(
    face, style=None, reference=True, licensed=False, direction=None, palette=None, notes=None
):
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
            f"Art style: {_style_text(style)}. This governs the whole picture — the "
            "furniture as much as the art.",
        ]
    if direction:
        lines += ["", f"Composition: {direction}."]
    if palette:
        lines += ["", f"Colour treatment: {palette}, within the colour identity above."]
    if notes:
        # `custom_art_notes` in their payload — the user's own words, placed after the style so it
        # refines rather than replaces it, and before the furniture so it cannot argue with the
        # surfaces. Passed verbatim: it is the one field where second-guessing the user is wrong.
        lines += ["", f"Also: {notes}."]

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
    band = (
        "ONE broad pale strip across the lower third, tall enough to hold every line of text "
        "comfortably with a margin. This is the single most important surface on the card: it "
        "must not be cramped, and nothing else may crowd it"
    )
    # The reference site produces a narrow right-hand rules panel on about 2 of every 10 cards
    # (measured on the ten Tannuks), with the art filling the space beside it. It is the best-
    # looking layout they have, and it is also the one that costs the most type size: half the
    # measure means roughly twice the lines, and a card whose text will not fit at a readable
    # size is a regeneration, which is a credit.
    #
    # So it is offered rather than left to emerge, and only where the arithmetic survives it.
    # Their brief evidently just permits it; ours permits it only for cards short enough that a
    # column still reads. Sol Ring (16 chars), Counterspell (21) and Lightning Bolt (44) are
    # comfortable; Terror of the Peaks (210) and Atraxa (200) are not, and those are exactly the
    # cards that came back with unreadable type when the layout was forced.
    if sum(len(paragraph) for paragraph in abilities) <= FLOAT_MAX_CHARS:
        surfaces.append(
            band + ". This card's text is short, so that strip may instead be a TALL NARROW "
            "panel down the left or the right, about a third of the card's width, with the "
            "artwork filling the space beside it — whichever of the two suits the composition. "
            "Either way it is one panel, pale, with straight level top and bottom edges"
        )
    else:
        surfaces.append(band)
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
        "IMAGE — not on the raised surfaces, not on the edge material, and not in the gaps "
        "between them. Every raised surface is bare stone, bare wood, bare metal — blank. No "
        "letters, no words, no names, no titles, no numbers, no glyphs, no decorative script, "
        "no fake writing, no watermark, no emblem, no mana symbols, no set symbol. If you are "
        "tempted to label a surface or carve script into the edge, leave it empty instead. Real "
        "text is printed onto these surfaces afterwards and anything you paint on them will "
        "collide with it.",
        # MEASURED 2026-08-11 on Raphael: a band of carved rune-like marks came back in the gap
        # between the type plate and the rules panel — a region the ban above named as surfaces
        # and edge, and therefore did not cover. Runes are the recurring form of this failure
        # rather than one item in a list of twelve, and the reference site has it too: their
        # Twinflame Tyrant carries painted fake runes right beside its real composited text. So
        # it gets its own sentence, after the list, where nothing follows to outrank it.
        "RUNES ESPECIALLY. A row or band of carved rune-like marks anywhere on this card is a "
        "failed image, and it is failed even when the marks are meant as ornament rather than "
        "as something readable. Where you would carve runes, carve nothing: leave the material "
        "plain, or use a shape that is obviously not writing — a notch, a rivet, a crack, a leaf.",
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
        # Located by looking for the ban rather than counting back from the end: it was inserted
        # at len(lines) - 1 and silently moved AFTER the writing ban the day a rune sentence was
        # appended, which is the exact position this comment says it must never take.
        writing_ban = next(
            index
            for index, line in enumerate(lines)
            if line.startswith("ABSOLUTE REQUIREMENT")
        )
        lines.insert(
            writing_ban,
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
            f"Art style: {_style_text(style)}. This governs the whole picture — the "
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
