"""Creative Full, end to end, from the command line.

    uv run python manage.py compose_card "Terror of the Peaks" --style dark_fantasy

Scryfall resolve -> one image call for art and blank furniture -> one vision call for the
surface boxes -> composite Scryfall's own text into them -> check the result is structurally
sound, and repaint once if it is not.

`--from` skips the image call and composites onto a card already on disk, which is what to use
while tuning the compositor: it costs nothing and keeps the layout the same between runs.

Every option is named for the reference site's own POST /api/ai-proxies/generate/ payload, so a
frontend or an API layer maps one-to-one with no translation table in between.
"""

import io
import re
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError
from PIL import ImageDraw

from cards import compositor, scryfall
from generation import check, gemini, panels, prompts, refusals


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def io_bytes(png):
    """PNG bytes as something Image.open accepts."""
    return io.BytesIO(png)


class Command(BaseCommand):
    help = "Generate and composite one Creative Full card."

    def add_arguments(self, parser):
        parser.add_argument("card")
        parser.add_argument("--style", default=None, help="art_style: key, label or free text")
        parser.add_argument("--direction", default=None, help="art_direction")
        parser.add_argument("--palette", default=None, help="color_palette")
        parser.add_argument("--notes", default=None, help="custom_art_notes, free text")
        parser.add_argument(
            "--flavor", action="store_true",
            help="include_flavor_text: print the card's flavour text under its rules",
        )
        parser.add_argument(
            "--no-reference", dest="use_reference", action="store_false",
            help="use_original_art_reference=false: do not attach Scryfall's own art",
        )
        parser.add_argument(
            "--attempts", type=int, default=2,
            help="how many times to paint before accepting a structurally faulty card "
                 "(default 2: measured, about one card in five needs a second)",
        )
        parser.add_argument("--out", default=Path("card-out"), type=Path)
        parser.add_argument(
            "--from", dest="source", default=None, type=Path,
            help="Composite onto this existing empty-furniture PNG instead of generating one.",
        )
        parser.add_argument(
            "--boxes", action="store_true",
            help="Also write a copy with the detected boxes outlined, to check the detector.",
        )

    def handle(
        self, card, style, out, source, boxes, direction, palette, notes, flavor,
        use_reference, attempts, **_,
    ):
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
            face, reference, licensed = self._prepare(face, use_reference)

            attempt, problems = 0, []
            while True:
                attempt += 1
                png = (
                    source.read_bytes()
                    if source
                    else self._paint(face, licensed, reference, style, direction, palette, notes)
                )
                if not source:
                    (out / f"{stem}-blank.png").write_bytes(png)

                # The ability count is a hint for how many pale strips to look for — the brief
                # asks for one, so a second is worth knowing about rather than assuming.
                oracle = face.get("oracle_text") or ""
                detected = panels.detect(
                    png, paragraphs=len([p for p in oracle.split("\n") if p.strip()]) or None
                )
                card_image, overflowed = compositor.compose(
                    io_bytes(png), face, detected, include_flavor_text=flavor
                )
                problems = check.inspect(face, detected, overflowed)

                # Where, not just whether. Across a batch the failure that matters is a surface
                # landing in the wrong place, and that is invisible in a list of keys.
                self.stdout.write(f"{face['name']}: " + self._where(detected))
                if not problems or source or attempt >= max(1, attempts):
                    break
                self.stdout.write(
                    self.style.WARNING(
                        f"  attempt {attempt}: "
                        + "; ".join(problem.detail for problem in problems)
                        + " — repainting"
                    )
                )

            for problem in problems:
                self.stdout.write(self.style.ERROR(f"  UNSOUND [{problem.code}] {problem.detail}"))

            path = out / f"{stem}.png"
            card_image.convert("RGB").save(path)
            report = self.style.WARNING if problems else self.style.SUCCESS
            self.stdout.write(report(f"{path}"))

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

    def _prepare(self, face, use_reference):
        """(face, reference bytes, licensed) — the Scryfall side, done once per card.

        Outside the retry loop deliberately: repainting must not re-download the art or re-ask
        Scryfall which printing to use.
        """
        original = scryfall.art_reference(face)
        url, licensed = original.art_crop, original.licensed
        # The flavour text has to come from the same printing the art does. `resolve()` answers a
        # bare name with the NEWEST printing, which since June 2026 is a licensed crossover for a
        # lot of staples, while `art_reference()` deliberately goes back to the oldest
        # non-crossover one. Left unreconciled, `--flavor` printed Christopher Rush's Alpha
        # Lightning Bolt under flavour text reading "...speaks The Mighty Thor!" — one card
        # wearing two printings.
        if face["is_crossover"] and not licensed:
            face = {**face, "flavor_text": original.flavor_text}
        if not use_reference:
            url = None
        reference = None
        if url:
            response = requests.get(url, headers=scryfall.HEADERS, timeout=30)
            response.raise_for_status()
            reference = response.content
        return face, reference, licensed

    def _paint(self, face, licensed, reference, style, direction, palette, notes):
        """One image call: the card's art and its blank furniture, as PNG bytes.

        Tries the card's own NAME first and falls back to its game identity only once the model
        has actually refused (bd mtg-kx4). Measured on ten licensed-only cards: eight painted the
        real character first try and only the two Marvel ones were refused, so treating every
        crossover as unpaintable loses the likeness the client asked for on eight of them. The
        reference site's gallery agrees — its Raphael, Gimli, Sephiroth and Y'shtola are all named
        and all at full likeness, and in 3265 cards it holds no Marvel card at all.
        """
        attach = bool(reference)
        if not (licensed and refusals.is_refused(face["name"])):
            try:
                return gemini.generate(
                    prompts.creative_full(
                        face, style, reference=attach, licensed=False,
                        direction=direction, palette=palette, notes=notes,
                    ),
                    reference,
                )
            except gemini.NoImage as refusal:
                # A refusal repeats for this prompt forever, so the only useful response is a
                # different prompt. A transient miss is neither remembered nor retried here: it
                # costs the same generation either way and the caller can run the command again.
                if not (licensed and refusal.refused):
                    raise
                refusals.remember(face["name"])
                self.stdout.write(
                    self.style.WARNING(
                        f"  {face['name']}: refused under its own name "
                        f"({refusal.finish_reason}) — repainting from the card's game identity "
                        "instead. Remembered, so this is paid once."
                    )
                )
        return gemini.generate(
            prompts.creative_full(
                face, style, reference=attach, licensed=True,
                direction=direction, palette=palette, notes=notes,
            ),
            reference,
        )

    def _where(self, detected):
        """Every detected surface and where it landed, for reading a batch at a glance."""
        where = []
        for key in ("title", "type", "rules", "pt"):
            panel = detected.get(key)
            if not panel:
                continue
            for one in compositor._rules_panels(panel) if key == "rules" else [panel]:
                where.append(f"{key} y{one[1]:.2f}-{one[3]:.2f} x{one[0]:.2f}-{one[2]:.2f}")
        return "; ".join(where) or "nothing detected"
