"""One generation per face. No repaint. Writes card, prompt, panels, then sheet.png.

    cd backend && uv run python packs/_oneshot_seven.py packs/verify-oneshot-seven.json
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import django

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from generation import bleed, exemplars, gemini, pipeline, prompts  # noqa: E402
from generation.pipeline import Options, _letter, prepare  # noqa: E402

OPTIONS = (
    "art_style", "art_direction", "color_palette", "custom_art_notes", "include_flavor_text",
    "use_original_art_reference", "borderless", "lettered", "name_lettered", "archetype",
    "exemplar_count", "cost_lettered",
)


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-").replace("--", "-")


def _sheet(paths: list[Path], dest: Path) -> None:
    """Simple contact sheet — thumbs in one row of 4 + one of 3, labels under each."""
    cards = [Image.open(p).convert("RGB") for p in paths]
    thumb_w, gap, label_h, pad = 280, 12, 28, 16
    thumb_h = int(thumb_w * cards[0].height / cards[0].width)
    rows = [cards[:4], cards[4:]]
    row_paths = [paths[:4], paths[4:]]
    width = pad * 2 + 4 * thumb_w + 3 * gap
    height = pad * 2 + 2 * (thumb_h + label_h) + gap
    sheet = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except OSError:
        font = ImageFont.load_default()

    y = pad
    for row, row_p in zip(rows, row_paths):
        x = pad
        for card, path in zip(row, row_p):
            thumb = card.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            sheet.paste(thumb, (x, y))
            label = path.stem.replace("-", " ")
            draw.text((x, y + thumb_h + 4), label[:34], fill=(220, 220, 220), font=font)
            x += thumb_w + gap
        y += thumb_h + label_h + gap
    sheet.save(dest)


def main() -> int:
    spec_path = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "packs" / "verify-oneshot-seven.json")
    loaded = json.loads(spec_path.read_text(encoding="utf-8"))
    options = Options(**{k: loaded[k] for k in OPTIONS if k in loaded})
    out = spec_path.parent / spec_path.stem
    out.mkdir(parents=True, exist_ok=True)

    attached = (
        exemplars.load(options.archetype, options.exemplar_count) if options.archetype else []
    )
    results = []
    card_paths: list[Path] = []

    for name in loaded["cards"]:
        print(f"\n=== {name}", flush=True)
        started = time.monotonic()
        try:
            faces = pipeline.faces_of(name)
        except pipeline.Rejected as rejected:
            results.append({"name": name, "status": "rejected", "error": rejected.detail})
            print(f"  rejected: {rejected.detail}", flush=True)
            continue

        for face in faces:
            suffix = "" if face["face_position"] == "SINGLE" else f"-{face['face_position'].lower()}"
            stem = f"{_slug(face['name'])}{suffix}"
            try:
                face, reference, licensed = prepare(face, options.use_original_art_reference)
                prompt = prompts.creative_full(
                    face,
                    options.art_style,
                    reference=bool(reference),
                    licensed=False,
                    direction=options.art_direction,
                    palette=options.color_palette,
                    notes=options.custom_art_notes,
                    borderless=options.borderless,
                    corrections=(),
                    lettered=options.lettered,
                    name_lettered=options.name_lettered,
                    archetype=options.archetype,
                    exemplars=len(attached),
                    cost_lettered=options.cost_lettered,
                )
                (out / f"{stem}-prompt.txt").write_text(prompt, encoding="utf-8")
                print(f"  prompt -> {stem}-prompt.txt ({len(prompt)} chars)", flush=True)

                # ONE image call. No grade-and-repaint loop.
                png = gemini.generate(prompt, reference, exemplars=attached)
                if options.borderless:
                    png, depth = bleed.trim(png)
                    if depth:
                        print(f"  trimmed {depth:.1%} painted margin", flush=True)

                card, detected, problems = _letter(png, face, options)
                (out / f"{stem}-blank.png").write_bytes(png)
                (out / f"{stem}-panels.json").write_text(
                    json.dumps(detected, indent=2, sort_keys=True), encoding="utf-8"
                )
                card_path = out / f"{stem}.png"
                card.convert("RGB").save(card_path)
                card_paths.append(card_path)

                for problem in problems:
                    print(f"  UNSOUND [{problem.code}] {problem.detail}", flush=True)
                results.append({
                    "name": face["name"],
                    "stem": stem,
                    "status": "unsound" if problems else "ok",
                    "seconds": round(time.monotonic() - started, 1),
                    "problems": [{"code": p.code, "detail": p.detail} for p in problems],
                    "prompt_chars": len(prompt),
                    "exemplars": len(attached),
                    "licensed_fallback": licensed,
                })
                print(f"  saved {stem}.png ({results[-1]['status']})", flush=True)
            except Exception as failure:
                print(f"  failed: {failure}", flush=True)
                results.append({
                    "name": face["name"],
                    "stem": stem,
                    "status": "failed",
                    "seconds": round(time.monotonic() - started, 1),
                    "error": str(failure),
                    "traceback": traceback.format_exc(),
                })

    (out / "_pack.json").write_text(
        json.dumps({**loaded, "options": options._asdict(), "oneshot": True, "attempts": 1}, indent=2),
        encoding="utf-8",
    )
    (out / "_job.json").write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")

    if card_paths:
        _sheet(card_paths, out / "sheet.png")
        print(f"\nsheet -> {out / 'sheet.png'}", flush=True)

    ok = sum(1 for r in results if r.get("status") == "ok")
    unsound = sum(1 for r in results if r.get("status") == "unsound")
    broken = len(results) - ok - unsound
    print(f"\n{ok} ok, {unsound} unsound, {broken} failed -> {out}", flush=True)
    return 0 if broken == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
