"""Print the real card text onto the AI's empty raised surfaces, with real type treatment.

The AI paints art and blank furniture (`generation.prompts.creative_full`); a vision pass says
where the surfaces landed (`generation.panels`); this draws Scryfall's own text into them, so the
text is correct by construction — the model writing its own type line produced a fabricated
subtype in the right font (bd mtg-9pi).

MEASURED 2026-08-10, our Terror of the Peaks beside the reference site's own version of the same
card: dropping flat text into a box does not survive the comparison. Every glyph on theirs carries
a stroke scaled to its size and a blurred drop shadow under it; the name, type line and P/T are
embossed, a dark edge below and a light edge above; and their display text is warm gold on the
dark banner rather than plain white. A one-pixel halo, which is what this module started with, is
invisible at 70px and reads as cheap.

So text is built up in layers per panel — shadow or glow, stroke, fill — with one blur per panel
rather than one per glyph, which is what keeps it affordable across a 100-card deck. The emboss that
sentence used to name was removed 2026-08-17: measured across the reference site's own light-on-dark
titles the halo is symmetric, not a bevel. See the note above `TRACKING`.

REVISED 2026-08-10 against their FULL-RESOLUTION original rather than a gallery thumbnail: the
type treatment here is close and the remaining gap is not a blend effect, it is SIZE and LAYOUT.
See the note above `_stamp`, and `generation.panels` for the multi-panel finding.
"""

import colorsys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageStat

from cards import fonts, symbols, textlayout

PAD = 0.055
# The rules panel pads tighter than the display plates, because it is the only surface whose
# padding was doing TWO jobs and now only has one.
#
# PAD's own comment records the first: "the plate the detector reports includes the carved rim, so
# a fraction of it is already conservative". `printable_face` now measures that rim off the box
# instead of budgeting for it, so on this panel the margin is pure optical breathing room.
#
# MEASURED 2026-08-16 on the three staged Craterhoofs and the rod card. The rules panel is the one
# place the margin is expensive, because `textlayout.fit_across` steps the type size down until
# the block fits the box HEIGHT — so padding comes straight out of legibility:
#
#   PAD        run1 fit 46 (UNSOUND)   run3 51   rod 53
#   RULES_PAD  run1 fit 48 (passes)    run3 53   rod 56
#
# run1 passes at exactly RULES_MIN, which is a pass and not a margin. The durable fix is the brief
# asking for the flat pale FACE to be tall enough rather than the whole ornamented piece — see
# bd mtg-8h9, changed the same day and still unverified.
RULES_PAD = 0.035
# Name and type line, as a fraction of CARD height. CLIENT 2026-08-17, on the sign-off pack:
# "small somewhere large somewhere".
#
# These used to be fractions of the detected PLATE's height — 0.68 and 0.66 — which is the same
# bug `_pt_size` below was fixed for a day earlier, and the same argument applies unchanged: the
# plate is whatever the model painted, so the spread is in the multiplicand and no fraction can
# narrow it. MEASURED over every stored face that kept its boxes (n=58 name, n=59 type), replaying
# the old sizing exactly, as a fraction of card height:
#
#                 bottom quartile      median     top quartile      spread
#   card name     0.0292 - 0.0367      0.0396    0.0437 - 0.1054     3.61x
#   type line     0.0229 - 0.0304      0.0342    0.0383 - 0.0496     2.16x
#
# The name's 0.1054 is a title box that swallowed the art; after the width fit in `_title` cut the
# worst of those back the name still ran 0.0292 - 0.0600, 2.06x, on cards of identical size.
#
# So the size comes from the CARD and the plate only ceilings it. FITTED by sweeping candidates
# back over those same 58 faces — every real detected plate, every real mana cost, every real type
# line — and reading off the spread each one leaves. The target cannot simply be the old median:
# a plate has to be about 1.3x the type size to carry it, and the short tail of real plates then
# clamps, which is spread again from the other end.
#
#   name   0.034 -> 1.02x   0.036 -> 1.08x   0.038 -> 1.14x   0.040 -> 1.20x
#   type   0.030 -> 1.04x   0.032 -> 1.12x   0.034 -> 1.19x
#
# So each constant is the largest that holds the spread under 1.15x, because the one directional
# complaint on record about ABSOLUTE size points up: on 2026-08-10 ours were raised after theirs
# were measured filling their plates while ours sat in a ring of bare stone. Against the old
# medians this costs the typical card 4% of its name and 6% of its type line.
#
# The type figure excludes Elesh Norn's `Legendary Creature - Phyrexian Praetor`, 38 characters and
# the longest type line in the archive: it is the ONE card in 59 the width fit had to cut, and it
# was cut on all ten paintings of it, on plates from 0.562 to 0.880 of the card. No plate the model
# painted could hold it at target, so no gate would help and a repaint would not either. It needs a
# region wider than any painting gives — which is the fixed layouts in docs/COMPOSITION-LAYER-
# FIXES.md, not a number here.
NAME_CARD_SIZE = 0.038
TYPE_CARD_SIZE = 0.032
# Ceiling only, as a fraction of the plate, so a genuinely short plate still contains its text.
# Beleren Bold's ascent+descent is 0.94 of its em, so 0.80 puts the glyph band at 0.75 of the
# plate — inside the 0.64 the old 0.68-of-plate produced and well clear of clipping. It binds on
# 1 of the 57 shippable faces; at 0.75 it binds on 4 and buys nothing.
#
# NO FLOOR, unlike P/T. A floor stops a value looking lost on a generous tab; here the generous
# boxes are detection failures — the two 0.13 and 0.155 title boxes in that population swallowed
# the art — and forcing those up to a floor would put back exactly the spread this removes.
NAME_MAX_OF_BOX = TYPE_MAX_OF_BOX = 0.80
# Lettered-mode pips. Size is from the CARD, same as the composited path — a 37px painted name
# (Tromell, live pack 2026-08-19) is the model's lettering, not a reason to stamp 37px stickers
# into a 160px well. Vertical placement still follows the ink (`_letter_band`). Horizontal
# placement follows the plate's INNER face (`_plate_face_right`), not the detector box: that box
# includes the carved black bevel, and 50px of card-width inset still landed the pips on it.
#
# How much brighter (dark plate) or darker (pale plate) a row's ink percentile has to sit than the
# plate before it counts as lettering. 25 is the gap on the live pack: gold p90 ≈ 180 against a
# plate at ~30, and empty padded rows stay within a few values of the plate.
LETTER_INK = 25
# Gap between adjacent pips, as a share of pip diameter. The Scryfall SVGs are full-bleed circles
# (r=50 on a 100 viewBox), so 0.00 would kiss. 0.14 is a clear hairline of plate — and it only
# reads as a gap if the pips are NOT then run through the Beleren glow; that blur was what made
# {2}{G} look like one smashed oval on Tromell.
PIP_GAP = 0.14
# Optical pad inside the inner face, as a share of pip diameter. Real cards sit the last pip
# about a quarter of a pip in from the frame; 0.28 still read as flush on the 2026-08-19 pack
# (Progenitus, Craterhoof) once the well was the inner face. 0.40 is a visible hairline of plate.
PIP_RIGHT = 0.40
PIP_MIN_OF_TARGET = 0.75
# How far past a truncated title box we may walk, in pixels, across a painted
# seam. Kitchen Finks' cost box sat 8-16px past the detector's x1; a wider gap
# is art, not the rest of the plate.
PLATE_SEAM = 24
# Air between the painted name and the first pip, as a share of CARD width.
COST_NAME_GAP = 0.02
# Collision-gate budget for rim + optical pad, as a share of CARD width, for callers that have
# boxes and no pixels (`check.cost_collides`). Measured Tromell bevel was 69px / 1792 ≈ 0.038.
COST_RIGHT_INSET = 0.045
# Right-hand rim peel. A flat black bevel has no STRUCTURE, so `printable_face` leaves it. The
# face is the first sustained run of columns whose mean looks like the plate's interior.
FACE_RIGHT_MIN = 0.70
FACE_RIGHT_RUN = 8
FACE_RIGHT_MAX_PEEL = 0.22
# Inside-out walk: a stop after this much of the strip was face is a rim, even
# if the detector box then runs 100px into a gothic frame (Progenitus, 26% of
# the strip — over FACE_RIGHT_MAX_PEEL, so a peel-cap would reject the real edge).
FACE_RIGHT_MIN_SPAN = 0.55
# THE SIZE THE BODY TEXT IS SET AT, in px, taken from the CARD and not from the panel.
#
# The same fix the name and type line got on 2026-08-17 and the P/T on 2026-08-16, for the same
# symptom and by the same argument: the panel is whatever the model painted, so a size derived
# from it inherits the model's variance and no fraction can narrow that. This is the third and
# last surface to get it.
#
# It used to be a CEILING of 0.055 of card height — 132px — raised from 0.030 on 2026-08-10
# because the text "sat at half the size and floated in empty stone". That fixed the floating and
# created the opposite defect, because `fit_across` starts at the ceiling and only comes down: a
# card with one line of text takes the whole 132px. MEASURED 2026-08-17 over the composited
# regression run, exactly, from the layout engine rather than from pixels:
#
#   Sol Ring     132px  (1 line,  35% panel fill)   Craterhoof 68px (5 lines)   Terror 53px (6)
#
# 2.5x across three cards of one deck. Meanwhile `generation.prompts` was already asking the model
# for a panel sized to hold each card's text at `textlayout.target_size` — 61px, measured over 40
# real printed cards — so the brief and the compositor were two halves of one contract that had
# never been introduced. They now read the same number.
#
# It stays a ceiling, not a fixed size: a card whose panel cannot hold its text at 61px still
# steps down, and `RULES_MIN` below still reports it. What is gone is stepping UP.
RULES_SIZE = textlayout.target_size(2400) / 2400
# Power/toughness. CLIENT 2026-08-16: "some P/T are large some small".
#
# This used to be a fraction of the TAB's height alone, and the tab is whatever the model painted:
# MEASURED over nine cards the same day, `panels.detect` returned P/T boxes from 0.050 to 0.180 of
# card height, so the numerals ran 74 to 268 px on identically sized cards. Moving the fraction
# moved all nine together and narrowed nothing, because the spread is in the multiplicand.
#
# So the size comes from the CARD and the tab only clamps it. PT_CARD_SIZE is fitted between the
# two populations in that batch: the cards that read well sat at 149-179 px (0.062-0.075 of card
# height) and the ones the client called small sat at 74-89 (0.031-0.037). The clamp keeps the
# numerals inside a tab that is smaller or larger than the target, which is what stops this
# reintroducing overflow on the small tabs it exists to help.
PT_CARD_SIZE = 0.068
PT_MIN_OF_BOX, PT_MAX_OF_BOX = 0.45, 0.85


def _pt_size(box, card_height):
    """P/T cap height: taken from the card, clamped to the tab it is printed on."""
    height = box[3] - box[1]
    return max(11, round(min(max(card_height * PT_CARD_SIZE,
                                 height * PT_MIN_OF_BOX), height * PT_MAX_OF_BOX)))


def _plate_size(box, card_height, card_fraction, max_of_box):
    """Display type on a plate: taken from the card, ceilinged by the plate it is printed on."""
    return max(11, round(min(card_height * card_fraction, (box[3] - box[1]) * max_of_box)))
