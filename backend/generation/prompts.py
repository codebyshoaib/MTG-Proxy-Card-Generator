"""Scryfall card data -> the brief the model paints from.

Art Only (BUILD-SPEC §2) is the whole of this file: the AI paints artwork and we composite
nothing, so the brief has exactly two jobs — say what the card is, and forbid everything
that is not art.

The colour-identity sentence is correctness, not styling (BUILD-SPEC §7): it comes from
Scryfall `color_identity`, never from the style, because purple reads as black mana and a
purple-tinted mono-green card misstates its own cost.
"""

import math

from cards import compositor, textlayout

COLOURS = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}

# Longest rules text that may be offered the narrow side-panel layout. Above this a column has to
# wrap so hard that the shared type size drops below what reads across a table. See the comment
# where it is used.
FLOAT_MAX_CHARS = 110

# The canvas: gemini-3-pro-image at 3:4 2K, which is the 1792x2400 we store and composite into.
CANVAS = (1792, 2400)
# A rules strip runs about 88% of the card's width once it is clear of the sides, and the
# compositor then insets the text by PAD at each end. It is that INNER width the text wraps to —
# measuring against the outer width assumes a wider measure than the text ever gets, under-counts
# the lines, and asks for a strip too short.
STRIP_WIDTH = round(CANVAS[0] * 0.88 * (1 - 2 * compositor.PAD))

# MEDIAN LINE PITCH OF A REAL PRINTED CARD, as a fraction of card height. MEASURED 2026-08-15 over
# n=40 real 2015-frame cards spanning 13-336 oracle characters (bd mtg-8h9,
# bd mtg-8h9). Sizing the strip to this asks for a card that reads like a printed
# one, rather than one that merely clears `compositor.RULES_MIN` — the floor is the point below
# which a card is unusable, not the target.
REAL_CARD_PITCH = 0.0332


def _target_size():
    """The em at which our text matches a real printing's line pitch.

    Derived from `textlayout` rather than written down, so that if the face or the leading ever
    changes the brief keeps asking for the right amount of room instead of quietly going stale.
    """
    for size in range(20, 200):
        _, line_height, _ = textlayout.wrap(
            textlayout.atoms("the quick brown fox"), size, STRIP_WIDTH, None
        )
        if line_height >= CANVAS[1] * REAL_CARD_PITCH:
            return size
    return 60


TARGET_SIZE = _target_size()

# The demand is a rounded PERCENTAGE, not a rung off a ladder, and that is measured.
#
# It was a ladder — 1/8, 1/6, 1/5, 1/4, 1/3 — on the theory that a model acts on fractions more
# reliably. The theory cost more than it bought. Elesh Norn's text needs 26.6% of the card, the
# ladder had no rung between a quarter and a third, so it rounded UP to a THIRD and asked for a
# quarter more room than the card actually needs. MEASURED over 8 live faces on 2026-08-15: the
# strip came back at or above the asked height 1 time in 8, and across six runs of that one card
# it never passed 27.6%. An unreachable number is not a stricter instruction, it is an ignored
# one — and it makes the compliance figure meaningless as well.
#
# Percentages are already this brief's own idiom ("inside the middle 92% of the canvas"), so
# stating one costs nothing in legibility. Rounded UP to the nearest 2%, so the number reads as a
# target rather than as a suspiciously precise measurement.
STRIP_STEP = 0.02
# A floor, because "as tall as this card's text needs" stops being sensible at the short end. A
# 44-character card needs one line, which is 3% of the card — ask for that and the brief is
# demanding a nameplate rather than a text box, and it would be asking for LESS than the model
# already paints unprompted (Lightning Bolt came back at 14.0% on 2026-08-15). This was the old
# fraction ladder's bottom rung doing work nobody had noticed it doing, so it is kept explicitly.
# A real printed card goes further and gives every card the same text box whatever its text; the
# reference site sizes panels to the text (HOW-THEY-DO §6) and that is the look being matched, so
# this is a floor rather than a fixed size.
STRIP_MIN = 1 / 8
# Capped at a THIRD, measured rather than chosen: a real printed card gives its text box roughly
# 28-30%, so a third for the wordiest cards is what Magic itself does. Capping lower guaranteed a
# repaint on any card over ~270 characters, because the brief would then be asking for a surface
# too short to hold the text even at the floor.
STRIP_MAX = 1 / 3
# The other two surfaces the brief asks for: the top plate (1/10th) and the narrow strip (1/16th).
OTHER_SURFACES = 1 / 10 + 1 / 16
TOTAL_LADDER = ((1 / 3, "a third"), (0.42, "two fifths"), (1 / 2, "half"), (0.55, "55%"))


def _strip_height(face):
    """(fraction, phrase) the rules strip must be for THIS card's text — or None if it has none.

    THE POINT OF THIS FUNCTION. `compositor.RULES_MIN` was validated over n=40 real printed cards
    and is right to within 6% of the tightest real printing, so a card that trips it is genuinely
    unreadable and the floor must not be moved. The defect it reports is upstream: the surface the
    model painted is too short. The brief used to ask for a strip "tall enough to hold every line
    of text comfortably", which is a wish — the model has no idea how much text this card has,
    because we deliberately never show it any. So the number is computed here and stated.

    The reference site evidently does the same thing: HOW-THEY-DO 2026-08-10 §6 records that they
    size the panel TO the text, which is why theirs has no dead parchment.

    Measured with the compositor's own layout engine, so the two cannot drift apart.
    """
    needed = _needed(face)
    if not needed:
        return None
    rounded = math.ceil(needed / STRIP_STEP) * STRIP_STEP
    asked = min(STRIP_MAX, max(STRIP_MIN, rounded))
    return asked, f"{asked * 100:.0f}%"


def _needed(face):
    """The bare fraction of the card this face's text occupies, before any floor, cap or rounding.

    Split out so a test can assert the DEMAND tracks the NEED — the defect that made the old
    fraction ladder ask for a third of the card when 26.6% would do.
    """
    oracle = "\n".join(p for p in (face.get("oracle_text") or "").split("\n") if p.strip())
    if not oracle:
        return 0.0
    # Wrapped in ONE pass, exactly as `compositor._rules` does it. Measuring each ability on its
    # own and adding the results looks equivalent and is not: `block_height` charges a gap BETWEEN
    # abilities, and an ability measured alone has no gap to charge. On a four-ability card that
    # lost three gaps and under-asked by enough that a quarter of the card still overflowed —
    # caught by the round-trip test, which is the only reason this is right.
    wrapped, line_height, _ = textlayout.wrap(
        textlayout.atoms(oracle), TARGET_SIZE, STRIP_WIDTH, None
    )
    return textlayout.block_height(wrapped, line_height) / (CANVAS[1] * (1 - 2 * compositor.PAD))


