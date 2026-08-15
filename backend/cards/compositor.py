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

So text is built up in layers per panel — cast shadow, stroke, fill, emboss —
with one blur per panel rather than one per glyph, which is what keeps it affordable across a
100-card deck.

REVISED 2026-08-10 against their FULL-RESOLUTION original rather than a gallery thumbnail: the
type treatment here is close and the remaining gap is not a blend effect, it is SIZE and LAYOUT.
See the note above `_stamp`, and `generation.panels` for the multi-panel finding.
"""

import colorsys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from cards import fonts, symbols, textlayout

PAD = 0.055
# Display sizes as a fraction of their plate's height. RAISED 2026-08-10: theirs fill their
# plates and ours sat inside a ring of bare stone, which is the same "smaller and less readable"
# report as the rules text and the same cause. The plate the detector reports includes the carved
# rim, so a fraction of it is already conservative before PAD is taken off.
NAME_SIZE = 0.68
TYPE_SIZE = 0.66
# Ceiling as a fraction of CARD height. Their rules text fills its panel; ours sat at half the
# size and floated in empty stone, because this was 0.030.
RULES_SIZE = 0.055
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
# VALIDATED 2026-08-15 (bd mtg-8h9, spikes/measure_rules_size.py) against n=40 real printed
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

# Negative tracking, as a fraction of the font size. Real card titles are set tight; Pillow has
# no letter-spacing, so display runs are drawn glyph by glyph to get it.
TRACKING = -0.018

SHADOW_ALPHA = 165
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
        return ink, (0, 0, 0, 235), _hsv(h, min(1.0, sat * 1.1), val * 0.20, SHADOW_ALPHA)
    # Dark text on pale material: no stroke. A light stroke at 5.5% of the glyph size eats the
    # letterform from outside and black ends up reading grey.
    return (
        _hsv(h, min(1.0, sat * 1.7), val * 0.12),
        None,
        _hsv(h, min(1.0, sat * 1.5), val * 0.42, 150),
    )


def _box(panel, size):
    """Panel in 0-1 fractions -> pixel box, clamped to the canvas."""
    w, h = size
    x0, y0, x1, y1 = panel
    x0, x1 = sorted((max(0, round(x0 * w)), min(w, round(x1 * w))))
    y0, y1 = sorted((max(0, round(y0 * h)), min(h, round(y1 * h))))
    return x0, y0, x1, y1


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


def _stamp(image, layer, box, size, colour, direction=(1, 1)):
    """Composite a finished text layer onto the card, its own cast shadow first.

    The shadow is the layer's own alpha, tinted, blurred and offset away from the scene's light,
    so one blur covers everything drawn into this panel rather than one per glyph. Nothing is
    added at zero offset and the glyphs are not softened — see the note above on why a halo and
    a sub-pixel blur were tried and measured to be wrong.
    """
    offset = max(1, round(size * SHADOW_OFFSET))
    image.alpha_composite(
        _spread(layer, colour, max(1, round(size * SHADOW_BLUR)), colour[3]),
        (box[0] + offset * direction[0], box[1] + offset * direction[1]),
    )
    image.alpha_composite(layer, (box[0], box[1]))


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


def compose(png, face, panels, include_flavor_text=False):
    """(finished card, whether the rules text overflowed its panel).

    A panel the detector did not find is skipped rather than guessed at — a card missing its type
    line is obvious, while a type line printed over the art looks like a design choice. The
    overflow flag means the AI painted a slab too small for this card's text, which is a reason to
    regenerate the art rather than something the compositor can fix.
    """
    image = Image.open(png).convert("RGBA") if not isinstance(png, Image.Image) else png.copy()
    light = light_direction(image)

    if panels.get("title"):
        _title(image, face, _box(panels["title"], image.size), light)
    if panels.get("type"):
        _display(image, face["type_line"], _box(panels["type"], image.size), TYPE_SIZE, light)
    overflowed = False
    if panels.get("rules") and face.get("oracle_text"):
        shield = _box(panels["pt"], image.size) if panels.get("pt") else None
        boxes = [_box(panel, image.size) for panel in _rules_panels(panels["rules"])]
        # Named to match the reference site's own generate payload, so the frontend passes its
        # toggle straight through. Off by default: flavour text competes with the rules for the
        # one panel we get, and rules text losing size to prose is the worse trade.
        flavour = (face.get("flavor_text") or "") if include_flavor_text else ""
        overflowed = _rules(image, face["oracle_text"], boxes, shield, light, flavour)
    if panels.get("pt") and face.get("power") is not None:
        pt = f"{face['power']}/{face['toughness']}"
        _display(image, pt, _box(panels["pt"], image.size), 0.50, light)
    return image, overflowed


def _title(image, face, box, light=(1, 1)):
    """Name on the left, mana cost on the right, name shortened to clear the cost.

    Closes the pip/name collision (bd mtg-6iy): both are ours now, so the space the cost needs is
    measured and subtracted before the name is laid out, rather than the two being placed
    independently and hoped about.
    """
    x0, y0, x1, y1 = box
    fill, stroke, shadow = panel_palette(image, box, display=True)
    height = y1 - y0
    pad = round(height * PAD) + round((x1 - x0) * 0.015)
    size = max(12, round(height * NAME_SIZE))
    pip_px = max(1, round(size * 0.92))

    layer, draw = _layer(box)
    x = (x1 - x0) - pad
    for token in reversed(symbols.TOKEN.findall(face.get("mana_cost") or "")):
        pip = symbols.pip("{" + token + "}", pip_px)
        if pip is None:
            continue
        x -= pip_px
        layer.alpha_composite(pip, (round(x), round((height - pip_px) / 2)))
        x -= round(pip_px * 0.10)

    available = x - 2 * pad
    font = ImageFont.truetype(str(fonts.DISPLAY), size)
    tracking = size * TRACKING
    while size > 11 and _tracked_width(font, face["name"], tracking) > available:
        size -= 1
        font = ImageFont.truetype(str(fonts.DISPLAY), size)
        tracking = size * TRACKING
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
        emboss=True,
    )
    _stamp(image, layer, box, size, shadow, light)


def _display(image, text, box, size_fraction, light=(1, 1)):
    """Type line and P/T: centred, embossed, stroked."""
    x0, y0, x1, y1 = box
    fill, stroke, shadow = panel_palette(image, box, display=True)
    height, available = y1 - y0, (x1 - x0) * (1 - 2 * PAD)
    size = max(11, round(height * size_fraction))
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
        emboss=True,
    )
    _stamp(image, layer, box, size, shadow, light)


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
        pad_x, pad_y = round((x1 - x0) * PAD), round((y1 - y0) * PAD)
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
        pad_x, pad_y = round((x1 - x0) * PAD), round((y1 - y0) * PAD)
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
