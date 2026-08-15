"""Does the model paint the surfaces the brief asked for? Read off the jobs already run.

Every argument about panel geometry on this project has been settled — or worse, not settled — by
looking at one card. `panels.detect`'s boxes are stored on every result now (bd mtg-57t), so the
question "does the model comply" is answerable across every generation ever run, for free and with
no AI call. This is that report.

It compares what `generation.prompts` DEMANDS of each surface against what `panels.detect` FOUND,
per face, and gives a compliance rate. Two things it is deliberately not: it is not a grade (that
is `check.py`, and it runs on the composited card), and it does not open a single image.

    uv run python manage.py compliance                # every job
    uv run python manage.py compliance --card "Elesh" # one card, for repeat sampling
    uv run python manage.py compliance --since 3      # the last 3 jobs
"""

import statistics

from django.core.management.base import BaseCommand

from generation import check, prompts

# `check.TITLE_MAX_Y` is the grade — a plate below it fails the card. The BRIEF asks for something
# stricter, the top tenth, so both are reported: one says "would this ship", the other says "did it
# do what it was told".
BRIEF_TITLE_MAX_Y = 0.10


class Command(BaseCommand):
    help = "How often the model paints the surfaces the brief asked for."

    def add_arguments(self, parser):
        parser.add_argument("--card", default="", help="only faces whose name contains this")
        parser.add_argument("--since", type=int, default=0, help="only the last N jobs")

    def handle(self, *args, **options):
        from generation.models import Job

        jobs = list(Job.objects.order_by("created"))
        if options["since"]:
            jobs = jobs[-options["since"]:]

        rows = []
        for job in jobs:
            by_name = {
                face["name"]: face
                for entry in job.cards
                for face in entry.get("faces", [])
            }
            for result in job.results or []:
                if options["card"].lower() not in result["name"].lower():
                    continue
                panels = result.get("panels")
                if not panels:
                    continue  # Art Only, or a job from before the boxes were kept
                rows.append((job, result, panels, by_name.get(result["name"])))

        if not rows:
            self.stdout.write("No faces with stored panel boxes. Only jobs run after bd mtg-57t "
                              "have them — generate one and run this again.")
            return

        self._report(rows)

    def _report(self, rows):
        self.stdout.write(
            f"{'job':10} {'card':26} {'title y':>8} {'top?':>5} "
            f"{'rules':>7} {'asked':>7} {'met?':>5}  status"
        )
        self.stdout.write("-" * 92)
        titles, strips = [], []
        for job, result, panels, face in rows:
            title = panels.get("title")
            title_y = title[1] if title else None
            at_top = title_y is not None and title_y <= BRIEF_TITLE_MAX_Y
            titles.append(at_top)

            boxes = panels.get("rules") or []
            if boxes and isinstance(boxes[0], (int, float)):
                boxes = [boxes]
            # The brief asks for ONE strip; if the model painted several, what it owes is their
            # combined height, so that is what is measured against the demand.
            height = sum(box[3] - box[1] for box in boxes)
            asked = prompts._strip_height(face)[0] if face and prompts._strip_height(face) else None
            met = asked is not None and height >= asked
            if asked is not None:
                strips.append(met)

            self.stdout.write(
                f"{str(job.pk)[:8]:10} {result['name'][:26]:26} "
                f"{('%.3f' % title_y) if title_y is not None else 'none':>8} "
                f"{'yes' if at_top else 'NO':>5} "
                f"{height:>7.3f} {('%.3f' % asked) if asked else '  -':>7} "
                f"{('yes' if met else 'NO') if asked else '-':>5}  {result['status']}"
            )

        self.stdout.write("")
        self._rate("top plate inside the top tenth", titles)
        self._rate("rules strip at least the height asked for", strips)
        if titles:
            observed = [
                panels["title"][1]
                for _, _, panels, _ in rows
                if panels.get("title")
            ]
            if observed:
                self.stdout.write(
                    f"  title y: median {statistics.median(observed):.3f}, "
                    f"worst {max(observed):.3f} "
                    f"(check.py fails above {check.TITLE_MAX_Y})"
                )

    def _rate(self, label, outcomes):
        if not outcomes:
            return
        met = sum(1 for o in outcomes if o)
        self.stdout.write(f"  {label}: {met}/{len(outcomes)} = {met / len(outcomes):.0%}")