# Below this fraction of card height the type is too small to be read across a table, and the
# real cause is a slab the AI painted too small — Craterhoof came back with visibly smaller text
# than three other cards in the same batch. Type size varying card to card is worse in a deck
# than one tight card, so it is reported like overflow and the art gets regenerated.
#
# RE-MEASURED 2026-08-10, after the brief started asking for an enclosed card edge. 0.024 was
# calibrated against a full-bleed slab ~1600px wide. Inside the edge material the slab is ~1458px,
# so the same text wraps to more lines and fits at a smaller em — Terror of the Peaks fitted at
# 55px into a 522px box needing 518px, and was flagged as too small at a floor of 57.6px. That is
# a false positive that costs a regeneration: measured against the reference site's own cards,
# their rules text runs at pitch/cardH 0.031 and ours at that size runs at 0.0304, i.e. their
# cards would trip the old floor too. The floor has to sit BELOW the look we are matching.
#
# VALIDATED 2026-08-15 (bd mtg-8h9) against n=40 real printed
# 2015-frame cards spanning 13-336 oracle characters, measured off Scryfall's own 745x1040 PNGs by
# pixel projection. The comparable is LINE PITCH as a fraction of card height, not font size: real
# cards are set in Plantin and we ship PT Serif, whose x-height per em differs, so equal font sizes
# are not equally readable.
#
#   this floor            2.625%   (48px on a 2400px card)
#   smallest real card    2.788%   The One Ring, 305 chars, 7 lines = 1.06x this floor
#   median real card      3.317%
#   0 of 40 real printings set their rules text below it.
#
# So the guess was right to within 6% of the tightest thing Wizards prints. DO NOT RETUNE IT to
# make failing cards pass — a card that trips it is genuinely below anything a real printing uses,
# and the defect is upstream: the surface the model painted is too short for the text.
# `prompts._strip_height` is what asks for a surface big enough, using the same measurement.
RULES_MIN = 0.020

# NO LINE SPREADING. Tried 2026-08-10 to fill a strip the text did not reach the bottom of, and
# it is the wrong direction by the same measurement that motivated it: ink-to-pitch is 0.49 on
# their card against 0.385 on ours, so theirs carries LESS air per line, not more. Adding leading
# lowers that ratio further, and on a two-line ability at 0.55 it read as two loose lines rather
# than a paragraph. A strip fills because its glyphs are big, not because its lines are far apart
# — which is what `_assign` packing by capacity actually buys.

# All as fractions of the font size, so they hold at any panel size.
STROKE = 0.055
SHADOW_OFFSET = 0.055
SHADOW_BLUR = 0.045
EMBOSS = 0.030

# NO HALO, NO SOFTENING, NO GLOW — and this is a measurement, not a preference.
#
# A contact halo and a sub-pixel blur were added on 2026-08-10 from a reading of their card that
# was taken off a 597x800 gallery THUMBNAIL upscaled 3x. The softness and the halo were both JPEG
# and resampling artefacts of that thumbnail. Their full-resolution original is public at
# cdn.proxyprintery.de/ai_proxy_cards/<uuid>.png and it is 1792x2400, the same canvas as ours.
#
# At 1:1 their rules text is FLAT BLACK, hard-edged, and carries no shadow and no halo at all.
# Measured as the 99th-percentile horizontal luminance gradient across stroke edges, which is
# how hard an edge is: theirs 169, ours 113 before the halo, ours 63 after it. Their text is
# sharper than ours ever was, so both passes moved us away from the target and the halo cost
# nearly half the edge contrast. Removed.
#
# What is left — stroke, cast shadow, emboss — was measured at card size and stays. The gap that
# is real is SIZE: their body x-height is 34px against our 24px on the same canvas.
#
# SUPERSEDED 2026-08-17 for the emboss, on the same axis and a wider sample. The 2026-08-10 reading
# was one card; measured across the reference site's light-on-dark titles, the ring 4px out is
# BRIGHTER than the plate on both sides of the glyph (+15/+18 and +32/+15, asymmetry 3.2 and 16.7).
# That is a symmetric halo of the letter's own light, not a bevel. Ours read -36 above-left against
# +19 below-right, asymmetry 54.8 — three times their worst. The emboss is gone from the display
# text and the dark cast shadow under light lettering is now a centred glow (`GLOW_ALPHA`).

# Negative tracking, as a fraction of the font size. Real card titles are set tight; Pillow has
# no letter-spacing, so display runs are drawn glyph by glyph to get it.
TRACKING = -0.018

SHADOW_ALPHA = 165

GLOW_ALPHA = 110
"""Alpha of the halo under LIGHT lettering on a dark plate, in place of a cast shadow.

Set so the ring 4px out lands +15 to +30 over the plate, which is where the reference site's own
light-on-dark titles measured on 2026-08-17 (Grazilaxx +15/+18, Spellskite +32/+15). Lower than
`SHADOW_ALPHA` because a halo that reads as bright as the letter turns the letter into a blob —
the job is to lift the plate away from the glyph, not to outline it.
"""

# Warm gold for display text on a dark surface: their type line is gold on near-black lava, and
# plain white reads as a screenshot rather than a printed card.
GOLD = (248, 227, 176)


def _hsv(h, s, v, alpha=None):
    r, g, b = (round(c * 255) for c in colorsys.hsv_to_rgb(h, max(0.0, min(1.0, s)), max(0.0, min(1.0, v))))
    return (r, g, b) if alpha is None else (r, g, b, alpha)


def _mean(image, box):
    x0, y0, x1, y1 = box
    ix, iy = round((x1 - x0) * 0.2), round((y1 - y0) * 0.2)
    patch = image.crop((x0 + ix, y0 + iy, max(x0 + ix + 1, x1 - ix), max(y0 + iy + 1, y1 - iy)))
    return patch.convert("RGB").resize((1, 1)).getpixel((0, 0))


def light_direction(image):
    """Which way shadows fall, from where the art is brightest.

    Their shadows fall consistently away from the scene's light, which is part of why the text
    reads as printed on the card rather than pasted over it. Comparing half-brightnesses is
    enough — the sign is all that matters, and it costs one downscale.
    """
    small = image.convert("L").resize((32, 32))
    px = small.load()
    left = sum(px[x, y] for x in range(16) for y in range(32))
    right = sum(px[x, y] for x in range(16, 32) for y in range(32))
    top = sum(px[x, y] for x in range(32) for y in range(16))
    bottom = sum(px[x, y] for x in range(32) for y in range(16, 32))
    return (1 if left >= right else -1), (1 if top >= bottom else -1)


def panel_palette(image, box, display=False):
    """(ink, stroke, shadow) sampled from this surface, in the surface's own hue.

    MEASURED 2026-08-10 against the reference site: neutral values are what make composited text
    look digital. Their ink is a warm near-black carrying the parchment's own hue rather than
    #000, and the shadow under it is a darker, more saturated version of the panel rather than
    grey. Both are derivable from the pixels, so neither needs to be asked of a model — asking
    would trade a measurement for a guess, and a hallucinated ink colour is an unreadable card.
    """
    r, g, b = _mean(image, box)
    h, sat, val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if 0.2126 * r + 0.7152 * g + 0.0722 * b < 128:
        # Light text on dark material: keep a trace of the panel's hue so it belongs to the card,
        # and stroke it, because dark painted texture will otherwise eat the glyph edge.
        ink = GOLD if display else _hsv(h, sat * 0.10, 0.97)
        if display:
            # NO BLACK STROKE ON DISPLAY TEXT, and this is the difference the client circled on
            # 2026-08-17 ("their text completely satisfies the style and blends in"). At
            # STROKE=0.055 and a 91px name that is a FIVE-PIXEL black outline drawn around every
            # gold letter, and it is what the ring measurement below was actually finding.
            #
            # The stroke's job — stop dark painted texture eating the glyph edge — is real and is
            # kept. It is done in the direction of the letter instead of against it: a soft halo of
            # the letter's own light, which is what the reference site does. Body text is NOT
            # changed; on a dark rules panel a black stroke round pale text is load-bearing for
            # legibility at body size, and `check.contrast` is the gate that watches it.
            return ink, None, _hsv(h, sat * 0.12, 1.0, GLOW_ALPHA)
        # A GLOW AND NOT A CAST SHADOW, and this is the difference the client circled on 2026-08-17
        # ("their text completely satisfies the style and blends in").
        #
        # MEASURED that day, as the brightness of a 4px ring around the glyph against the plate it
        # sits on, sampled up-left and down-right so an asymmetric treatment shows up as asymmetry:
        #
        #                        above-left   below-right   asymmetry
        #     THEIRS Grazilaxx      +15.0         +18.2          3.2
        #     THEIRS Spellskite     +31.8         +15.1         16.7
        #     OURS                  -36.0         +18.8         54.8
        #
        # Theirs is BRIGHTER on both sides — light lettering carrying a soft halo of its own light,
        # which is why it reads as part of the plate. Ours was dark on one side and light on the
        # other at three times their worst asymmetry, which is a bevel stuck onto the glyph, and a
        # bevel is what makes composited type look like a sticker from another product.
        #
        # Dark text on a PALE plate keeps its dark shadow below — see the branch after this one, and
        # their own pale-plate cards, where the lettering is flat dark on flat cream.
        return ink, (0, 0, 0, 235), _hsv(h, sat * 0.12, 1.0, GLOW_ALPHA)
    # Dark text on pale material: no stroke. A light stroke at 5.5% of the glyph size eats the
    # letterform from outside and black ends up reading grey.
    return (
        _hsv(h, min(1.0, sat * 1.7), val * 0.12),
        None,
        _hsv(h, min(1.0, sat * 1.5), val * 0.42, 150),
    )


# How far below its own paper a pixel has to sit before it counts as something painted IN FRONT of
# the surface rather than as the surface's own tone, and the range over which that judgement fades
# in. A ramp and not a threshold, because a vine the model painted has its own antialiased edge and
# a hard cut puts a stair-step outline around it when it goes back over the text.
#
# MEASURED 2026-08-17 on the three stored blanks of the composited regression run. At 0.30 the mask
# takes the vines crossing Craterhoof's scroll and the branch crossing Terror's slab, and takes
# nothing at all on Sol Ring, whose panel is clean — which is the discrimination this needs. Below
# 0.20 the parchment's own shading starts coming back as foreground; above 0.40 the thinner vines
# drop out.
OCCLUDE_DEPTH = 0.30
OCCLUDE_RAMP = 0.12


def _paper(grey):
    """The value of this surface's own paper.

    The 90th percentile and not the mean: the mean is what `check.contrast` measures, and a mean is
    exactly what a vine painted across a pale panel hides inside — Craterhoof's scroll reads 211
    with a vine through it and 222 without, a difference no threshold can sit in. A high percentile
    asks "what is this surface when nothing is on it", which is the question.
    """
    histogram = grey.histogram()
    target = 0.90 * sum(histogram)
    running = 0
    for value, count in enumerate(histogram):
        running += count
        if running >= target:
            return value
    return 255


def foreground_mask(surface):
    """Soft mask of everything painted in front of this surface's own paper.

    LIGHT SURFACES ONLY. On a dark slab the foreground is whatever is *lighter* than the material
    and this returns the material itself, so callers gate on `surface_is_dark` first. Not
    generalised here because no stored blank has painted foreground crossing a dark slab, and an
    untested inverse branch is a second way to be wrong rather than a feature.
    """
    grey = surface.convert("L")
    paper = _paper(grey)
    low = round(paper * (1 - OCCLUDE_DEPTH))
    span = max(1, round(paper * OCCLUDE_RAMP))
    return grey.point(lambda v: 0 if v >= low else min(255, round(255 * (low - v) / span)))


def _box(panel, size):
    """Panel in 0-1 fractions -> pixel box, clamped to the canvas."""
    w, h = size
    x0, y0, x1, y1 = panel
    x0, x1 = sorted((max(0, round(x0 * w)), min(w, round(x1 * w))))
    y0, y1 = sorted((max(0, round(y0 * h)), min(h, round(y1 * h))))
    return x0, y0, x1, y1