def _surface_budget(face):
    """How much of the card all the raised surfaces may cover, given what the rules strip needs.

    Kept consistent with `_strip_height` by construction. The artwork still has to dominate — that
    requirement was measured on 2026-08-10, when the slab came back eating ~40% of three cards in
    a row — so this only ever loosens by as much as the text genuinely requires.
    """
    room = _strip_height(face)
    needed = (room[0] if room else 1 / 6) + OTHER_SURFACES
    for fraction, phrase in TOTAL_LADDER:
        if needed <= fraction:
            return phrase
    return TOTAL_LADDER[-1][1]

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

# Their own grouping of the 48, same source and same date as DIRECTIONS below. Presentation
# only — it changes no brief — but 48 options in one flat list is a scroll, not a choice.
STYLE_GROUPS = {
    "Classic": ("fantasy_realistic", "oil_painting", "watercolor", "digital_art", "sketch", "ink_drawing", "vintage_mtg"),
    "Animated": ("anime", "studio_ghibli", "disney", "pixar", "rick_and_morty", "adventure_time", "comic_book", "manga"),
    "Modern": ("cyberpunk", "vaporwave", "synthwave", "pixel_art", "low_poly", "neon_noir"),
    "Artistic": ("impressionist", "art_nouveau", "art_deco", "surrealism", "expressionism", "baroque"),
    "Dark": ("dark_fantasy", "gothic", "lovecraftian", "grimdark", "body_horror"),
    "Light": ("ethereal", "celestial", "pastel_fantasy", "kawaii", "fairy_tale"),
    "Artists": ("mtg_seb_mckinnon", "mtg_rebecca_guay", "mtg_john_avon", "alphonse_mucha", "hr_giger", "moebius"),
    "Other": ("stained_glass", "paper_cut", "graffiti", "propaganda_poster", "tarot_card"),
}
STYLE_GROUP_OF = {key: group for group, keys in STYLE_GROUPS.items() for key in keys}


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


# The other two option groups, `art_direction` (21) and `color_palette` (20), EXTRACTED VERBATIM
# from their bundle on 2026-08-15 — `tcggenerator.com/assets/index-Btl2yW79.js`, where the three
# catalogues sit together as `{classic:[...], animated:[...]}` object literals. Their keys, their
# labels and their grouping; only the brief text after each one is ours, because their prompts
# are server-side and were never obtained.
#
# Each entry is (label, brief text, group). The text goes into the brief as written, and
# unrecognised input passes through, so the frontend's select and its free-text field are the
# same field. The group is presentation: it drives the `<optgroup>` headings, exactly as they
# group theirs.
#
# Every palette phrase is worded as LIGHT and TREATMENT rather than as hues, because the brief
# constrains it with "within the colour identity above" and colour identity comes from Scryfall,
# never from the palette (CLAUDE.md). A palette that named hues would fight that rule — a violet
# one on a mono-green card misstates the card's colour in MTG's own visual language. This is why
# "Toxic" and "Cosmic" describe luminescence and starlight rather than green and purple.
DIRECTIONS = {
    "dynamic": ("Dynamic", "caught mid-action on a strong diagonal, weight and motion", "Composition"),
    "portrait": ("Portrait", "a formal portrait, the subject squared to the viewer", "Composition"),
    "close_up": ("Close Up", "a tight crop on the subject's head and shoulders", "Composition"),
    "full_body": ("Full Body", "the whole subject in frame, head to feet", "Composition"),
    "landscape": ("Landscape", "the subject small against a vast landscape", "Composition"),
    "aerial_view": ("Aerial View", "seen from high above, looking down", "Composition"),
    "worms_eye": ("Worm's Eye", "seen from ground level, towering over the viewer", "Composition"),
    "cinematic": ("Cinematic", "an anamorphic film frame, shallow focus, lens bloom", "Cinematic"),
    "dramatic": ("Dramatic", "one hard key light, deep falloff into shadow", "Cinematic"),
    "epic": ("Epic", "scale and grandeur, the moment a legend is made", "Cinematic"),
    "intimate": ("Intimate", "close and quiet, a private moment", "Cinematic"),
    "minimalist": ("Minimalist", "one subject, empty space, nothing else competing", "Style"),
    "detailed": ("Detailed", "dense detail and ornament carried into every corner", "Style"),
    "abstract": ("Abstract", "shape, gesture and light over literal description", "Style"),
    "symmetrical": ("Symmetrical", "a formal, mirrored composition built on a centre line", "Style"),
    "rule_of_thirds": ("Rule of Thirds", "the subject set off-centre on a third", "Style"),
    "heroic": ("Heroic", "the moment a stand is made, light breaking through", "Mood"),
    "menacing": ("Menacing", "something is about to go wrong, tension held", "Mood"),
    "peaceful": ("Peaceful", "still and unhurried, soft light, nothing threatening", "Mood"),
    "chaotic": ("Chaotic", "everything in motion at once, debris and clash", "Mood"),
    "mysterious": ("Mysterious", "half-hidden, fog and withheld information", "Mood"),
}

PALETTES = {
    "vibrant": ("Vibrant", "saturated and high-key, colour pushed hard", "Basic"),
    "muted": ("Muted", "desaturated and restrained, colour held back", "Basic"),
    "dark": ("Dark", "a low-key scene, deep shadow with light used sparingly", "Basic"),
    "light": ("Light", "a high-key scene, bright and open with soft shadow", "Basic"),
    "pastel": ("Pastel", "soft, chalky and light, no hard darks", "Basic"),
    "monochrome": ("Monochrome", "near-monochrome, one hue carrying the whole image", "Basic"),
    "neon": ("Neon", "neon signage as the light source, wet reflective surfaces", "Specific"),
    "earth_tones": ("Earth Tones", "ochre, clay and weathered stone, nothing synthetic", "Specific"),
    "jewel_tones": ("Jewel Tones", "deep saturated gemlike colour, lit from within", "Specific"),
    "metallic": ("Metallic", "polished metal, specular highlights and reflected light", "Specific"),
    "sepia": ("Sepia", "aged and toned, like a photograph left in the sun", "Specific"),
    "warm": ("Warm", "warm light throughout, amber and firelit", "Temperature"),
    "cool": ("Cool", "cool light throughout, cold air and long shadow", "Temperature"),
    "sunset": ("Sunset", "low sun, long shadows, warm haze", "Themed"),
    "ocean": ("Ocean", "underwater light, caustics and suspended particles", "Themed"),
    "forest": ("Forest", "dappled light through canopy, moss and damp bark", "Themed"),
    "fire": ("Fire", "lit by flame, embers and heat haze", "Themed"),
    "ice": ("Ice", "lit through ice, frost and pale glare", "Themed"),
    "toxic": ("Toxic", "sickly luminescence, vapour and stained ground", "Themed"),
    "cosmic": ("Cosmic", "starfield and nebula light, vast and cold", "Themed"),
}


