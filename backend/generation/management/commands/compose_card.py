"""Creative Full, end to end, from the command line.

    uv run python manage.py compose_card "Terror of the Peaks" --style "Dark Fantasy"

Scryfall resolve -> one image call for art and blank furniture -> one vision call for the
surface boxes -> composite Scryfall's own text into them. Four steps, two AI calls, and the
printed text is correct by construction rather than by proofreading.

`--from` skips the image call and composites onto a card already on disk, which is what to use
while tuning the compositor: it costs nothing and keeps the layout the same between runs.
"""

import re
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageDraw

from cards import compositor, scryfall
from generation import gemini, panels, prompts


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class Command(BaseCommand):
    help = "Generate and composite one Creative Full card."

    def add_arguments(self, parser):
        parser.add_argument("card")
        parser.add_argument("--style", default=None)
        parser.add_argument("--direction", default=None)
        parser.add_argument("--palette", default=None)
        parser.add_argument("--out", default=Path("card-out"), type=Path)
        parser.add_argument(
            "--from", dest="source", default=None, type=Path,
            help="Composite onto this existing empty-furniture PNG instead of generating one.",
        )
        parser.add_argument(
            "--boxes", action="store_true",
            help="Also write a copy with the detected boxes outlined, to check the detector.",
        )

    def handle(self, card, style, out, source, boxes, direction, palette, **_):
        found, missing = scryfall.resolve([card])
        if missing:
            raise CommandError(f"Scryfall does not know {missing[0]!r}")
        resolved = found[card]
        if resolved.layout in scryfall.UNSUPPORTED:
            raise CommandError(f"{resolved.name}: layout {resolved.layout} is not supported")

        out.mkdir(parents=True, exist_ok=True)
        for face in scryfall.faces(resolved):
            suffix = "" if face["face_position"] == "SINGLE" else f"-{face['face_position'].lower()}"
            stem = f"{_slug(face['name'])}{suffix}"

            if source:
                png = source.read_bytes()
            else:
                url, licensed = scryfall.art_reference(face)
                reference = None
                if url:
                    response = requests.get(url, headers=scryfall.HEADERS, timeout=30)
                    response.raise_for_status()
                    reference = response.content
                prompt = prompts.creative_full(
                    face, style, reference=bool(url), licensed=licensed,
                    direction=direction, palette=palette,
                )
                png = gemini.generate(prompt, reference)
                (out / f"{stem}-blank.png").write_bytes(png)

            # The ability count is a hint for how many pale strips to look for — the brief asked
            # for one per ability, so the detector may as well know what it is counting.
            oracle = face.get("oracle_text") or ""
            detected = panels.detect(
                png, paragraphs=len([p for p in oracle.split("\n") if p.strip()]) or None
            )
            # Where, not just whether. Across a batch the failure that matters is a surface
            # landing in the wrong place — the name plate came back in the lower third twice on
            # 2026-08-10 — and that is invisible in a list of keys.
            where = []
            for key in ("title", "type", "rules", "pt"):
                panel = detected.get(key)
                if not panel:
                    continue
                for one in (compositor._rules_panels(panel) if key == "rules" else [panel]):
                    where.append(f"{key} y{one[1]:.2f}-{one[3]:.2f} x{one[0]:.2f}-{one[2]:.2f}")
            self.stdout.write(f"{face['name']}: " + "; ".join(where))
            if detected.get("title") and detected["title"][1] > 0.25:
                self.stdout.write(
                    self.style.WARNING(
                        f"  name plate is at y={detected['title'][1]:.2f}, not at the top — the "
                        "model painted the card's surfaces out of order (see "
                        "HOW-THEY-DO-CREATIVE-FULL: their order is invariant across 10 of 10)"
                    )
                )
            for key in ("title", "type", "rules"):
                if key not in detected:
                    self.stdout.write(
                        self.style.WARNING(f"  no {key} surface found — that field is unprinted")
                    )

            card_image, overflowed = compositor.compose(io_bytes(png), face, detected)
            if overflowed:
                self.stdout.write(
                    self.style.WARNING(
                        "  rules text does not fit its panel at a readable size — the AI painted "
                        "the slab too small for this card. Regenerate rather than accept it: "
                        "type that varies card to card is worse across a deck than one tight card"
                    )
                )
            path = out / f"{stem}.png"
            card_image.convert("RGB").save(path)
            self.stdout.write(self.style.SUCCESS(f"{path}"))

            if boxes:
                debug = card_image.copy()
                drawer = ImageDraw.Draw(debug)
                for key, panel in detected.items():
                    strips = compositor._rules_panels(panel) if key == "rules" else [panel]
                    for index, one in enumerate(strips):
                        x0, y0, x1, y1 = compositor._box(one, debug.size)
                        drawer.rectangle((x0, y0, x1, y1), outline=(255, 0, 255), width=6)
                        label = f"{key}{index + 1}" if len(strips) > 1 else key
                        drawer.text((x0 + 10, y0 + 10), label, fill=(255, 0, 255))
                debug.convert("RGB").save(out / f"{stem}-boxes.png")


def io_bytes(png):
    """PNG bytes as something Image.open accepts."""
    import io

    return io.BytesIO(png)