# How much a boundary line may vary ALONG ITS OWN LENGTH before it is treated as rim, ornament or
# something crossing in front rather than as printable face.
#
# MEASURED 2026-08-16 on Craterhoof's scroll, the card whose text printed onto the rod. Scanning
# the rules box column by column, in grey levels:
#
#     parchment face   median 244-245   sd 0.4 - 2.7
#     the curled rod   median 131-234   sd 64  - 90
#
# The two populations do not touch, so the threshold is put in the gap rather than fitted to
# either edge of it — the same way CONTRAST_MIN sits between its two clusters.
#
# It is the SPREAD and not the mean because the mean does not separate them: a face can be lit
# across a gradient, stained, or dark on one surface and pale on the next, while ornament is
# ornament because it has structure — an edge, a shadow, hatching. That also makes one threshold
# work for the DARK title plate and the PALE rules slab, which no value-based test can do.
#
# BUT AN ABSOLUTE NUMBER IS STYLE-DEPENDENT, and a fixed 16 was wrong. MEASURED 2026-08-16 on
# three Ink Drawing Craterhoofs: that style hatches every surface, so the FACE reads as structured
# too, the peel ran to its cap on 5 of 9 surfaces, and 2 of the 3 cards came back UNSOUND
# [text_too_small] — the peel had taken the room the model had correctly left for the text. The
# one card whose surfaces happened to be smooth peeled 90-96% and passed.
#
# So the threshold is taken from the surface's OWN interior instead. Ornament is not "textured",
# it is textured RELATIVE TO the thing it sits on, which is true of a smooth parchment with a
# carved rod and of a hatched ink panel with a heavier hatched rim alike.
FACE_RATIO = 3.0
# A floor, so a perfectly flat synthetic surface (baseline ~0) does not treat its own noise as
# ornament and peel itself away.
FACE_FLOOR = 6.0
# Peeling is capped so a misread can never eat the surface. A rim this wide is not a rim, and a
# box that wrong is better printed on and reported by `check` than silently shrunk to nothing.
#
# LOWERED FROM 0.30, 2026-08-16. At 0.30 the pathology this cap exists to stop was slipping under
# it. A Phyrexian Obliterator came back with a smoke plume and a branch crossing the left of its
# rules parchment — which is THE OVERLAP the brief explicitly asks for — and the scan read 414 of
# its 447-column limit as rim. The card graded SOUND and shipped with its text jammed into the
# right two-thirds of a large empty parchment: no gate fires, and it is exactly the "layers pasted
# together" look the client reported.
#
# Measured over every stored blank that has a detection beside it (n=8, and biased — blanks are
# only kept on cards that graded unsound, so this is the hard end of the population):
#
#     plausible rims     0.006  0.007  0.036  0.037  0.058  0.075  0.084  0.103  0.106  0.154  0.181
#     scan ran away      0.257  0.292   (one Elesh Norn, 0.549 of its panel width between them)
#
# 0.20 sits in that gap. It keeps every rim the scan has ever found legitimately and rejects both
# runaways, and the Obliterator's 0.277 now returns the box untouched.
#
# REVISE THIS if a card turns up whose real rod or torn end is genuinely a fifth of the panel — the
# sample above is small and one-sided. The symptom would be text starting ON the rim again, which
# is the fault `printable_face` was written for in the first place.
FACE_MAX_PEEL = 0.20