STYLE_TIEBREAK = (
    "Where the style names colours of its own, they are its medium and its mood — the card's "
    "colour identity above still decides which colour reads hottest."
)
"""The other door the same bug walks through (bd mtg-v2n).

MEASURED 2026-08-10: the "Rick and Morty" row hard-codes "acid-bright greens and cyans", and on
mono-black Vampiric Tutor the style won — the card came back green-lit, misstating its identity
exactly as the client's original purple-on-mono-green bug did.

23 of the 48 rows name a colour, but most name a MEDIUM — black ink, white paper, the leading in
stained glass — and stripping those would break the style they describe. The bead's own note is
that this is arguable and worth asking the client, since their reference deck does it too. So
this states the tiebreak instead of editing 23 rows on an open question: cheap, reversible, and
it leaves the decision where it belongs.
"""


def _palette_clause(palette, color_identity):
    """The colour-treatment line, shared by both modes so there is one answer, not two that drift.

    MEASURED on job 9f16e827 (bd mtg-5pb): `ice` on mono-red Lightning Bolt came back blue-white —
    frost, icicles, cold glare — with red surviving only as an ember. The identity paragraph is
    strong and comes first; this clause used to end with "within the colour identity above", a
    BACK-REFERENCE, and on that card the palette won. Intermittent, too: the rerun with identical
    inputs read red.

    The fix is the cheap lever the bead itself named — restate the constraint here instead of
    pointing back at it — plus the positive phrasing that bd mtg-8x6 measured working: name what
    the card's colour DOES rather than only what the palette may not do. An absolute prohibition
    repaints the subject; a positive instruction leaves its local colour alone.
    """
    treatment = _catalogue_text(palette, PALETTES)
    if not color_identity:
        # Colourless already forbids all five hues by name; adding a second, weaker restatement
        # here would give the model two rules to reconcile instead of one to follow.
        return f"Colour treatment: {treatment}."
    names = " and ".join(COLOURS[c] for c in color_identity if c in COLOURS)
    return (
        f"Colour treatment: {treatment}. This is the QUALITY OF THE LIGHT and the finish, not a "
        f"recolouring of the card: the {names} of this card's colour identity stays the brightest "
        f"and hottest thing in the frame, and the treatment plays around it. Where the two "
        f"disagree, the {names} wins."
    )


def _catalogue_text(value, table):
    """A key, a label, or free text -> the brief text, by the same rule as `_style_text`."""
    if not value:
        return None
    key = str(value).strip()
    if key in table:
        return table[key][1]
    by_label = {label.lower(): text for label, text, _group in table.values()}
    return by_label.get(key.lower(), key)


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

# How the attached official art is allowed to be used, shared by both modes so there is one
# answer to the question rather than two that drift.
#
# CLIENT 2026-08-13: "it is a little too similar to the original art on one of them, we usually
# dont want them to come out looking like the original card, just elements to be there." Our
# Raphael reproduced the official card's composition — the same turtle lifting the same
# bowling-ball dumbbells in the same gym — because the brief asked for exactly that: "what is in
# it, and what they are doing". The likeness was never the problem, the RESTAGING was missing.
#
# So identity is taken and composition is refused, in that order and in those words. Saying only
# "do not copy it" is the failure mode on the other side: the model drops the character too, and
# the client's first complaint about the whole batch was cards that did not look like the subject.
REFERENCE = (
    "The attached image is the card's official artwork. Take from it ONLY WHO OR WHAT the "
    "subject is — the character's identity, build, gear, and the markings and colours that make "
    "them recognisable at a glance. Do not restage the picture: invent a NEW moment for them, "
    "with a different pose, a different action, a different angle and a different setting from "
    "the reference. Someone holding the two side by side must see the same character and not the "
    "same picture. Take nothing of how it is drawn: not its palette, not its lighting, not its "
    "period, not its level of realism, not its setting. Where the reference and the art style "
    "disagree, the art style wins."
)

# CLIENT 2026-08-16, on Craterhoof: "the same animal in the same pose as the original, it must be
# different ... if it helps the ai can read the card typing on the creature to get an idea of what
# the creature should look like, that and the name of the card, as well as potentially referencing
# the original card to a degree."
#
# The first half of his suggestion is already what we do — the name and the type line are in every
# brief — and the second half is already what REFERENCE above asks for, in these words: "invent a
# NEW moment for them, with a different pose, a different action, a different angle". It lost.
#
# That makes it the fourth clause on this project to be correctly worded and ignored, and the
# lesson from the other three is that a NEGATIVE does not survive: the P/T shield took three
# rewordings and was only fixed by looking closer (e10ba96), the title order took a late positive
# restatement (mtg-39a), and the overlap took being made compulsory with a count.
#
# So this stops asking the model not to copy a staging and hands it one instead. A model given a
# camera and a moment to paint cannot fall back on the reference's, because it already has one.
#
# Camera and moment are separate lists multiplied together rather than one list of finished
# sentences: 8 x 7 is 56 stagings out of 15 phrases, and any card that lands on a bad pairing is
# one edit away rather than one more sentence.
#
# Both are deliberately SUBJECT-AGNOSTIC. "Charging at the viewer" reads as a direction to a beast
# and as nonsense to Sol Ring, and Creative Full briefs artifacts and instants through this same
# path. An angle and a beat apply to anything that can be drawn.
STAGING_CAMERA = (
    "from low down, looking up at it",
    "from slightly above, looking down",
    "at eye level and close, filling the frame",
    "from behind and to one side, as it turns back",
    "in three-quarter view from its left",
    "in three-quarter view from its right",
    "head-on and square to the viewer",
    "from far enough back that the place around it reads too",
)
STAGING_MOMENT = (
    "mid-movement and off-balance, not posed",
    "in the instant before it acts",
    "in the instant just after, everything still settling",
    "still and alert, watching something outside the frame",
    "turning sharply toward something off to one side",
    "at the top of its movement, held for a beat",
    "braced and bearing weight",
)


