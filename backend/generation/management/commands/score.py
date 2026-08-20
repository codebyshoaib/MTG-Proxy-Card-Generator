"""Score a batch's STRUCTURE against the client's corpus. No AI calls, no spend.

    uv run python manage.py score ../../Project\\ Material/LETTERED-DAILY-2026-08-20 \\
        --baseline ../../Project\\ Material/CLIENT-FAVORITES-2026-08-19

The point of it is `--baseline`. A batch's own numbers say nothing on their own; the same batch
next to his 19 favorites says whether a change moved toward his cards or away from them, which
is the question every phase of the exemplar pivot has to answer.

Phase 0 of `../PLAN-EXEMPLAR-PIVOT-2026-08-20.md`, and first on purpose: every later phase is
unmeasurable without it, and unmeasured iteration is what cost the fortnight before it.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from generation import score


def _cards(root):
    """Every card PNG under `root`, at any depth — his corpus is filed in subfolders."""
    if root.is_file():
        return [root]
    return [
        path
        for path in sorted(root.rglob("*.png"))
        if not path.stem.endswith("-blank") and path.stem != "sheet"
    ]


class Command(BaseCommand):
    help = "Score card structure against the client's corpus. Offline, no AI spend."

    def add_arguments(self, parser):
        parser.add_argument("directory", type=Path)
        parser.add_argument(
            "--baseline", type=Path, default=None,
            help="a corpus to compare against — normally CLIENT-FAVORITES-2026-08-19",
        )
        parser.add_argument(
            "--archetype", default=None,
            help="which gates to grade against: panel exempts the straight-edge limits, "
                 "because the client's flat-graphic cards use boxed captions by design",
        )
        parser.add_argument("--json", dest="as_json", type=Path, default=None)

    def handle(self, directory, baseline, archetype, as_json, **_options):
        paths = _cards(directory)
        if not paths:
            raise CommandError(f"no card PNGs under {directory}")
        measured = [(path.name, score.measure(path)) for path in paths]

        limits = score.gates(archetype)
        self.stdout.write(
            f"\n{directory}  ({len(measured)} cards, "
            f"gates: {archetype or 'default'} {limits})\n"
        )
        self.stdout.write(
            f"{'ruled':>6} {'widest':>7} {'band':>6} {'inner':>6}  card"
        )
        failures = 0
        for name, metrics in sorted(measured, key=lambda row: -row[1]["ruled_rows"]):
            problems = score.grade(metrics, archetype)
            failures += bool(problems)
            self.stdout.write(
                f"{metrics['ruled_rows']:6d} {metrics['widest_edge']:7.2f} "
                f"{metrics['band_structure']:6.1f} {metrics['interior_energy']:6.1f}  "
                f"{name[:44]}"
                + (self.style.ERROR("  " + ", ".join(p.code for p in problems)) if problems else "")
            )

        summary = score.summarise(measured)
        self.stdout.write("")
        for key, stats in summary.items():
            self.stdout.write(
                f"  {key:16} mean={stats['mean']:7.2f}  median={stats['median']:7.2f}  "
                f"min={stats['min']:7.2f}  max={stats['max']:7.2f}"
            )
        verdict = self.style.SUCCESS if not failures else self.style.WARNING
        self.stdout.write(verdict(f"\n  {len(measured) - failures}/{len(measured)} inside the gates"))

        if baseline:
            base = [(path.name, score.measure(path)) for path in _cards(baseline)]
            if not base:
                raise CommandError(f"no card PNGs under {baseline}")
            base_summary = score.summarise(base)
            self.stdout.write(f"\nagainst {baseline} ({len(base)} cards)\n")
            self.stdout.write(f"  {'metric':16} {'theirs':>9} {'ours':>9} {'delta':>9}")
            for key, stats in base_summary.items():
                ours = summary.get(key, {}).get("mean")
                if ours is None:
                    continue
                delta = ours - stats["mean"]
                line = f"  {key:16} {stats['mean']:9.2f} {ours:9.2f} {delta:+9.2f}"
                self.stdout.write(self.style.WARNING(line) if abs(delta) > stats["mean"] else line)
            summary = {"batch": summary, "baseline": base_summary}

        if as_json:
            as_json.write_text(json.dumps(
                {"summary": summary, "cards": {name: dict(m) for name, m in measured}}, indent=2
            ))
            self.stdout.write(f"\nwrote {as_json}")