def printable_face(image, box, ratio=FACE_RATIO):
    """`box` shrunk to the flat interior text can actually sit on.

    MEASURED 2026-08-16 (bd mtg-1uv and its siblings): `panels.detect` reports the whole painted
    OBJECT, and the part we can print on is a rim's width inside it. Craterhoof's rules text came
    back printed onto the scroll's curled rod — "Haste", "control", "end of turn" all beginning on
    the rod rather than the parchment — and the same fault is what puts a P/T on a shield's bright
    rim and mana pips over a plate's edge. One box, three surfaces, one bug.

    `panels.py` already ASKS for the inner usable area and is ignored; that instruction has now
    failed on four surfaces, so this is measured from the pixels instead of requested again.

    The invariant is UNIFORMITY, not value. Only the rules strip is pale — `check.contrast`
    enforces that at 5.0:1 — while the title and type plates are briefed DARK, so a "find the pale
    part" scan would peel a title plate away entirely. What every printable face does share is that
    it is EVEN, which the brief states outright: "keep that band even in value so printed letters
    stay readable". Rim, rod, carved boss and a vine crossing in front are all things that DIFFER
    from that interior, whichever direction they differ in.

    So: measure how much structure this surface's OWN interior carries, then peel inward from each
    edge while the boundary line carries much more than that. A clean rectangular plate peels
    nothing, and a surface whose face is as busy as its rim peels nothing either — see below, that
    outcome is deliberate.
    """
    x0, y0, x1, y1 = box
    if x1 - x0 < 8 or y1 - y0 < 8:
        return box  # too small to sample; the caller's own guards cover it
    region = image.crop(box).convert("L")
    width, height = region.size

    # Each line is sampled over its own middle half, never its full length. A column read top to
    # bottom crosses the surface's own top and bottom ornament, so EVERY column comes back
    # structured and the peel runs to its cap — measured, on all four surfaces of all three cards.
    # The middle half is the part no perpendicular edge can reach, which is the same reason the
    # colour reference in `surface_is_dark` is taken from the middle.
    ymid0, ymid1 = height // 4, height - height // 4
    xmid0, xmid1 = width // 4, width - width // 4

    def spread(line):
        return ImageStat.Stat(line).stddev[0]

    # What this surface's own face looks like, sampled down the middle where no rim reaches.
    baseline = sorted(
        spread(region.crop((x, ymid0, x + 1, ymid1)))
        for x in range(xmid0, xmid1, max(1, (xmid1 - xmid0) // 24))
    )
    threshold = max(FACE_FLOOR, (baseline[len(baseline) // 2] if baseline else 0) * ratio)

    def peel(length, line_at):
        """How many lines in from one edge are ornament rather than face.

        Returning the CAP means the scan never found the face, not that the whole edge is rim.
        MEASURED 2026-08-16: capping out and shrinking by the maximum anyway took the room the
        model had correctly left for the text, and 2 of 3 Ink Drawing Craterhoofs came back
        UNSOUND [text_too_small]. So a cap-out gives the box back untouched — the behaviour we had
        before this function existed, which is a known quantity rather than a new failure.
        """
        limit = int(length * FACE_MAX_PEEL)
        cut = 0
        while cut < limit and spread(line_at(cut)) > threshold:
            cut += 1
        return 0 if cut >= limit else cut

    # WIDTH ONLY, and this is the whole of the restraint. MEASURED 2026-08-16 on four blanks:
    #
    #   - Every observed defect was horizontal. Text began on the scroll's LEFT or RIGHT rod;
    #     nothing ever landed on a top or bottom rim, because `_rules` centres the block
    #     vertically and it rarely fills the panel.
    #   - Height is what sets type size. `textlayout.fit_across` steps the size down until the
    #     block fits the box HEIGHT, so every pixel peeled off the top or bottom comes straight
    #     out of the type. Peeling both axes took run1's panel from 360px to 242px and its text
    #     from 49 to 35, under the 48px RULES_MIN — turning a card that was fine into UNSOUND
    #     [text_too_small]. Width-only was equal or better on all four blanks.
    #
    # Vertical rims are therefore left to `check.contrast` and `panel_palette`, which already
    # handle "the text is on a surface it reads badly against" without costing a single pixel.
    left = peel(width, lambda i: region.crop((i, ymid0, i + 1, ymid1)))
    right = peel(width, lambda i: region.crop((width - i - 1, ymid0, width - i, ymid1)))
    return x0 + left, y0, x1 - right, y1


# How far past the detected box a plate may be grown, as a multiple of the box's own height. A
# plate more than this much bigger than what was reported is not a detection to repair, it is a
# detection to distrust.
PLATE_MAX_GROWTH = 2.5


def plate_extent(image, box, ratio=FACE_RATIO):
    """`box` grown DOWN and UP to the full height of the plate it sits on.

    NO LONGER CALLED IN PRODUCTION as of 2026-08-17 — `compose.plate_box` dropped it, and the reason
    and the measurements are in that docstring. Kept, not deleted, because its premise could come
    back: it is the right mechanism the moment any field is sized from its own box again. Everything
    below describes what it does, not something the pipeline currently does.

    MEASURED 2026-08-16, running `detect` four times over the SAME stored blank:

        title box height   132   125   120   214 px
        name size          90    85    82    146

    The same plate, the same image, and a 78% swing in how big the card's name is printed — which
    is what put a tiny "Craterhoof Behemoth" on an otherwise good card. One of those four runs also
    came back 672px wide against 1430 for the others, i.e. half the plate.

    `_title` sets the name as a fraction of the box's HEIGHT, so an unstable box is an unstable
    name. This is the same disease as the P/T shield (bd mtg-1uv, "a fixed box cannot track a
    painted one") on a second surface, and the same answer: stop trusting the reported geometry and
    measure the painted one.

    The statistic is `printable_face`'s, run outward instead of inward — a row still belongs to the
    plate while it looks like the plate's own interior. Growth is capped, and a plate that grows to
    the cap is left at its detected size rather than trusted, on the same reasoning as the peel:
    running to the limit means the scan never found the edge.
    """
    x0, y0, x1, y1 = box
    if x1 - x0 < 8 or y1 - y0 < 8:
        return box
    height = y1 - y0
    xmid0, xmid1 = x0 + (x1 - x0) // 4, x1 - (x1 - x0) // 4
    core = image.crop((xmid0, y0 + height // 4, xmid1, y1 - height // 4)).convert("L")
    rows = sorted(
        ImageStat.Stat(core.crop((0, y, core.width, y + 1))).stddev[0]
        for y in range(0, core.height, max(1, core.height // 24))
    )
    threshold = max(FACE_FLOOR, (rows[len(rows) // 2] if rows else 0) * ratio)
    limit = int(height * (PLATE_MAX_GROWTH - 1) / 2)

    def grow(step, edge):
        moved = 0
        while moved < limit:
            y = edge + step * (moved + 1)
            if y < 0 or y >= image.height:
                break
            line = image.crop((xmid0, y, xmid1, y + 1)).convert("L")
            if ImageStat.Stat(line).stddev[0] > threshold:
                break
            moved += 1
        return 0 if moved >= limit else moved

    return x0, y0 - grow(-1, y0), x1, y1 + grow(1, y1)


def surface_is_dark(image, box):
    """True if text on this surface has to be light.

    Sampled from the middle of the surface, inset so the carved rim and its rim light do not drag
    the average. Needed per card and not once: measured across three cards, one slab came back
    mid-grey stone, one dark blue, one pale bone.
    """
    x0, y0, x1, y1 = box
    ix, iy = round((x1 - x0) * 0.2), round((y1 - y0) * 0.2)
    patch = image.crop((x0 + ix, y0 + iy, max(x0 + ix + 1, x1 - ix), max(y0 + iy + 1, y1 - iy)))
    r, g, b = patch.convert("RGB").resize((1, 1)).getpixel((0, 0))
    # Rec. 709 luma: green dominates perceived brightness, so a mid-green slab is "light".
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 128


def ink_for(image, box, display=False):
    """(fill, stroke) for text on this surface. Shadow comes from `panel_palette`."""
    ink, stroke, _ = panel_palette(image, box, display)
    return ink, stroke


def _layer(box):
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", (max(1, x1 - x0), max(1, y1 - y0)), (0, 0, 0, 0))
    return layer, ImageDraw.Draw(layer)


def _spread(layer, colour, blur, alpha):
    """The layer's own alpha, tinted and blurred — one blur for everything in this panel.

    Doing it per panel rather than per glyph is what keeps this affordable across a 100-card
    deck, and it is also more correct: adjacent glyphs share one soft edge the way ink does.
    """
    out = Image.new("RGBA", layer.size, tuple(colour[:3]) + (0,))
    out.putalpha(layer.getchannel("A").point(lambda a: a * alpha // 255))
    return out.filter(ImageFilter.GaussianBlur(blur))


CROSSING_SIGMA = 8.0
CROSSING_FLOOR = 14
OCCLUDE_MAX_COVER = 0.15
"""Finding a thing painted across a DARK plate, where `foreground_mask` cannot help.

CLIENT 2026-08-17, on the art deco Sol Ring: "the rope behind sol ring shall feel like its submerged
and blended, not imposed cheap." A twisted rope crosses that card's title plate and the card's name
was printed straight over it, which is the same depth error `_occlude` already fixes on the pale
rules panel — only the title plate is DARK, so the foreground there is what is BRIGHTER than the
material rather than darker, and `foreground_mask` returns the material itself.

MEASURED that day over the title plates to hand, as the share of the plate sitting more than
`CROSSING_SIGMA` median-absolute-deviations above its own median:

    Sol Ring     rope crossing      median  49  MAD  3.0   3.70%
    Craterhoof   vine crossing      median  70  MAD  1.0   9.39%
    Lightning B. nothing crossing   median  91  MAD 11.0   0.00%
    Craterhoof   thorn crossing     median  63  MAD 18.0   0.00%   <- missed

It fires on a crossing over a QUIET plate and does nothing over a grainy one, including one that has
a real crossing. That asymmetry is why this is used for occlusion and NOT as a gate: a miss changes
nothing, which is exactly the behaviour before it existed, while a false positive would paste plate
grain over the card's name. `CROSSING_FLOOR` stops a nearly flat plate — MAD 1 on Craterhoof — from
setting a threshold so tight that its own shading qualifies.

`OCCLUDE_MAX_COVER` is the legibility backstop, and it applies to every surface. CLAUDE.md's rule
that survives is that a card whose printed text differs from Scryfall must never ship silently, and
a name with a third of it hidden behind a rope breaks it as surely as a wrong name would. Above this
share of the glyph pixels the crossing is simply not put back, and the text stays on top — worse
depth, readable card. On the pale rules panel `check.obstructed` refuses that card anyway, so the cap
only ever changes what a card looks like while it is on its way to being repainted.
"""


def crossing_mask(surface):
    """Soft mask of a distinctly BRIGHT thing crossing a dark surface.

    The counterpart to `foreground_mask`, which does the same job on a pale one. Kept separate
    rather than folded in, because `generation.check.obstructed` is built on `foreground_mask`'s
    behaviour and skips dark surfaces on purpose — this must not quietly change what that gate sees.
    """
    grey = surface.convert("L")
    values = sorted(grey.getdata())
    if not values:
        return grey.point(lambda _: 0)
    median = values[len(values) // 2]
    spread = sorted(abs(value - median) for value in values)[len(values) // 2]
    low = median + max(CROSSING_FLOOR, round(spread * CROSSING_SIGMA))
    span = max(1, round((255 - low) * 0.35))
    return grey.point(lambda v: 0 if v <= low else min(255, round(255 * (v - low) / span)))


def _stamp(image, layer, box, size, colour, direction=(1, 1), *, occlude=True):
    """Composite a finished text layer onto the card, its own cast shadow first.

    The shadow is the layer's own alpha, tinted, blurred and offset away from the scene's light,
    so one blur covers everything drawn into this panel rather than one per glyph. Nothing is
    added at zero offset and the glyphs are not softened — see the note above on why a halo and
    a sub-pixel blur were tried and measured to be wrong.
    """
    # A LIGHT spread is a glow and a glow has no direction — it is the letter's own light on the
    # plate, so it sits centred and lands evenly on all sides. Offsetting it away from the scene's
    # light, which is right for a cast shadow, is what measured as a bevel against the reference
    # site's even halo (see `panel_palette`). Decided by the colour rather than by a flag, because
    # `panel_palette` already chose it for this surface and a second switch could disagree with it.
    glow = 0.2126 * colour[0] + 0.7152 * colour[1] + 0.0722 * colour[2] > 128
    offset = 0 if glow else max(1, round(size * SHADOW_OFFSET))
    # Kept before anything is composited, so `_occlude` sees the surface as the model painted it.
    surface = image.crop(box)
    image.alpha_composite(
        _spread(layer, colour, max(1, round(size * SHADOW_BLUR)), colour[3]),
        (box[0] + offset * direction[0], box[1] + offset * direction[1]),
    )
    image.alpha_composite(layer, (box[0], box[1]))
    # Title and rules: a thin rim crossing goes back in front of the stamp. Type never — COMPOSITED-
    # OBJECT Triumph put the dragon back over "SORCERY", which is unreadable and looks like the type
    # line was printed on the creature. The brief keeps the subject off that object; this stops the
    # compositor from hiding the word if the model still paints over it.
    if occlude:
        _occlude(image, surface, layer, box)


def _occlude(image, surface, layer, box):
    """Put the panel's own foreground back OVER the text. Returns the share of the text it hides.

    THE ONE THING THIS MODULE WAS MISSING, and it is a depth error rather than a blend one.
    MEASURED 2026-08-17, our three composited regression cards against the reference site's own
    Craterhoof: their text and ours are the same stack to within a few values — ink RGB (40,35,28)
    on paper (240,224,191) against their (50,36,25) on (230,200,149), glyph cores flat to sd ~2 on
    both sides, and a ring 2-3px outside the glyph reading -63 on ours and -67 on theirs, which is
    antialiasing on both and a drop shadow on neither. There is no filter to copy.

    What differs is that nothing on any of their eighteen cards is painted across the panel their
    text sits on — the scene wraps the border and stops. Ours paints vines over the scroll, and we
    then drew the text ON TOP of the vines. 8.4% of Craterhoof's glyph pixels and 9.6% of Terror's
    landed on substrate darker than 150. Text in front of a thing that is in front of the panel is
    what reads as a sticker, however the glyph itself is rendered.

    So the crossing goes back on top and the text passes behind it.

    THE MASK IS CHOSEN BY THE SURFACE. On a pale panel the foreground is what is darker than the
    paper (`foreground_mask`); on a dark plate it is what is distinctly brighter (`crossing_mask`).
    Picking by polarity rather than by a flag, because the caller already knows neither and the
    surface itself is the only thing that does.

    Above `OCCLUDE_MAX_COVER` of the glyph pixels nothing is put back — see that constant. Better a
    readable card with the depth wrong than an unreadable one with the depth right, and on the rules
    panel `check.obstructed` refuses the card at that point anyway.
    """
    if surface.size != layer.size:
        return 0.0
    dark = surface_is_dark(surface, (0, 0) + surface.size)
    mask = crossing_mask(surface) if dark else foreground_mask(surface)
    ink = layer.getchannel("A")
    total = ImageStat.Stat(ink).sum[0]
    if not total:
        return 0.0
    covered = ImageStat.Stat(ImageChops.multiply(ink, mask)).sum[0] / total
    if covered > OCCLUDE_MAX_COVER:
        return 0.0
    image.paste(surface, (box[0], box[1]), mask)
    return covered


def _tracked_width(font, text, tracking):
    """Shaped width of the run, plus tracking. `getlength` on the whole string is kerned."""
    return font.getlength(text) + tracking * max(0, len(text) - 1)


def _write_tracked(draw, xy, text, font, fill, stroke, size, tracking, emboss=False):
    """A display run drawn glyph by glyph so it can be tracked tighter than the font's metrics.

    Each glyph is placed at the SHAPED width of everything before it, not at the sum of its
    predecessors' individual advances. MEASURED 2026-08-10: Pillow is built against HarfBuzz, so
    `getlength("VA")` is 7.41px tighter at 100px than the two glyphs measured apart — drawing
    char by char and advancing by each glyph's own width throws that kerning away and stamps the
    letters down like a typewriter, which is precisely the failure this function was accused of.
    Measuring the prefix keeps every kern pair and still allows tracking on top.
    """
    x, y = xy
    for index, char in enumerate(text):
        offset = font.getlength(text[:index]) + tracking * index
        _write(draw, (x + offset, y), char, font, fill, stroke, size, emboss=emboss)


def _write(draw, xy, text, font, fill, stroke, size, anchor=None, emboss=False):
    """One run of text: emboss edges first, then the stroked fill over them."""
    x, y = xy
    if emboss:
        step = max(1, round(size * EMBOSS))
        draw.text((x + step, y + step), text, font=font, fill=(0, 0, 0, 150), anchor=anchor)
        # The light half of the emboss only helps where the ink itself is light; on parchment it is
        # one more thing washing the glyph out.
        if stroke is not None:
            draw.text(
                (x - step, y - step), text, font=font, fill=(255, 255, 255, 90), anchor=anchor
            )
    if stroke is None:
        draw.text((x, y), text, font=font, fill=fill, anchor=anchor)
        return
    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
        anchor=anchor,
        stroke_width=max(1, round(size * STROKE)),
        stroke_fill=stroke,
    )


TAB_MAX_ASPECT = 2.5
"""Widest a P/T box may be, as width/height, before it is trimmed from the RIGHT.

CLIENT 2026-08-17: "look at ours" — the numerals leaving a gap at the tab's left and running off its
right. They are centred correctly; the BOX is wrong. On the card in question it was reported at
x0.762-0.953 where the tab's flat face measured x0.776-0.866 by column stddev (1.5-6.3 inside the
face, 16-64 past it), so centring put the value 119px right of where it belonged.

TRIMMED FROM THE RIGHT, and the asymmetry is structural rather than a guess. The tab lives in the
bottom-right corner: its LEFT edge borders the pale rules panel, which is the strongest value edge on
that part of the card, and its RIGHT edge borders the card's own corner scenery, which the model
paints in the tab's own dark material. Every over-report measured has been on the right.

2.5 IS THE REFERENCE SITE'S OWN CEILING, read off all eighteen of their stored cards: their tabs run
from about 1.0 (the discs on Elemental, Devil, Sunspine Lynx) to about 2.5 (the banners on Agate
Instigator and Spellskite). A box wider than anything in that population has swallowed scenery. Our
own five detected boxes are 0.88, 1.76, 2.41, 2.48 and 2.95 — so this fires on exactly the one that
is visibly broken and leaves the other four untouched, which is the whole point of setting it at
their maximum rather than at their median.

REJECTED FIRST, and worth recording so it is not re-attempted blind: segmenting the box by column
stddev and keeping the largest flat run. It is the more principled measurement and it moved two boxes
that were already correct — stored Terror by 40px — on a sample of five with no ground truth for four
of them. `printable_face` cannot do this job either: its threshold is the box's median row stddev
times FACE_RATIO, and a box that is half tab and half foliage has a median high enough that the
threshold lands above the foliage's own noise, so it peels nothing (measured: 0px on this card).
"""


def _tab_box(box):
    """A P/T box trimmed to a plausible tab. Returns it unchanged when it already is one."""
    x0, y0, x1, y1 = box
    height = y1 - y0
    if height <= 0 or (x1 - x0) <= height * TAB_MAX_ASPECT:
        return box
    return (x0, y0, x0 + round(height * TAB_MAX_ASPECT), y1)


def compose(png, face, panels, include_flavor_text=False, lettered=False, name_lettered=False):
    """(finished card, whether the rules text overflowed its panel).

    A panel the detector did not find is skipped rather than guessed at — a card missing its type
    line is obvious, while a type line printed over the art looks like a design choice. The
    overflow flag means the AI painted a slab too small for this card's text, which is a reason to
    regenerate the art rather than something the compositor can fix.

    `lettered` means the model already set every field except the cost, so this stamps the cost and
    nothing else. Overflow is always False there: the model sized the panel to text it could see,
    which is the whole reason that mode exists (bd mtg-469).

    `name_lettered` is the failed hybrid: the model painted the name INTO the top object, and we
    stamp cost, type, rules and P/T. `lettered` wins if both are set.
    """
    image = Image.open(png).convert("RGBA") if not isinstance(png, Image.Image) else png.copy()
    light = light_direction(image)

    def face_box(panel):
        """The detected object, shrunk to the part of it we can actually print on."""
        return printable_face(image, _box(panel, image.size))

    def plate_box(panel):
        """A display plate, with its carved rim peeled off so text lands on the flat face.

        `plate_extent` USED TO RUN HERE and was removed 2026-08-17, premise first. Its docstring
        states that premise plainly: "`_title` sets the name as a fraction of the box's HEIGHT, so an
        unstable box is an unstable name". That stopped being true earlier the same day, when
        NAME_CARD_SIZE and `_plate_size` moved the name and the type line onto the CARD's height with
        the box as a ceiling only. The instability it was built to absorb is absorbed upstream now.

        MEASURED over four stored blanks, with and without the growth. The name came out 91px on
        every card BOTH WAYS — it no longer moves the size at all — while the vertical placement of
        the ink inside the DETECTED plate went:

                            with growth        without
            new3          20.9% / 20.9%     20.9% / 20.9%
            new           21.9% / 21.2%     21.9% / 21.2%
            Craterhoof    24.2% / 34.8%     29.8% / 30.4%
            Terror        37.0% /  2.2%     20.0% / 19.3%

        as (gap above, gap below). On two cards it changes nothing; on the other two it walks the box
        past the plate's lower rim into the art and the text follows it down. On Terror that leaves
        the card's name three pixels off the bottom edge of the plate it is supposed to sit on, with
        a third of the plate empty above it — which is the "look at ours" the client circled on
        2026-08-17.

        Same shape as deleting the guessed P/T box (38f6b16): a mechanism built to paper over an
        upstream defect, kept after the defect was fixed, doing nothing but its own side effects.
        """
        return printable_face(image, _box(panel, image.size))

    paints_name = lettered or name_lettered
    if paints_name and panels.get("title"):
        # THE RAW BOX, not `plate_box`. MEASURED on Progenitus, 2026-08-17: `plate_extent`
        # grew a title box reported at y 0.05-0.15 all the way to y 0.00, and the pips centred
        # in that box rode half off the top of the plate. Both repairs are tuned for a BLANK
        # surface — they find a plate's painted extent by scanning for the value edge where it
        # meets the art, and on a lettered card the name's own strokes are value edges, so the
        # scan walks past the rim and into the picture.
        #
        # The NAME box is the letters. Passing it is what stops the pips sitting in the
        # title box's empty sky (live pack 2026-08-19). `_cost` then tightens it to the
        # painted ink, because the box itself still carries detector padding.
        name = _box(panels["name"], image.size) if panels.get("name") else None
        # The TYPE box is passed for one reason: if the cost has to go on a medallion row under
        # the plate, that row must not land on the type strip.
        _cost(
            image, face, _box(panels["title"], image.size), light, name,
            type_box=_box(panels["type"], image.size) if panels.get("type") else None,
        )
        if lettered:
            return image, False

    if not paints_name and panels.get("title"):
        _title(image, face, plate_box(panels["title"]), light)
    if panels.get("type"):
        type_box = plate_box(panels["type"])
        # SET IN CAPS. CLIENT 2026-08-17: "Creature - Beast looks small". It is not set small — it is
        # set in mixed case, so most of its visual mass is x-height and the line reads as a thin
        # ribbon on a tall plate. MEASURED that day against their own Craterhoof, as the ink band's
        # share of the plate it sits on: theirs 79px in a 103px plate, 76.6%; ours 56px in a 154px
        # plate, 36.4%. Less than half the presence at a comparable point size.
        #
        # Caps is the free half of the gap: at the SAME em, `CREATURE - BEAST` measures 71px against
        # `Creature - Beast` at 56px, so 1.27x taller for nothing, and 683px wide against 582px in
        # 1316px of available room, so it never costs a size step. 9 of the reference site's 18
        # stored cards set the type line in caps, Craterhoof among them.
        #
        # The other half is TYPE_CARD_SIZE, and it is NOT taken here. Their absolute ink is 1.41x
        # ours, so caps leaves about 1.11x on the table, which would mean 0.032 -> 0.036 — and that
        # constant's own note measures the size spread across the archive at 1.12x at 0.032 against
        # 1.19x at 0.034, past the 1.15x bar it was set to hold. Trading consistency across a deck
        # for one card's presence is the trade that produced "small somewhere large somewhere".
        _display(image, face["type_line"].upper(), type_box, light,
                 size=_plate_size(type_box, image.height, TYPE_CARD_SIZE, TYPE_MAX_OF_BOX))
    overflowed = False
    if panels.get("rules") and face.get("oracle_text"):
        shield = _box(panels["pt"], image.size) if panels.get("pt") else None
        boxes = [face_box(panel) for panel in _rules_panels(panels["rules"])]
        # Named to match the reference site's own generate payload, so the frontend passes its
        # toggle straight through. Off by default: flavour text competes with the rules for the
        # one panel we get, and rules text losing size to prose is the worse trade.
        flavour = (face.get("flavor_text") or "") if include_flavor_text else ""
        overflowed = _rules(image, face["oracle_text"], boxes, shield, light, flavour)
    if panels.get("pt") and face.get("power") is not None:
        # DELIBERATELY not run through `printable_face`. MEASURED 2026-08-16: on all three cards
        # the P/T tab peels straight to FACE_MAX_PEEL, which means the scan cannot tell rim from
        # face at that size rather than that the tab is all rim. The P/T already has a working
        # mechanism — the enlarged corner paired into the detect call, commit e10ba96, which took
        # detection 35% -> 88% — and bd mtg-1uv owns finishing it. Adding an unvalidated second
        # shrink on top of that would put the one surface that just got better back at risk.
        # RAISED 2026-08-16 from 0.50. Measured on a Phyrexian Obliterator whose tab came back
        # 109px tall: at half the box the value read small against a generous plate, which is the
        # same "smaller and less readable than theirs" report that moved NAME_SIZE and RULES_SIZE
        # on 2026-08-10. Safe to raise now in a way it was not then — detection of this surface
        # measured 12/12 today against 35% when it was briefed as a shield, and the tab is asked
        # for with a flat even face rather than a pointed rim.
        pt = f"{face['power']}/{face['toughness']}"
        pt_box = _tab_box(_box(panels["pt"], image.size))
        _display(image, pt, pt_box, light, size=_pt_size(pt_box, image.height))
    return image, overflowed


class UnknownSymbol(KeyError):
    """A mana symbol we hold no artwork for. CLAUDE.md: this must fail loudly.

    `symbols.pip` answers None for a token with no vendored SVG, and this loop used to `continue`
    past it — which prints `{2}{G}` as one green pip and calls the card finished. A cost missing a
    symbol is a WRONG cost, not a slightly plainer one, and it is invisible on the finished card
    precisely because the remaining pips still look right. `jobs._face` catches this per face, so
    one unrenderable cost is reported failed and the rest of the deck still paints.
    """


def _draw_pips(layer, tokens, pip_px, right, height):
    """Stamp `tokens` right-aligned at `right`, reversed, on `layer`. Vertically centred.

    Shared by the composited path, where the name shrinks around the cost, and the lettered one,
    where the model painted the name and left the room the brief reserved.
    """
    gap = round(pip_px * PIP_GAP)
    x = right
    for token in tokens:
        pip = symbols.pip("{" + token + "}", pip_px)
        if pip is None:
            raise UnknownSymbol(f"no vendored artwork for the mana symbol {{{token}}}")
        x -= pip_px
        layer.alpha_composite(pip, (round(x), round((height - pip_px) / 2)))
        x -= gap


CARD_ASPECT = 2400 / 1792
"""Our canvas, height over width — the same one the reference site paints on."""


def cost_width(face, box, name_box=None):
    """How NARROW this cost can be made and still be stamped into `box`, in fractions of card width.

    The same arithmetic `_cost` does in pixels, in the unit a caller holding only 0-1 boxes can
    use. `check.cost_collides` is that caller: the cost lands against the plate's right end and
    the only thing there to hit is the name the model lettered, and both arrive as fractions from
    `panels.read_back` with no image between them.

    AT THE FLOOR, and not at the nominal pip size, because `_cost` shrinks the row before it gives
    up: `while pip_px > floor and span + pad > well_w: pip_px -= 1`. Measured at nominal this
    function answers a question the compositor never asks, and the two disagree on exactly the
    marginal case — which a ten-pip cost always is. PROGENITUS, 2026-08-20: its ten pips stamped
    correctly, clear of the name, and `cost_collides` had already called the card unsound for a
    collision that did not happen. A false repaint is a spent credit.

    So the contract is the widest the row is ALLOWED to be squeezed to. A name that clears this
    still leaves `_cost` free to stamp bigger pips when there is room for them; a name that does
    not clear it is one `_cost` would refuse outright, which is the fault worth reporting.
    `compositor.cost_fits` measures the same floor in pixels, so the two gates now agree.
    """
    tokens = symbols.TOKEN.findall(face.get("mana_cost") or "")
    if not tokens:
        return 0.0
    pip = _pip_frac(box) * PIP_MIN_OF_TARGET
    n = len(tokens)
    return (n + max(0, n - 1) * PIP_GAP) * pip * CARD_ASPECT + COST_RIGHT_INSET


def _pip_frac(plate, name=None):
    """Pip diameter as a fraction of CARD HEIGHT. Shared by `_cost` and `cost_width`.

    `name` is accepted so older callers keep working; it does not size the pip. A short painted
    name is not a small cost — see the note above `LETTER_INK`.
    """
    plate_h = plate[3] - plate[1]
    from_card = NAME_CARD_SIZE * 0.92
    from_plate = plate_h * 0.72
    return max(0.018, min(from_card, from_plate))


def _longest_run(indexes):
    """Inclusive (start, end) of the longest consecutive run, or None."""
    if not indexes:
        return None
    best_a = best_b = start = prev = indexes[0]
    for i in indexes[1:]:
        if i == prev + 1:
            prev = i
            continue
        if prev - start > best_b - best_a:
            best_a, best_b = start, prev
        start = prev = i
    if prev - start > best_b - best_a:
        best_a, best_b = start, prev
    return best_a, best_b


def _letter_band(image, box):
    """`box` tightened to the rows that actually carry the painted name.

    `read_back` reports the letters plus padding. LIVE PACK 2026-08-19, Tromell: an 89px name box
    with the gold in the bottom 37px. Pips sized and centred on that box sat 23px above the name
    and read as stickers. The pixels know where the ink is.

    Not `crossing_mask`. That misses on a grainy plate (its own docstring, Craterhoof thorns), and
    Tromell's grey banner is grainy. A row's 90th-percentile luma against the plate catches gold,
    cream and white lettering alike without a hue gate; inverted (10th percentile) on a pale plate.
    The longest dense run drops snow on the banner and a highlight on one serif.
    """
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    if width < 8 or height < 8:
        return box
    grey = image.crop(box).convert("L")
    dark = surface_is_dark(image, box)
    px = grey.load()
    step = 2 if width >= 16 else 1
    high, low, means = [], [], []
    for y in range(height):
        vals = sorted(px[x, y] for x in range(0, width, step))
        n = len(vals) - 1
        high.append(vals[int(0.90 * n)])
        low.append(vals[int(0.10 * n)])
        means.append(sum(vals) / len(vals))
    if dark:
        plate = sorted(means)[len(means) // 4]
        inked = [i for i, value in enumerate(high) if value >= plate + LETTER_INK]
    else:
        plate = sorted(means)[(3 * len(means)) // 4]
        inked = [i for i, value in enumerate(low) if value <= plate - LETTER_INK]
    run = _longest_run(inked)
    if run is None:
        return box
    a, b = run
    # A highlight or a carved hairline, not a name.
    if (b - a + 1) < max(16, round(height * 0.28)):
        return box
    a = max(0, a - 1)
    b = min(height - 1, b + 1)
    return x0, y0 + a, x1, y0 + b + 1


def _plate_face_right(image, box):
    """Right edge of the plate's inner face, in pixels, inside the carved rim.

    Two walks, because each one is blind to a rim the other can see.

    OUTSIDE-IN (the fallback). `printable_face` peels STRUCTURE. A flat black bevel is
    even, so it is not peeled, and lettered pips land on the rim. LIVE PACK 2026-08-19,
    Tromell: the detector box ended at x=1740 and the grey face at x=1671 — a 69px bevel.
    COST_RIGHT_INSET of 50px still sat the pips on it. The face is the first sustained run
    of columns whose mean looks like the plate's interior.

    INSIDE-OUT (tried first). SIGNOFF 2026-08-19, Atraxa and Craterhoof: the outer frame
    is the SAME luma as the inner face, so outside-in treats the frame as face and the
    last pip sits on the rim, split by the carved lip. This strip's LEFT is already on
    the face (`_cost_well` seeds it there). Walk right until the column is not. Trust
    that stop if most of the strip was face — a vine at 40% is rejected; a rim after
    a gothic frame that the detector swallowed (Progenitus) is not.
    """
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    if width < 16 or height < 8:
        return x1
    region = image.crop(box).convert("L")
    ym0, ym1 = height // 4, height - height // 4
    px = region.load()
    ref = region.crop((max(1, width // 16), ym0, max(2, width // 4), ym1))
    interior = ImageStat.Stat(ref).mean[0]
    if interior < 8:
        return x1
    slack = max(22.0, interior * 0.40)

    def col_mean(i):
        vals = [px[i, y] for y in range(ym0, ym1)]
        return sum(vals) / len(vals)

    def col_sd(i):
        vals = [px[i, y] for y in range(ym0, ym1)]
        mean = sum(vals) / len(vals)
        return (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5

    miss = 0
    last = 0
    found = None
    bright = 0
    spike = max(50.0, interior * 0.80)
    for i in range(width):
        mean = col_mean(i)
        if mean > interior + spike:
            bright += 1
        else:
            bright = 0
        luma_ok = abs(mean - interior) <= slack
        # Grain on the LEFT of a stone plate (Craterhoof) is not a rim. A structured
        # spike AFTER a long face run is (Atraxa's bevel, Birthing Pod's gold).
        established = last >= int(width * FACE_RIGHT_MIN_SPAN)
        if luma_ok and not (col_sd(i) > 10.0 and established):
            last = i
            miss = 0
            continue
        miss += 1
        # CLIENT-PACK 2026-08-19, Atraxa: an 8px bright bevel, then a decorative end
        # whose luma is within slack of the face. FACE_RIGHT_RUN never accumulated
        # on luma, so the last pip sat on the notch. A highlight this much above
        # the plate, or a structured spike after the face is established, is the
        # rim even when it is thinner than the run.
        rim = miss >= FACE_RIGHT_RUN or bright >= 4
        if not rim:
            continue
        if established:
            found = x0 + last + 1
        break

    # High-structure columns on the right are a carved / gold rim even when the
    # mean is unhelpful (Birthing Pod's gold end). Cap-out peels nothing.
    sd_cap = 10.0
    limit = int(width * FACE_RIGHT_MAX_PEEL)
    cut = 0
    while cut < limit and col_sd(width - 1 - cut) > sd_cap:
        cut += 1
    if cut and cut < limit:
        peeled = x1 - cut
        found = peeled if found is None else min(found, peeled)

    if found is not None:
        return found

    floor = interior * FACE_RIGHT_MIN
    rim_slack = max(25.0, interior * 0.45)
    run = 0
    start = 0
    for i in range(limit):
        mean = col_mean(width - 1 - i)
        if mean >= floor and abs(mean - interior) <= rim_slack:
            if run == 0:
                start = i
            run += 1
            if run >= FACE_RIGHT_RUN:
                return x1 - start
        else:
            run = 0
    return x1


def _extend_plate_right(image, box, name=None):
    """Grow a truncated title box to the right while the name-band still looks like plate.

    SIGNOFF 2026-08-19, Kitchen Finks: `read_back` reported the left half of a split
    title (x1=0.67). The model had painted an empty cost box past a seam. Pips jammed
    into the first half and the second sat empty. The pixels of the plate continue;
    the detector stopped at the divider.
    """
    x0, y0, x1, y1 = box
    cap = int(image.width * 0.96)
    if x1 >= cap - 8:
        return box
    if name:
        by0 = max(y0, min(round(name[1]), y1 - 2))
        by1 = max(by0 + 1, min(round(name[3]), y1))
    else:
        mid = (y0 + y1) // 2
        by0, by1 = max(y0, mid - 8), min(y1, mid + 8)
    grey = image.convert("L")
    px = grey.load()
    pad_y = max(1, (by1 - by0) // 4)
    ym0, ym1 = by0 + pad_y, by1 - pad_y
    if ym1 <= ym0:
        ym0, ym1 = by0, by1

    def col_mean(x):
        vals = [px[x, y] for y in range(ym0, ym1)]
        return sum(vals) / len(vals)

    def col_sd(x):
        vals = [px[x, y] for y in range(ym0, ym1)]
        mean = sum(vals) / len(vals)
        return (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5

    # INTERIOR of the plate, not the last 40px. SIGNOFF Birthing Pod: those 40px
    # were already the gold lip the detector swallowed, so matching that ref grew
    # through more ornament to the cap and the last pip sat on the gold.
    inner0 = x0 + int((x1 - x0) * 0.15)
    inner1 = x0 + int((x1 - x0) * 0.55)
    if name:
        inner0 = max(inner0, min(round(name[2]) + 8, inner1 - 8))
    look = max(8, inner1 - inner0)
    ref = sum(col_mean(x) for x in range(inner0, inner0 + look)) / look
    slack = max(22.0, ref * 0.45)
    miss = 0
    structured = 0
    last = x1
    for x in range(x1, cap):
        mean = col_mean(x)
        # High-structure columns are a carved / gold rim, not a seam. The Kitchen
        # Finks gap is FLAT pale sky (sd ~0) and must still be crossed; Birthing
        # Pod's gold lip is striped (sd > 10) and must not.
        if col_sd(x) > 10.0:
            structured += 1
            if structured >= 6:
                break
        else:
            structured = 0
        if abs(mean - ref) <= slack:
            last = x + 1
            miss = 0
        else:
            miss += 1
            if miss > PLATE_SEAM:
                break
    if last - x1 < 16:
        return box
    return x0, y0, last, y1


def _name_plate_ref(image, name, title):
    """Luma of the plate the name sits ON, not of the letters and not of a hole after them.

    Taken from the title band's INTERIOR at the name's rows — the same 15–55%
    `_extend_plate_right` uses — so a carved black bevel (Atraxa) and a pale
    painted slot (Tromell) cannot become the plate luma. The name crop itself is
    gold lettering; its quartile is the ink.
    """
    x0, y0, x1, y1 = title
    by0 = max(y0, min(round(name[1]), y1 - 2))
    by1 = max(by0 + 1, min(round(name[3]), y1))
    inner0 = x0 + int((x1 - x0) * 0.15)
    inner1 = x0 + int((x1 - x0) * 0.55)
    if inner1 <= inner0 + 8:
        inner0, inner1 = x0, x1
    band = image.crop((inner0, by0, inner1, by1)).convert("L")
    vals = sorted(band.getdata())
    if not vals:
        return 0.0
    # The TITLE box can include a pale painted slot, which fools `surface_is_dark`.
    # The interior quartile itself says whether this plate is stone or bone.
    if vals[len(vals) // 4] < 128:
        return vals[len(vals) // 4]
    return vals[(3 * len(vals)) // 4]


def _well_ref(image, name, title, wx0):
    """Plate luma for the cost walk.

    Under-the-name stone (Atraxa's letters sit on a darker band than the empty
    face) is the identity of the object. The empty face just after the letters
    is what we walk, when it is the same material — a gradient of 20 luma is
    still the plate. A pale painted slot is 100+ luma away and is not.
    """
    under = _name_plate_ref(image, name, title)
    x1 = round(title[2])
    by0 = max(round(title[1]), min(round(name[1]), round(title[3]) - 2))
    by1 = max(by0 + 1, min(round(name[3]), round(title[3])))
    nx1 = min(x1, wx0 + 32)
    if nx1 <= wx0 + 4:
        return under
    vals = sorted(image.crop((wx0, by0, nx1, by1)).convert("L").getdata())
    if not vals:
        return under
    after = vals[len(vals) // 2]
    if abs(after - under) <= max(28.0, under * 0.55):
        return after
    return under


def _walk_plate_right(image, x0, y0, x1, y1, ref, slack):
    """Rightmost column in [x0, x1) that is still the plate `ref` describes.

    Crosses a short same-family seam (Kitchen Finks). Stops on a painted slot,
    sky, or a structured rim (Birthing Pod gold).
    """
    if x1 - x0 < 2 or y1 - y0 < 2:
        return x1
    grey = image.convert("L")
    px = grey.load()
    pad_y = max(1, (y1 - y0) // 4)
    ym0, ym1 = y0 + pad_y, y1 - pad_y
    if ym1 <= ym0:
        ym0, ym1 = y0, y1

    def col_mean(x):
        vals = [px[x, y] for y in range(ym0, ym1)]
        return sum(vals) / len(vals)

    def col_sd(x):
        vals = [px[x, y] for y in range(ym0, ym1)]
        mean = sum(vals) / len(vals)
        return (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5

    last = x0
    miss = 0
    structured = 0
    for x in range(x0, x1):
        if col_sd(x) > 10.0:
            structured += 1
            # Grain on the left of a stone plate is not a rim (Craterhoof, Atraxa).
            # A structured spike after the face is established is (gold lip, gothic frame).
            established = (last - x0) >= int(max(1, x1 - x0) * FACE_RIGHT_MIN_SPAN)
            if established and structured >= 6:
                break
        else:
            structured = 0
        if abs(col_mean(x) - ref) <= slack:
            last = x + 1
            miss = 0
        else:
            miss += 1
            if miss > PLATE_SEAM:
                break
    return max(x0 + 1, last)


def _cost_well(image, box, name=None, plate=None):
    """The inner rectangle that should hold the pips.

    SIGNOFF 2026-08-19: the well used to start at 72% of the title box. That boxed
    Progenitus's ten pips into the right quarter (postage stamps) and Kitchen Finks's
    three into the left half of a split plate (overflow, empty box on the right).
    The well starts after the painted name and runs to the inner face of the plate —
    including a cost box `read_back` dropped, via `_extend_plate_right`.

    LETTERED-OVERLAP v4 (bd mtg-2su): luma is taken from the name object, not from
    the pixels after the name. Those pixels are where Gemini paints a second box.
    The title detector box is a search cap, not the well.
    """
    x0, y0, x1, y1 = box
    gap = round(image.width * COST_NAME_GAP)
    grey = image.convert("L")
    px = grey.load()
    if name:
        wx0 = min(max(round(name[2]) + gap, x0), x1 - 8)
        seed0 = max(y0, min(round(name[1]), y1 - 2))
        seed1 = max(seed0 + 1, min(round(name[3]), y1))
        ref = _well_ref(image, plate or name, box, wx0)
        rx0, rx1 = round(name[0]), round(name[2])
        sample0 = max(rx0, rx1 - max(24, (rx1 - rx0) // 3))
        sample1 = max(sample0 + 1, rx1)

        def row_mean(y):
            vals = [px[x, y] for x in range(sample0, sample1)]
            return sum(vals) / len(vals)
    else:
        wx0 = x0 + int((x1 - x0) * 0.50)
        mid = (y0 + y1) // 2
        seed0, seed1 = max(y0, mid - 8), min(y1, mid + 8)
        xm0 = max(wx0 + 1, wx0 + (x1 - wx0) // 4)
        xm1 = max(xm0 + 1, x1 - (x1 - wx0) // 4)

        def row_mean(y):
            vals = [px[x, y] for x in range(xm0, xm1)]
            return sum(vals) / len(vals)

        ref = sum(row_mean(y) for y in range(seed0, seed1)) / (seed1 - seed0)
    slack = max(22.0, ref * 0.40)

    def same(y):
        return abs(row_mean(y) - ref) <= slack

    top = seed0
    while top > y0 and same(top - 1):
        top -= 1
    bot = seed1
    while bot < y1 and same(bot):
        bot += 1
    peel_x0 = max(wx0, x1 - max(round((x1 - x0) * 0.35), round(image.width * 0.22)))
    face_right = _plate_face_right(image, (peel_x0, top, x1, bot))
    # Default: pips at the inner-right of the title frame. That is the
    # placement the client flags daily when it misses. Only abandon it when
    # that right-hand end is a DIFFERENT painted box (Tromell's pale slot).
    pad_y = max(1, (bot - top) // 4)
    ym0, ym1 = top + pad_y, bot - pad_y
    if ym1 <= ym0:
        ym0, ym1 = top, bot
    probe = min(max(wx0, face_right - 16), max(wx0, face_right - 1))

    def col_mean(x):
        vals = [px[x, y] for y in range(ym0, ym1)]
        return sum(vals) / len(vals) if vals else 0.0

    tail = col_mean(probe)
    if abs(tail - ref) <= slack:
        return wx0, top, face_right, bot
    walked = _walk_plate_right(image, wx0, top, x1, bot, ref, slack)
    right = _plate_face_right(image, (wx0, top, walked, bot))
    return wx0, top, right, bot


# The medallion row, for a cost the title plate's own well will not take.
#
# WHY A SECOND PLACEMENT EXISTS AT ALL. `_cost` used to give up: it returns without stamping when
# the row will not fit even at the pip floor, because stamping anyway smashed `{2}{G}{G}` into one
# oval (LETTERED-OVERLAP v3). Correct, and it means the card ships with NO MANA COST — Birthing
# Pod, `packs/cost-hard/`, 2026-08-20. A proxy with no cost is unplayable, which is worse than any
# placement.
#
# The well is a negotiation for space inside a plate the MODEL sized, and it is a negotiation we
# lose on every card with a long name or a lot of pips. The client's own examples do not hold it:
# in 12 of his 19 the cost sits on its own medallions on a second row under the name, clear of the
# title bar entirely. Below the plate there is a whole card's width and no name to hit, so the
# collision cannot happen by construction rather than being measured away.
COST_ROW_GAP = 0.012
"""Air between the title plate's bottom edge and the top of the medallion row, as a share of card
height. Enough to read as a separate object under the plate rather than as its lower rim."""
COST_ROW_INSET = 0.055
"""How far in from the card's right edge the row ends, as a share of card width. The plate's own
right end is preferred when it is sane; this is the fallback and the cap, and it keeps the row
inside the 92% the card is trimmed to."""


def cost_row(image, face, plate, type_box=None):
    """(x0, y0, x1, y1) for the medallion row under the title plate, or None if it cannot sit.

    None means there is genuinely nowhere: the type strip is right beneath the plate, or the pips
    will not fit a whole card's width at the floor. Both are repaints, and `check.cost_off_rim`
    reports them — this function is what that gate asks so the two cannot disagree.
    """
    tokens = symbols.TOKEN.findall(face.get("mana_cost") or "")
    if not tokens:
        return None
    n = len(tokens)
    # SIZED OFF THE CARD, not off the plate's inner height, which is the whole point of moving:
    # a cost squeezed by a shallow plate is what put Progenitus's ten pips in the right quarter.
    target = max(1, round(_pip_frac((0, 0, 1, 1)) * image.height))
    floor = max(16, round(target * PIP_MIN_OF_TARGET))

    right = round(plate[2])
    cap = round(image.width * (1 - COST_ROW_INSET))
    if not (0 < right <= image.width):
        right = cap
    right = min(right, cap)

    top = round(plate[3] + image.height * COST_ROW_GAP)
    limit = round(type_box[1]) - round(image.height * COST_ROW_GAP) if type_box else image.height

    def span(at):
        return n * at + max(0, n - 1) * round(at * PIP_GAP)

    pip_px = target
    room = max(1, right - round(image.width * 0.04))
    while pip_px > floor and (span(pip_px) > room or top + pip_px > limit):
        pip_px -= 1
    if span(pip_px) > room or top + pip_px > limit:
        return None
    return (right - span(pip_px), top, right, top + pip_px)


def _cost_medallions(image, face, plate, type_box=None):
    """The cost as its own row of medallions under the title plate. True if it landed.

    A DROP SHADOW under each pip, which the plate placement does not need and this one cannot do
    without: the well sits the pips on flat painted stone, and here they sit on artwork that may be
    any value at all. A Scryfall pip is a finished circle with no outline of its own, so a white
    sun on pale sky has nothing to separate it from the sky.
    """
    box = cost_row(image, face, plate, type_box)
    if box is None:
        return False
    x0, y0, x1, y1 = box
    pip_px = y1 - y0
    layer, _ = _layer(box)
    _draw_pips(layer, list(reversed(symbols.TOKEN.findall(face["mana_cost"]))), pip_px, x1 - x0,
               pip_px)

    offset = max(2, round(pip_px * 0.06))
    shadow = Image.new("RGBA", (x1 - x0 + offset * 2, pip_px + offset * 2), (0, 0, 0, 0))
    shadow.paste(
        Image.new("RGBA", layer.size, (0, 0, 0, 150)), (offset * 2, offset * 2), layer
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(1, round(pip_px * 0.05))))
    image.alpha_composite(shadow, (x0 - offset, y0 - offset))
    # STRAIGHT ON, and NOT through `_paste_pips`, whose `_occlude` puts the surface's own
    # foreground back over the pips. That is right on a plate — a vine painted across the plate
    # should cross the cost the way it crosses the name. Here the "surface" is open artwork, so
    # the mask is arbitrary scene detail and the result is fragments of picture pasted over the
    # mana symbols, or not, depending on how busy the paint happens to be. These medallions are
    # the topmost objects on the card, which is what they are on the client's own examples.
    image.alpha_composite(layer, (x0, y0))
    return True


def cost_fits(image, face, box, name=None):
    """Whether this cost fits the plate's inner face at the size floor.

    CLIENT-PACK 2026-08-19: `_cost` used to shrink to the floor and stamp anyway, so a well
    that was really the outer frame still shipped pips on the rim. The gate in
    `check.cost_off_rim` reads this so a miss becomes a repaint, not a stamp.

    NOT the whole question any more: a cost this returns False for goes to `cost_row` instead of
    nowhere. `check.cost_off_rim` asks both.
    """
    tokens = symbols.TOKEN.findall(face.get("mana_cost") or "")
    if not tokens:
        return True
    plate = name
    if name:
        name = _letter_band(image, name)
    box = _extend_plate_right(image, box, name)
    wx0, wy0, wx1, wy1 = _cost_well(image, box, name, plate)
    n = len(tokens)
    target = max(1, round(_pip_frac((0, 0, 1, (wy1 - wy0) / image.height)) * image.height))
    floor = max(16, round(target * PIP_MIN_OF_TARGET))
    span = n * floor + max(0, n - 1) * round(floor * PIP_GAP)
    pad = max(round(floor * PIP_RIGHT), round(image.width * 0.012))
    return span + pad <= max(1, wx1 - wx0)


def _paste_pips(image, layer, box):
    """Scryfall SVG pips onto the card, no Beleren glow.

    `_stamp` is the type treatment: a blurred halo of the letter's own light. The pip artwork
    already is a finished circle; running it through that halo is what made {2}{G} read as one
    overlapping oval on Tromell. Occlusion stays — a vine crossing the cost still goes in front.
    """
    surface = image.crop(box)
    image.alpha_composite(layer, (box[0], box[1]))
    _occlude(image, surface, layer, box)


def _cost(image, face, box, light=(1, 1), name=None, type_box=None):
    """The mana cost alone, for the mode where the model lettered everything else.

    WHY THIS IS THE ONE FIELD WE KEEP. Measured over 25 lettered generations the model took the
    name and the rules text 25 of 25 and the mana cost 18 of 22 — every ordinary cost of four pips
    or fewer, and none of the four that need counting past four or a compound pip. See
    `prompts._lettering_block`.

    No shrink loop, because there is no name of ours to shrink. Size and placement follow the
    inner cost well on the right of the title plate — the painted name is only a seed for which
    band that well sits on.
    """
    tokens = list(reversed(symbols.TOKEN.findall(face.get("mana_cost") or "")))
    if not tokens:
        return
    plate = name
    if name:
        name = _letter_band(image, name)
    box = _extend_plate_right(image, box, name)
    wx0, wy0, wx1, wy1 = _cost_well(image, box, name, plate)
    target = max(1, round(_pip_frac((0, 0, 1, (wy1 - wy0) / image.height)) * image.height))
    pip_px = target
    n = len(tokens)
    well_w = max(1, wx1 - wx0)
    floor = max(16, round(target * PIP_MIN_OF_TARGET))

    def span(at):
        return n * at + max(0, n - 1) * round(at * PIP_GAP)

    def pad(at):
        return max(round(at * PIP_RIGHT), round(image.width * 0.012))

    # Shrink only when the row would hit the name. Floor is 75% of the name-matching
    # size — below that they read as dots (Progenitus, sign-off pack).
    while pip_px > floor and span(pip_px) + pad(pip_px) > well_w:
        pip_px -= 1
    # LETTERED-OVERLAP v3, Triumph of the Hordes: the floor still did not fit,
    # and stamping anyway stacked {2}{G}{G} into one oval. `cost_off_rim` already
    # fails the attempt; an empty well on a retry image is better than a smash.
    #
    # BUT NOT AN EMPTY CARD, which is what returning here used to mean on the last attempt —
    # Birthing Pod shipped with no cost at all on 2026-08-20. The medallion row below the plate
    # has a whole card's width and no name in it, so it takes the costs this well cannot.
    if span(pip_px) + pad(pip_px) > well_w:
        _cost_medallions(image, face, box, type_box)
        return
    mid = (wy0 + wy1) / 2
    top = round(mid - pip_px / 2)
    top = max(wy0, min(top, wy1 - pip_px))
    y0, y1 = top, top + pip_px
    height = y1 - y0
    right = wx1 - pad(pip_px)
    stamp_x0 = max(wx0, right - span(pip_px))
    layer, _ = _layer((stamp_x0, y0, right, y1))
    _draw_pips(layer, tokens, pip_px, right - stamp_x0, height)
    _paste_pips(image, layer, (stamp_x0, y0, right, y1))


def _title(image, face, box, light=(1, 1)):
    """Name on the left, mana cost on the right, name shortened to clear the cost.

    Closes the pip/name collision (bd mtg-6iy): both are ours now, so the space the cost needs is
    measured and subtracted before the name is laid out, rather than the two being placed
    independently and hoped about.

    CLIENT 2026-08-16, on Craterhoof (`{5}{G}{G}{G}`): "the mana symbols are a bit large on this
    card." They were not drawn larger than usual — the NAME was drawn smaller. The pip used to be
    sized once from the plate and the name then shrank around it, so the more pips a cost had, the
    further the two drifted apart: Raphael's two pips looked right beside a full-size name and
    Craterhoof's four did not. So the two shrink TOGETHER now. The loop is the only honest way to
    do it, because the fit is circular — the pips set how much room the name has, and the name's
    size sets how big the pips are.

    What the loop starts FROM changed on 2026-08-17: `_plate_size`, off the card, rather than a
    fraction of the plate. See NAME_CARD_SIZE. The loop itself is kept and is not the defect — it
    is driven by how long the NAME is, which no amount of fixed geometry can decide for us, and
    replayed over the 58 stored faces it moved only 5 of them.
    """
    x0, y0, x1, y1 = box
    fill, stroke, shadow = panel_palette(image, box, display=True)
    height = y1 - y0
    pad = round(height * PAD) + round((x1 - x0) * 0.015)
    size = _plate_size(box, image.height, NAME_CARD_SIZE, NAME_MAX_OF_BOX)
    tokens = list(reversed(symbols.TOKEN.findall(face.get("mana_cost") or "")))

    def pip_size(at):
        return max(1, round(at * 0.92))

    def cost_width(at):
        """What the pips take, gap included — the loop below spends it before the name."""
        pip_px = pip_size(at)
        return len(tokens) * pip_px + max(0, len(tokens) - 1) * round(pip_px * PIP_GAP)

    font = ImageFont.truetype(str(fonts.DISPLAY), size)
    tracking = size * TRACKING
    room = (x1 - x0) - 3 * pad
    while size > 11 and _tracked_width(font, face["name"], tracking) > room - cost_width(size):
        size -= 1
        font = ImageFont.truetype(str(fonts.DISPLAY), size)
        tracking = size * TRACKING

    pip_px = pip_size(size)
    layer, draw = _layer(box)
    _draw_pips(layer, tokens, pip_px, (x1 - x0) - pad, height)
    ascent, descent = font.getmetrics()
    _write_tracked(
        draw,
        (pad, (height - (ascent + descent)) / 2),
        face["name"],
        font,
        fill,
        stroke,
        size,
        tracking,
    )
    _stamp(image, layer, box, size, shadow, light)


def _display(image, text, box, light=(1, 1), *, size):
    """Type line and P/T: centred and stroked, at a size the CALLER decided.

    There is no box-relative fallback any more. Both callers now size from the card and clamp to
    the box — the P/T since 2026-08-16 and the type line since 2026-08-17 — because sizing a field
    off its own detected box is what made it vary 3.6x across a batch.

    The width fit below stays, and it is a different thing: it answers "is this STRING too long for
    this plate", not "how big is this plate". A type line runs from "Land" to "Legendary Artifact
    Creature — Phyrexian Horror", and only the string can decide that.
    """
    x0, y0, x1, y1 = box
    fill, stroke, shadow = panel_palette(image, box, display=True)
    height, available = y1 - y0, (x1 - x0) * (1 - 2 * PAD)
    font = ImageFont.truetype(str(fonts.DISPLAY), size)
    tracking = size * TRACKING
    while size > 11 and _tracked_width(font, text, tracking) > available:
        size -= 1
        font = ImageFont.truetype(str(fonts.DISPLAY), size)
        tracking = size * TRACKING
    layer, draw = _layer(box)
    ascent, descent = font.getmetrics()
    _write_tracked(
        draw,
        (
            ((x1 - x0) - _tracked_width(font, text, tracking)) / 2,
            (height - (ascent + descent)) / 2,
        ),
        text,
        font,
        fill,
        stroke,
        size,
        tracking,
    )
    _stamp(image, layer, box, size, shadow, light, occlude=False)


def _rules_panels(rules):
    """`rules` as a list of panels, whether it arrived as one panel or several.

    `generation.panels.detect` returns a list now, but a single 4-tuple is what every stored
    detection and every hand-written test carries, and one panel is still a legitimate outcome —
    a one-ability card gets one strip. Sorted top to bottom so paragraph order follows the card
    rather than whatever order the detector happened to report.
    """
    if rules and all(isinstance(value, (int, float)) for value in rules):
        return [tuple(rules)]
    return sorted((tuple(panel) for panel in rules), key=lambda panel: panel[1])


def _assign(text, areas):
    """Oracle paragraphs packed into panels by CAPACITY, top to bottom.

    Scryfall separates abilities with newlines, so the paragraph count is known before anything is
    painted — but one paragraph per strip is the wrong rule, and this is measured rather than
    guessed. Every strip shares one type size (`textlayout.fit_across`), so the size is capped by
    the WORST-fitting strip; give a three-line ability a short strip and a bare "Flying" a tall
    one and the whole card is set to whatever the three-line ability can survive, leaving the
    other strips reading as empty parchment. That is exactly what the first framed generation did.

    So paragraphs are dealt out in proportion to the area each strip actually has. `areas` is one
    (width, height) per strip, in the order they appear down the card; a strip with twice the
    room takes roughly twice the text. Order is never changed — abilities read top to bottom on a
    real card — and no strip is left empty while text remains, because an empty strip is a
    painted surface with nothing on it, which reads as a mistake rather than as a design.

    Leftovers land in the last strip rather than being dropped: a card missing an ability is a
    wrong card, and a crowded final strip is merely tight.
    """
    paragraphs = [p for p in text.split("\n") if p.strip()]
    if len(areas) <= 1 or len(paragraphs) <= 1:
        return ["\n".join(paragraphs)] if paragraphs else []
    if len(areas) >= len(paragraphs):
        return paragraphs

    capacity = [max(1, width * height) for width, height in areas]
    per_unit = sum(len(p) for p in paragraphs) / sum(capacity)
    out, index = [], 0
    for slot, room in enumerate(capacity):
        # Always leave one paragraph for each strip still to come, so none is left bare.
        spare = len(paragraphs) - index - (len(capacity) - slot - 1)
        taken, used = [], 0
        while index < len(paragraphs) and len(taken) < spare:
            taken.append(paragraphs[index])
            used += len(paragraphs[index])
            index += 1
            if used >= room * per_unit:
                break
        out.append("\n".join(taken))
    if index < len(paragraphs):
        out[-1] = "\n".join([out[-1]] + paragraphs[index:]).strip("\n")
    return out


def _divider(draw, x, y, width, colour):
    """The hairline a real card rules between its rules text and its flavour text.

    Drawn as a soft-ended line rather than a full-width rule: on a painted parchment strip a hard
    edge-to-edge bar reads as a UI element, where a line that fades out at both ends reads as
    printed. Same reason the panels are not plain rectangles.
    """
    inset = round(width * 0.08)
    draw.line((x + inset, y, x + width - inset, y), fill=colour[:3] + (110,), width=1)


def _rules(image, text, boxes, shield=None, light=(1, 1), flavour=""):
    """Rules text across one or more panels — one oracle paragraph per panel.

    MEASURED 2026-08-10 against their own full-resolution Terror of the Peaks: they set the three
    abilities on three separate pale strips. Ours put all of it in one slab, which is why their
    body text is 1.4x ours on an identical 1792x2400 canvas — a strip holding two lines can be
    set far larger than a slab holding five. bd mtg-yp3 saw the second panel and recorded it as
    variance; across the gallery it is the norm.

    Each panel is drawn into a layer its own size and clipped to it, because overflow has to stay
    inside the furniture: Atraxa's keywords plus a proliferate reminder hit the size floor and
    spilled onto the artwork, which reads as a broken card, where losing the tail of a line
    inside a panel reads as text that is merely long.

    Every panel gets its own ink, sampled from its own pixels — the strips are painted separately
    and do not all come back the same colour — but they share ONE size (`textlayout.fit_across`).
    """
    measures = []
    for x0, y0, x1, y1 in boxes:
        pad_x, pad_y = round((x1 - x0) * RULES_PAD), round((y1 - y0) * RULES_PAD)
        measures.append(((x1 - x0) - 2 * pad_x, (y1 - y0) - 2 * pad_y))
    paragraphs = _assign(text, measures)
    boxes = boxes[: len(paragraphs)]
    # Flavour text belongs to the LAST panel, after every rule. Splitting it across panels would
    # put uncoloured prose above game text, and a player has to be able to tell at a glance which
    # words are rules.
    flavours = [""] * len(paragraphs)
    if flavour and flavours:
        flavours[-1] = flavour

    inner, pads, excludes = [], [], []
    for box in boxes:
        x0, y0, x1, y1 = box
        pad_x, pad_y = round((x1 - x0) * RULES_PAD), round((y1 - y0) * RULES_PAD)
        width, height = (x1 - x0) - 2 * pad_x, (y1 - y0) - 2 * pad_y
        pads.append((pad_x, pad_y))
        inner.append((width, height))
        # Where the P/T shield eats into a panel, the lines that reach it are shortened. Only the
        # panel it actually overlaps is narrowed, which is the gain from having several.
        exclude = None
        if shield:
            sx0, sy0 = shield[0], shield[1]
            if sy0 < y1 and sx0 < x1 and shield[3] > y0:
                narrow = max(width * 0.35, (sx0 - x0) - pad_x - round((x1 - x0) * 0.02))
                exclude = (max(0, sy0 - y0 - pad_y), narrow)
        excludes.append(exclude)

    ceiling = image.height * RULES_SIZE
    size, laid = textlayout.fit_across(
        paragraphs, inner, ceiling, excludes=excludes, flavours=flavours
    )
    # A line that straddles the shield's top edge still runs into it, because a line is measured
    # by its top and drawn downwards. Pull each exclusion up by one line and re-fit.
    if any(excludes):
        excludes = [
            (max(0, e[0] - lh), e[1]) if e else None
            for e, (_, lh, _) in zip(excludes, laid)
        ]
        # `flavours` has to come along: this re-fit's `laid` is what actually gets DRAWN, and
        # dropping it here printed no flavour text at all on any creature whose P/T shield
        # overlaps its rules panel — which on a borderless card is the normal layout, not an edge
        # case (bd mtg-4qa). Silent, because the card still looked finished.
        size, laid = textlayout.fit_across(
            paragraphs, inner, ceiling, excludes=excludes, flavours=flavours
        )

    overflowed = size < image.height * RULES_MIN
    for box, (pad_x, pad_y), (width, height), (lines, lh, pip_px) in zip(boxes, pads, inner, laid):
        fill, stroke, shadow = panel_palette(image, box)
        total = textlayout.block_height(lines, lh)
        overflowed = overflowed or total > height
        gap = round(lh * textlayout.PARAGRAPH_GAP)
        layer, draw = _layer(box)
        y = pad_y + (max(0, height - total) / 2)
        for index, (line, starts_paragraph) in enumerate(lines):
            if starts_paragraph and index:
                y += gap
            if textlayout.starts_flavour(line) and index:
                _divider(draw, pad_x, y - round(gap * 0.45), width, fill)
            _line(layer, draw, line, pad_x, y, size, pip_px, fill, stroke)
            y += lh
        # `_stamp` runs the occlusion pass now, for every surface rather than this one.
        _stamp(image, layer, box, size, shadow, light)
    return overflowed


def _line(layer, draw, atoms, x, y, size, pip_px, fill, stroke):
    """One wrapped line of words and pips, left to right.

    A keyword-only paragraph ("Flying") is set larger and heavier, which both a real card and the
    reference site do — theirs sets it in the display face at roughly 1.3x the body.
    """
    # A keyword line goes in the DISPLAY face, not the bold text face. Seen at native pixels
    # 2026-08-10: the reference site's "Flying" is set in its display face with flat flared
    # serifs, while ours was PT Serif Bold — the same text face, just heavier, which is why it
    # read as emphasis rather than as card typography.
    keyword = bool(atoms) and atoms[0].keyword and not atoms[0].symbol
    body = round(size * 1.28) if keyword else size
    regular = ImageFont.truetype(str(fonts.DISPLAY if keyword else fonts.REGULAR), body)
    italic = ImageFont.truetype(str(fonts.ITALIC), body)
    space = regular.getlength(" ")
    ascent, _ = regular.getmetrics()
    pip = round(pip_px * 1.28) if keyword else pip_px

    previous = None
    for atom in atoms:
        if previous is not None:
            x += 0.0 if (atom.symbol and previous.symbol) else space
        if atom.symbol:
            art = symbols.pip(atom.text, pip)
            if art is None:
                # An unresolvable symbol is drawn as its literal token, never dropped: a cost
                # short one pip is a wrong card that looks like a right one (CLAUDE.md).
                _write(draw, (x, y), atom.text, regular, fill, stroke, body)
                x += regular.getlength(atom.text)
            else:
                layer.alpha_composite(art, (round(x), round(y + ascent - pip)))
                x += pip
        else:
            font = italic if atom.italic else regular
            _write(draw, (x, y), atom.text, font, fill, stroke, body)
            x += font.getlength(atom.text)
        previous = atom