def _staging(face):
    """One camera and one moment, fixed by the card's own name.

    Deterministic on purpose. A random staging would make the same card different on every run,
    which breaks the one thing this project relies on to tell a fix from noise — rerunning the
    same card over the same settings and comparing. `hash()` is salted per process and cannot be
    used; the name's own bytes can.
    """
    seed = sum(face["name"].encode())
    camera = STAGING_CAMERA[seed % len(STAGING_CAMERA)]
    moment = STAGING_MOMENT[(seed // len(STAGING_CAMERA)) % len(STAGING_MOMENT)]
    return (
        f"STAGE IT THIS WAY, and this is not a suggestion: show the subject {camera}, {moment}. "
        "That is the picture to paint. It is deliberately NOT the staging of the attached "
        "reference, and where the two disagree this one wins."
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
    # MEASURED 2026-08-16: mono-black is the only identity that has never passed
    # `check.colour_identity`. Obliterator came back red 79% under the `pastel` palette and red
    # 100% under `oil_painting`, a plain style with nothing fighting it — four failures, two
    # styles, no passes. The paragraph below is the cause rather than a wording weakness: it
    # assigns the identity to emissive light, and black has no emissive colour. Read back to a
    # black card it says "the black must read as the brightest thing ... which is what makes it
    # read hot", so the model paints the only hot thing it can and the card comes back orange.
    #
    # Black is therefore given the two routes it actually has, which are the two routes
    # `check.colour_identity` accepts: make no colour claim at all (saturated share under
    # NEUTRAL_SHARE, how white and colourless pass), or let its own hue dominate — and the hue
    # `check` reads back as black is purple. Warm light is banned by name because warm light is
    # the measured failure, not a hypothetical one.
    #
    # Mono-black only. B/R and B/G have a partner colour that does own an emissive, so the clause
    # below has something to assign there and has not been measured failing.
    if set(color_identity) == {"B"}:
        return (
            "This card's colour identity is BLACK. Black is the one colour with no light of its "
            "own — there is no black glow — so do not invent one and do not let the style's own "
            "warmth stand in for it. Black is carried by DARKNESS and by MATERIAL: a low-key "
            "scene where deep shadow holds most of the frame, and oil, ichor, tarnished iron, "
            "ash, bone, wet stone and rot doing the work that colour does on other cards. "
            "What light there is stays cold — violet, bruised purple, corpse-green or bone-white. "
            "Purple is right on this card and on no other, because purple reads as black mana. "
            "NO WARM LIGHT: no fire, no lava, no embers, no orange, no red glow, no gold. Warm "
            "light reads as red mana, and a black card lit warm misstates its own cost. "
            "THE SUBJECT KEEPS ITS OWN COLOUR even when that colour is not the card's: a green "
            "turtle on a black card stays green, and flesh under the armour stays the colour "
            "flesh is. The darkness is what falls ON the subject and the world around it, never "
            "paint applied to the subject itself."
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
    face, style=None, reference=True, licensed=False, direction=None, palette=None, notes=None,
    borderless=True,
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

    `borderless` drops that edge and runs the artwork off all four sides instead, with the
    surfaces sitting in the scene as objects. It is ON by default, and that is the CLIENT's call
    of 2026-08-13: "the white borders on the first card are not ideal ... what we use to do is
    type into the custom art notes 'borderless' and try to get no black or white borders, if you
    can do that it would be by far the best", and then, of a set of full-bleed ink-sketch cards,
    "these look the best ... how the cards are reallllly borderless and creative as to where to
    place the text and make the card feel like 1 piece of art".

    The framed edge is kept rather than deleted: it is what ~20 of the reference site's own 24
    gallery cards do, it is the measured cure for plates that read as pasted on, and it is the
    fallback the client also accepted ("id be okay with black borders or black going around").
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
    # The client's own workflow on the reference site is to type "borderless" into Custom Art
    # Notes, so the word arriving in `notes` turns the mode on as well as the argument does. Done
    # here rather than in the caller so every entry point — CLI, API, frontend — gets it.
    borderless = bool(borderless) or "borderless" in (notes or "").lower()
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
        lines += ["", REFERENCE, _staging(face)]
    if style:
        lines += [
            "",
            f"Art style: {_style_text(style)}. This governs the whole picture — the "
            f"furniture as much as the art. {STYLE_TIEBREAK}",
        ]
    if direction:
        lines += ["", f"Composition: {_catalogue_text(direction, DIRECTIONS)}."]
    if palette:
        lines += ["", _palette_clause(palette, face.get("color_identity") or [])]
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
        "a plate across the very top, no taller than 1/10th of the card"
        + (
            " and NARROWER than the card — its ends stop well short of both side edges, with "
            "painted scene either side of it and the picture running behind it"
            if borderless
            else ", held at both ends by the edge material"
        )
        + ". Do not omit this piece — every card has one",
        "a NARROW horizontal strip lower down, about 1/16th of the card's height, sitting "
        "directly above the broad pale strip below it. Do not omit this piece",
    ]
    # PER CARD, not one wish for every card (bd mtg-8h9). "Tall enough to hold every line of
    # text" cannot be acted on by a model that is never shown the text — and is never shown it on
    # purpose, because the whole design is that we composite the words and it paints the surface.
    # So the room its text needs is measured with the compositor's own engine and stated.
    room = _strip_height(face)
    band = (
        "ONE broad pale strip across the lower third, "
        + (
            f"whose FLAT PALE FACE is AT LEAST {room[1]} of the card's height — that is the "
            "clear even area alone, measured inside its rim and NOT counting the curled rods, "
            "carved ends, torn edges or anything crossing it. This card's rules text needs "
            "exactly that much clear room to be read across a table, and a shorter face makes "
            "the card unusable, so if the ends are ornate make the whole piece bigger"
            if room
            else "tall enough to hold every line of text comfortably with a margin"
        )
        + ". This is the single most important surface on the card: it must not be cramped, and "
        "nothing else may crowd it"
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
        # MEASURED 2026-08-16 across 18 full-res CREATURE cards from their gallery
        # (Project Material/evidence-reference-frames-2026-08-16/): rounded rectangle or tab 11,
        # disc 2, bare-on-the-art or an irregular blob 3, SHIELD 2. Shield is 11% of the reference
        # and was 100% of ours, because this line named it and naming a shape pins it — the same
        # mechanism the comment above records for "banner" and "plaque".
        #
        # The shield is also the worst shape for our own pipeline, which is why it is not merely a
        # taste fix: it is a pointed rim around a small recessed face (bd mtg-1uv, "a fixed box
        # cannot track a painted one") and the smallest surface on the card at 0.067 of the width,
        # which is what held detection at 35%. A rounded tab has a straight rim and a far larger
        # printable face inside the same bounding box.
        #
        # So the shape is opened up and the FACE is what gets pinned instead — flat, even, and big
        # enough for the two characters we print onto it. Still a shape and never a field: "plaque
        # for power/toughness" came back carrying a literal "P/T" (2026-08-10).
        # CLIENT 2026-08-16: "the P/T box always comes as a shield, it shall come as per the art
        # not always shield. And that too blank without any symbol in it — Craterhoof has a spiral
        # in it."
        #
        # Two asks. The SHAPE is led by the material rather than left open, because "whichever
        # suits the picture" still came back a shield on 1 of 3 — the model's prior for this field
        # is strong and an open choice does not displace it, the same way an open choice did not
        # displace the reference's staging. Concrete alternatives are given instead, tied to what
        # the scene is made of, so there is something specific to paint.
        #
        # The FACE is stated positively as bare material. "No spiral" is already in the set-symbol
        # ban, and bd mtg-z12's finding is that naming a thing summons it, so this says what the
        # face IS rather than adding a fourth mention of what it must not carry.
        surfaces.append(
            "a small raised tab overlapping the bottom-right corner of the lowest strip. Its "
            "shape comes from what this scene is made of, not from a template — a broken slab "
            "where the scene is stone, a river pebble by water, a torn tag or a hanging seal "
            "where there is cloth, a beaten plate among metal, a knot of wood in a forest, a "
            "disc, a rounded tab. Its face is flat, even, BARE MATERIAL and wide enough to hold "
            "two characters side by side — the value goes on it afterwards, so it is left as "
            "plain stone, plain wood, plain metal with nothing cut or carved into it"
        )
    total = len(surfaces)
    if borderless:
        lines += [
            "",
            # CLIENT 2026-08-13: "the white borders on the first card are not ideal ... what we
            # use to do is type into the custom art notes 'borderless' and try to get no black or
            # white borders, if you can do that it would be by far the best", and of a set of
            # full-bleed ink-sketch cards: "these look the best ... how the cards are reallllly
            # borderless".
            #
            # Stated as a POSITIVE instruction with the ban second, because bd mtg-z12's finding
            # cuts both ways: naming an object summons it, and "no border" is a sentence with a
            # border in it. So the first sentence is what to paint — scene to the trim on all four
            # sides — and only then what must not be there.
            "THE CARD IS FULL BLEED, and this is the most important thing about it:",
            "The picture runs off all four edges of the image. Whatever is at the top edge, the "
            "bottom edge and both side edges is scene — sky, rock, smoke, water, foliage, cloth, "
            "distance — carrying straight off the image the way a photograph does. All four "
            "corners are painted scene too.",
            "Nothing surrounds the picture and nothing encloses it. No rim, no band, no margin, "
            "no outline, no strip of material, no beading and no line of any kind runs around the "
            "outside, and there is no white or black edge anywhere. The artwork is not set inside "
            "anything and is not a picture with a surround: it IS the card, all the way out.",
            # MEASURED 2026-08-13, first generation under this brief: the model obeyed "full bleed"
            # and still built a card, by painting a riveted steel band across the top tenth and
            # insetting the picture in a rectangular window below it. That is bd mtg-9pi's "art in
            # a box" arriving through a different door — the window has no border drawn around it,
            # it is made by the top band plus the strips below.
            #
            # Two things kill it. There is no art window: the scene is the whole card. And no
            # surface reaches the left or right edge, because a plate that runs edge to edge IS a
            # band whatever it was asked to be, and the corners it makes are what read as a border.
            "There is NO ART WINDOW and no inner rectangle: the scene is not a picture placed on "
            "the card with anything above, below or beside it. It fills the card corner to corner, "
            "and the raised surfaces lie ON it.",
            "So no surface reaches the left or right edge of the card. Every one of them stops "
            "short at both ends, with painted scene continuing past it on both sides — for the "
            "plate at the top as much as for the strips below it. A surface that runs the full "
            "width of the card makes a band across it, and a band across the card is the exact "
            "thing this must not have.",
            "",
            # This is what the edge material was doing that the plates now have to do for
            # themselves. MEASURED 2026-08-10: plates asked for with nothing anchoring them came
            # back as three cream rectangles on every card in the batch — the client's own "flat
            # and pasted-on" report. Without an edge to hang off, the anchor has to be that each
            # plate is a THING IN THE SCENE, which is exactly how the ink-sketch cards the client
            # sent do it: every one of their text surfaces is a painted ribbon or banner in the
            # same ink as the art, with the art running behind and through it.
            "THE RAISED SURFACES, and here each one is an OBJECT IN THE SCENE:",
            # "SAME MATERIAL as the art" is kept word for word from the framed branch: a frame
            # overlay on an art window scored 0/3 and read as art in a box (bd mtg-9pi), and with
            # no edge to grow out of, this phrase is the only thing left holding that line.
            "Each surface is a real thing in this world, made of the SAME MATERIAL as the art and "
            "lit by this scene's light — a hanging banner, a torn ribbon of cloth or vellum, a slab of "
            "stone, a plate of beaten metal, a length of bone, a curl of bark, a scroll with a "
            "rod at each end. It has thickness, it catches the light along one edge, and it casts "
            "its own shadow onto whatever is behind it.",
            "The artwork runs behind each surface and past it on both sides.",
            # Every surface on their Craterhoof ends in a carved boss; ours end square, which is
            # what a rectangle laid on a painting looks like. Cheap to ask for and it is the half
            # of the overlap problem that does not depend on the model risking the text area.
            "No surface ends in a square cut. Each one's two ends are finished as part of the "
            "scene — a rod, a carved boss, a knot of vine, a rivet, a torn or frayed edge, a "
            "curled corner — so it looks made rather than cropped.",
            # The client's fourth ask — "creative as to where to place the text" — is only this
            # much freedom, and no more. `cards.compositor` lays out axis-aligned lines and
            # `generation.check` asserts the vertical order, so a diagonal ribbon or a title
            # halfway down the card is not a bolder layout, it is a card the pipeline reports as
            # unsound and repaints. Their own Wheel of Fortune, with rules text on a painted
            # diagonal, is the one card in the reference gallery that is barely readable.
            "They need not span the card's full width and need not be centred: make each one as "
            "wide or as narrow as the composition wants, sitting where it belongs in the picture, "
            "as long as the ORDER down the card is kept and each surface's long top and bottom "
            "edges stay straight and level.",
            # ALL FOUR EDGES, not just the long two. MEASURED 2026-08-16: Swords to Plowshares came
            # back with a torn slab whose right edge sloped inward going down, and the rules text
            # ran off it onto the art. Nothing downstream can catch that — `panels.detect` answers
            # with an axis-aligned rectangle, `compositor` prints into one, and `printable_face`
            # could not find the true edge either, because the art beside that slab was white robe
            # on snow: the same value as the parchment and just as smooth, so there is no boundary
            # to measure.
            #
            # So the shape is constrained instead of the measurement being made cleverer. The
            # ornament that makes a surface look hand-made moves OUTSIDE the flat face rather than
            # eating into it, which is also what the reference site's own slabs do — carved bosses
            # and curled rods at the ends of a straight-sided panel.
            "The flat part of each surface is a straight-sided rectangle — its left and right "
            "edges run straight up and down, the same way its top and bottom run straight across. "
            "Torn corners, curled rods, carved ends and chipped stone all sit OUTSIDE that "
            "rectangle, added around it. A surface that narrows as it goes down loses the text "
            "printed on it.",
            # Straight-sided constrains the OUTLINE, and neither of the two faults below is an
            # outline. Both were measured on the first batch generated under it (bd mtg-cig).
            #
            # PLANE. Elesh Norn's P/T came back a broken stone slab lying flat on the ground,
            # receding away from the camera. "4/7" is composited square onto it, so the number sits
            # on a plane the art says is horizontal and reads as pasted on. It satisfied
            # straight-sided — the slab IS a rectangle — and `panels.detect` and `check` both
            # passed it, because an axis-aligned box cannot express which way a surface faces.
            #
            # EDGE. The pastel Obliterator's rules slab fades into dark mud instead of ending. Row
            # means down its detected box run 111-171 to y0.877, then 82, 54, 39, 34: the painted
            # face stops near y0.885 and the box runs to y0.940, so the last line is set in dark
            # ink on artwork. `printable_face` peels width only and hands that box straight back,
            # `plate_extent` grows the bottom further still, and the card's UNSOUND
            # [panel_too_dark] at 4.53:1 is this defect being sampled rather than a panel that is
            # really too dark. A vertical peel is the fourth-time-cleverer move the 2026-08-16
            # handover warns off; the shape is constrained instead, and the peel stays in reserve.
            "Each flat face is turned square to the viewer, seen straight on the way a sign nailed "
            "to a post is — never lying flat in the scene, never receding into the distance, never "
            "tilted away. A number or a line of text set on a receding surface reads as pasted on.",
            "Every flat face ENDS at a definite edge on all four sides — a rim, a lip, a moulding, "
            "a fold, or a hard change of material. It never fades out, dissolves, crumbles or "
            "blends into the scene behind it. Where the face stops it stops sharply, because text "
            "printed past that point lands on the artwork.",
            f"Paint exactly these {total} raised surfaces and no others: "
            + "; ".join(surfaces)
            + ".",
        ]
    else:
        lines += [
            "",
            # MEASURED 2026-08-10, 24 cards pulled from tcggenerator.com/explore: ~20 of them
            # build the card's outer edge out of the scene's own material and hang the plates off
            # it. That is the whole gap. Ours were three cream rectangles floating on a painting
            # with nothing anchoring them, which is why every card in a batch looked like the same
            # sticker set.
            #
            # bd mtg-z12 logged "a literal rectangular carved frame with a MOUNT, art inset inside
            # it" as a failure. It was right about the word and wrong about the thing. "Border"
            # and "frame" name an object that surrounds a picture, and the model duly supplies a
            # gallery mount. Asked for as material closing in around the scene, the same request
            # produces what their gallery has. So the shape is asked for and the noun is never
            # used.
            "THE CARD'S EDGE — this is what makes it a card and not a picture:",
            "The world's own material closes in around the scene at the card's edge — thick at "
            "the corners, thinner along the sides, never an even width and never a clean "
            "rectangle. Build it from whatever this scene is made of: cracked stone, living wood "
            "and root and vine, corroded iron and gears, bone, coral, ice.",
            # MEASURED 2026-08-10, ours beside the reference site's own Terror of the Peaks:
            # theirs is a hot orange ribbon of lava and ours came back near-black rock, which is
            # what makes the whole card read dark and muddy against theirs. The emissive
            # convention `_palette` already enforces for the scene had never been stated for the
            # edge, and the material list led with "cracked obsidian" — a dark descriptor — so the
            # model painted a dark rim.
            "Run the card's colour through it as LIGHT: molten veins in the stone, sap glowing in "
            "the wood, current in the metal, frost-fire in the ice. It is lit from within, not a "
            "dark rim around a bright picture — after the subject it is the brightest thing on "
            "the card, and it is where the card's colour reads from across a table.",
            "It is grown, not laid on. The scene continues behind it, breaks through where it is "
            "thin, and at one or two points something from the scene — a claw, a tail, a wingtip, "
            "a curl of smoke — crosses in FRONT of it. It runs off all four edges of the image.",
            # MEASURED 2026-08-10, first generation under this brief: the model enclosed the
            # ARTWORK and stopped. Both side members died where the lower surfaces began, the
            # bottom never closed, and the two bottom corners came back as dead black wedges. It
            # encloses the card, and the surfaces are inside it — that has to be said, because
            # "the card's edge" and "around the scene" are the same sentence to a model painting a
            # picture.
            "It encloses the whole CARD, not just the picture: it runs unbroken down both sides "
            "all the way past the lower surfaces and closes across the bottom underneath them, so "
            "all four corners are made of it. The raised surfaces sit INSIDE it and overlap it at "
            "their ends. No corner and no edge of this card is left as empty dark space.",
            "",
            "THE RAISED SURFACES, built from that same material and joined to it:",
            "They must look carved out of the world, out of the SAME MATERIAL as the art, never "
            "like a panel laid on top of a picture. Let the art bleed past and behind them.",
            f"Paint exactly these {total} raised surfaces and no others: "
            + "; ".join(surfaces)
            + ".",
        ]

    lines += [
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
        "TOPMOST thing on the card and "
        # In borderless mode the scene itself runs above and behind the plate, so "touches the
        # upper edge" would fight the full bleed — and the ink-sketch cards the client sent all
        # float their banner just inside the top with art visible above it.
        + ("sits inside its top tenth" if borderless else "touches its upper edge")
        + "; the narrow strip is below the picture; the broad pale strip is below the narrow "
        "strip; the shield, if there is one, is at the bottom right. No surface may be painted "
        "above the top plate.",
        # CLIENT 2026-08-13, circling the second dark strip under Raphael's type line: "on one of
        # them it has 2 creature type text boxes, here it looks kind of natural but i have seen
        # these as errors many times". That card came back with two narrow strips; we printed the
        # type line into the upper one and the lower one stayed blank, which is exactly what a
        # second painted-but-empty surface looks like to a customer. The count was already stated
        # twice and still lost, so an extra surface is now also DETECTED and repainted
        # (`generation.panels`, `generation.check`) rather than only asked against.
        f"That is {total} and only {total}. Do not add one more, do not repeat one, and do not "
        "split a surface into a row of smaller ones — the one broad pale strip is the only place "
        "the rules text goes. In particular there is exactly ONE narrow strip above it: a second "
        "narrow strip, bar or ledge anywhere near it is a failed image. Everything between the "
        "picture and these surfaces is "
        + ("scene" if borderless else "scene or edge material")
        + " — never another plate, tablet, ingot, cartouche or panel.",
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
        # CLIENT 2026-08-16: "some P/T are large some small and small pure black dull ugly".
        #
        # This paragraph governed three surfaces and left the tab — the fourth display surface —
        # to take its value from the art. `compositor.panel_palette` then branched on whatever
        # came back: under luminance 128 the numerals are GOLD, stroked, with a saturated shadow;
        # over it they are unstroked near-black. MEASURED over nine cards, six tabs landed dark
        # (71-126) and three landed pale (151-162), so the same field alternated between the
        # handsome treatment and flat black on grey stone. The threshold is a cliff in the middle
        # of that range, so two near-identical cards flip.
        #
        # Sampling the surface is right for the rules slab, where real cards do print black on
        # parchment. The tab has no such freedom: every Magic card ever printed sets its P/T as
        # light numerals on a dark plate. So its value is pinned like the other two display
        # surfaces, and the compositor needs no change — panel_palette picks gold on its own.
        "The tab at the bottom right is DARK too, the same family as the top plate — dark stone, "
        "blackened metal, dark wood, dark horn — because warm gold numerals are printed on it "
        "afterwards. A pale tab makes those numerals flat black on pale rock, which is the one "
        "part of the card that then looks unfinished.",
        # "Glowing amber stone" used to be in this list and is now excluded by name. MEASURED on
        # the eight-card Ice batch, job 10746c0b: it was the only MID-value entry among otherwise
        # pale materials, and on red and green cards the model reached for it because it matched
        # the scene. Those slabs landed at L=110-133 against 185-210 for the cream ones, taking
        # the printed text to 3.6:1 and 4.5:1 — unreadable at arm's length, and graded sound by
        # every structural check we had. `check.contrast` now enforces the floor; this stops the
        # brief asking for the thing that breaks it.
        "The broad strip is LIGHT AND PALE — warm cream parchment, bleached bone, aged ivory, "
        "weathered chalk. Near-black lettering is printed on it afterwards, so it has to be pale "
        "enough to read that text: think the palest thing in the picture, not a mid-tone. Even on "
        "a night scene or a lava scene it stays pale — a lava card gets a bone-coloured slab lit "
        "warm, NOT a slab made of lava. If in doubt, make it paler.",
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
        "above sits on top of the picture. "
        + (
            ""
            if borderless
            else "The edge material is a narrow margin — no thicker than 1/12th of the card where "
            "it is thickest, and thinner than that along the sides. "
        )
        # Derived from the band above rather than fixed at "a third". Fixed, it CONTRADICTED the
        # per-card strip requirement on wordy cards — the band alone could be a quarter, and a
        # quarter plus the top plate plus the narrow strip is already over a third. A brief that
        # asks for two incompatible things gets one of them at random, which is the same class of
        # bug as bd mtg-cjx.
        + f"The raised surfaces together may cover no more than {_surface_budget(face)} of the "
        "card's height, and the strip is a BAND across the lower third — never half the card.",
        (
            "The raised surfaces may not cover the subject's head, face or silhouette."
            if borderless
            else "Neither the raised surfaces nor the edge material may cover the subject's head, "
            "face or silhouette."
        ),
        "",
        QUALITY,
        "",
        "Put the subject's face and focal point in the UPPER-MIDDLE of the card, clear of the "
        "lower strip. Nothing COMPETES for attention in the lower third — no second subject, no "
        "bright hotspot, no dense detail.",
        # The previous wording — "nothing that matters may sit in the lower third" — is what bd
        # mtg-9ww recorded failing: asked to keep the lower half calm, the model stopped painting
        # and left dead space. Same lesson as the raised surfaces above, one layer further out:
        # legibility needs an EVEN, QUIET CONTINUATION of the scene, not an absence of scene. A
        # blank lower third also loses the client's "not a rectangle inside a frame" requirement,
        # because the art visibly stops where the furniture starts.
        "But the picture CONTINUES through the lower third and out to the bottom edge — ground, "
        "haze, smoke, embers, water, drifting cloth, the scene going quiet at low contrast and "
        "low detail. It never stops into a blank panel, a flat wash or bare canvas. Calm is the "
        "scene continuing softly, not the scene ending.",
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
        "IMAGE — not on the raised surfaces, "
        + ("not anywhere in the artwork" if borderless else "not on the edge material")
        + ", and not in the gaps between them. Every raised surface is bare stone, bare wood, "
        "bare metal — blank. No letters, no words, no names, no titles, no numbers, no glyphs, no "
        "decorative script, no fake writing, no watermark, no emblem, no mana symbols, no set "
        "symbol. If you are tempted to label a surface or carve script into it, leave it empty "
        "instead. Real text is printed onto these surfaces afterwards and anything you paint on "
        "them will collide with it.",
        # CLIENT 2026-08-13, circling the swirl beside the reference site's own type line: "these
        # are set symbols, to know which set the cards from, but these are proxies that dont have
        # a set so its just a random symbol and actually sometimes ive seen it put a real symbol
        # on the card which isnt good, but if we can not have these generate that would be great."
        #
        # It was already one item in the list above and the list is twelve items long, which is
        # the same distance problem the rune sentence was created to solve. A real symbol is the
        # worse case of the two: an invented swirl is meaningless, a real expansion symbol is a
        # Wizards mark printed on a proxy. So it gets its own sentence, and it names the PLACE it
        # appears — the model is reproducing a card layout it has seen ten thousand times, and the
        # slot is more load-bearing than the shape.
        "NO SET SYMBOL. A real Magic card carries a small expansion symbol at the right-hand end "
        "of its type line; this card belongs to no set, so that slot stays EMPTY. Paint no small "
        "badge, emblem, gem, seal, crest, sigil, rune-circle, spiral or logo at either end of any "
        "surface, in any corner, or anywhere in the artwork. Where one would sit, paint the "
        "surface's own plain material.",
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
    def before_the_writing_ban(sentence):
        """Insert late, but never after the lettering ban — that ban's last place is measured.

        Located by looking for the ban rather than counting back from the end: a clause was once
        inserted at len(lines) - 1 and silently moved AFTER it the day a rune sentence was
        appended, which is the exact position these comments say it must never take.
        """
        lines.insert(
            next(
                index
                for index, line in enumerate(lines)
                if line.startswith("ABSOLUTE REQUIREMENT")
            ),
            sentence,
        )

    # CLIENT 2026-08-15, sending a card whose vines cross its own title arch: "you see how this
    # card feels like 1 piece of art ... the examples you showed me ... dont have an abstract text
    # box design."
    #
    # This brief already asked for it, inside the surfaces paragraph: "at one or two points
    # something from the scene ... crosses in FRONT of one". MEASURED 2026-08-16 on the two cards
    # the client was sent — ZERO overlaps on either, against vines over the title plate and roots
    # over the rules panel on the reference site's own Craterhoof of the same card
    # (Project Material/evidence-reference-frames-2026-08-16/).
    #
    # So this is the same lesson the top-plate clause above records, for the third time: a soft
    # sentence ("one or two", "something") in the middle of a long paragraph does not survive. It
    # is compulsory now, it names a count, and it is repeated late and alone.
    #
    # Only in the borderless branch. The framed branch has the edge material anchoring the plates,
    # which is what this clause substitutes for, and it has not drawn the complaint.
    if borderless:
        before_the_writing_ban(
            "AND: THE OVERLAP, which is what makes the card read as ONE piece of art instead of a "
            "picture with labels laid on it. At least TWO of the raised surfaces have a real "
            "element of the scene crossing in FRONT of them — a vine, a creeping root, a claw, a "
            "limb, a wingtip, a tail, a curl of smoke, a lick of flame, a hanging chain. Not a "
            "shadow and not a glow: a solid thing, drawn in the same ink and lit by the same light "
            "as the rest of the picture, passing over the surface and continuing out the other "
            # The hard boundary. `cards.compositor` prints into each surface's interior, so an
            # element crossing the middle of the pale strip lands under our own rules text and
            # `check.contrast` fails the card into a repaint — trading the client's complaint for
            # a legibility one. Overlapping the rim is free; overlapping the face costs a credit.
            # Stated as geometry rather than as a ban, because bd mtg-z12's finding is that naming
            # a thing summons it.
            "side. Each crossing stays at that surface's OUTER EDGE or over one of its corners: "
            "the broad flat middle of every surface stays completely clear and unbroken, because "
            "that is where the card's text is printed. "
            # MEASURED 2026-08-16, first batch under this clause: Craterhoof's vine crossed a
            # quarter of the way along the top plate. `panels.detect` is asked to keep what
            # crosses in front OUT of the box, did so correctly, and the box that came back
            # started at x=0.27 — so the name was laid out from there and sat visibly off-centre
            # on a plate that runs nearly the full width. The clause worked and the card looked
            # wrong, which is the cheapest kind of bug to catch and the easiest to leave in.
            #
            # The top plate is the one surface where this costs something, because it is the only
            # one whose text is left-aligned rather than centred, and it is the sliver a fanned
            # hand shows. So its crossing is pushed out to the very end.
            "On the plate across the top, keep any crossing within a sixth of one end or the "
            "other. The long middle of that plate carries the card's name and must be clear "
            "right across it."
        )

    # INSERTED BEFORE THE TOP-PLATE CLAUSE, and the order is load-bearing. These insert in call
    # order, so whatever is added last sits closest to the lettering ban at the end. MEASURED
    # 2026-08-16: with the overlap clause added AFTER the top plate's, 3 of 6 cards in one batch
    # failed on the top plate — twice with no title surface painted at all, once with the plate
    # at y=0.58 — against 0 of 3 before it. Pushing that restatement one clause further from the
    # end was enough to break it, which is the third time this file has measured the same thing.
    # MEASURED 2026-08-15, bd mtg-8h9 — the first diagnosis made possible by keeping the blank
    # (bd mtg-57t). Elesh Norn came back with all four surfaces painted in the right ORDER and all
    # four crammed into the bottom 45% of the card: the name plate landed at y=0.556 and
    # `check.title_out_of_order` failed it. Job c66d6b93 did the same on the same card before that.
    #
    # The placement is already stated once, in the middle of the ~100-word sentence that lists the
    # four surfaces, and it lost there. This file has learned the same lesson twice — the lettering
    # ban had to move to the very end before it held on 3 of 3 — so it is repeated late and alone.
    #
    # The REASON is given rather than just the rule, because the reason is a real constraint a
    # model can reason from: a hand of cards is held fanned, so the name is the only part of most
    # of them that is visible at all. Nothing the compositor can do repairs this — we print onto
    # the plates that were painted, and inventing one is the pasted-on rectangle the client
    # rejected (bd mtg-vbo), so the brief is the only lever there is.
    # Worded in SHAPES — "the top plate", "the broad pale strip" — and never as the fields they
    # will carry. Naming a field invites filling it: "title banner" came back with a painted title
    # and "plaque for power/toughness" with a literal "P/T" (2026-08-10), and
    # `test_surfaces_are_described_as_shapes_not_as_fields` is what holds that line. The first
    # draft of this very clause broke it.
    before_the_writing_ban(
        "AND: THE TOP PLATE SITS AT THE TOP OF THE CARD. Its upper edge "
        + ("is inside the top tenth of the image, with the picture running behind it"
           if borderless else "touches the upper edge of the card")
        + ". Filling the upper half of the card with picture and then stacking all three "
        "surfaces together down the lower half is the single most common way this image comes "
        "back wrong, and it is wrong even when their order is right. These cards are held fanned "
        "in one hand, so the top sliver of each is the ONLY part of it anyone can see — a top "
        "plate lower down makes a card nobody can pick out of a hand."
    )

    if "B" not in (face.get("color_identity") or []):
        before_the_writing_ban(
            "AND: no purple, violet, magenta or lilac anywhere in this image — not in the art, "
            "not in the light, "
            + ("" if borderless else "not in the edge material, ")
            + "not in any surface. Purple reads as black mana and this card is not black."
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
        lines += ["", REFERENCE, _staging(face)]
    if style:
        lines += [
            "",
            f"Art style: {_style_text(style)}. This governs the whole picture — the "
            f"world it is set in, the light, the palette and the finish. {STYLE_TIEBREAK}",
        ]
    if direction:
        lines += ["", f"Composition: {_catalogue_text(direction, DIRECTIONS)}."]
    if palette:
        lines += ["", _palette_clause(palette, face.get("color_identity") or [])]

    lines += [
        "",
        QUALITY,
        "",
        "Output ONE full-bleed illustration that fills the entire frame, edge to edge, "
        "with the subject clear of the edges.",
        f"Paint the art and nothing else: {FORBIDDEN}.",
    ]
    return "\n".join(lines)
