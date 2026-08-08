"""Warm the local Card cache from a decklist, so building offline has real data.

    uv run python manage.py fetch_cards                 # the layout-coverage deck below
    uv run python manage.py fetch_cards mydeck.txt

db.sqlite3 is gitignored, so a fresh checkout has an empty cache and every compositor or
prompt-builder change means another round trip to Scryfall. Run this once per checkout.

MEASURED 2026-08-08 by running it: Scryfall's `layout` is NOT the render layout.
`Teferi, Hero of Dominaria` is layout `normal`, `Bottomless Pool // Locker Room` is
`split`, `Invasion of Alara` is `transform` — there is no `planeswalker` or `room` layout
in the API at all. Whatever decides how to draw a card must read `type_line` and the
presence of `loyalty`, never `layout` alone.
"""

from django.core.management.base import BaseCommand

from cards import scryfall

# One card per row of BUILD-SPEC 9's build sequence, plus a rejected layout and a name
# Scryfall does not know, so a run exercises both failure paths as well as the happy one.
COVERAGE = """
1 Craterhoof Behemoth
1 Birds of Paradise
1 Dark Ritual
1 Demonic Tutor
1 Sol Ring
1 Huntmaster of the Fells // Ravager of the Fells
1 Turntimber Symbiosis // Turntimber, Serpentine Wood
1 Teferi, Hero of Dominaria
1 History of Benalia
1 Fire // Ice
1 Bottomless Pool // Locker Room
1 Bonecrusher Giant // Stomp
1 Barbarian Class
1 Invasion of Alara // Awaken the Maelstrom
1 Student of Warfare
1 Erayo, Soratami Ascendant
1 Bruna, the Fading Light
1 Phyrexian Fleshgorger
1 Auspicious Starrix
1 Academy at Tolaria West
1 Notarealcardatall
"""


class Command(BaseCommand):
    help = "Resolve a decklist through Scryfall into the local Card cache"

    def add_arguments(self, parser):
        parser.add_argument("decklist", nargs="?", help="path; omit for the coverage deck")

    def handle(self, *args, **options):
        path = options["decklist"]
        text = open(path, encoding="utf-8").read() if path else COVERAGE
        plan = scryfall.resolve_decklist(text)

        for entry in plan["entries"]:
            card = entry["card"]
            faces = ",".join(f["face_position"] for f in entry["faces"])
            self.stdout.write(f"  {card.name[:50]:52} {card.layout:12} {faces}")
        for bad in plan["unsupported"]:
            self.stdout.write(self.style.WARNING(f"  unsupported: {bad['name']} ({bad['layout']})"))
        for name in plan["unresolved"]:
            self.stdout.write(self.style.ERROR(f"  unresolved:  {name}"))

        credits = sum(e["quantity"] * len(e["faces"]) for e in plan["entries"])
        self.stdout.write(
            self.style.SUCCESS(f"cached {len(plan['entries'])} cards, {credits} credits' worth of faces")
        )
