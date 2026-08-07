"""Vendor Scryfall's card-symbol SVGs into assets/symbols/.

Run once, and again only when Scryfall adds a symbol (a new mechanic, roughly yearly).
The files are committed, so rendering a card never touches the network for a pip.

    uv run python manage.py fetch_symbols
"""

import json
import time

import requests
from django.core.management.base import BaseCommand

from cards.symbols import SYMBOL_DIR, _filename

SYMBOLOGY = "https://api.scryfall.com/symbology"
# Scryfall asks for an identifying User-Agent and 50-100ms between requests.
HEADERS = {"User-Agent": "mtg-proxy-generator/0.1", "Accept": "*/*"}
DELAY = 0.1


class Command(BaseCommand):
    help = "Download the official Scryfall mana/card symbol SVGs into assets/symbols/"

    def handle(self, *args, **options):
        SYMBOL_DIR.mkdir(parents=True, exist_ok=True)
        data = requests.get(SYMBOLOGY, headers=HEADERS, timeout=30).json()["data"]

        written = 0
        for sym in data:
            dest = SYMBOL_DIR / f"{_filename(sym['symbol'])}.svg"
            svg = requests.get(sym["svg_uri"], headers=HEADERS, timeout=30).content
            dest.write_bytes(svg)
            written += 1
            time.sleep(DELAY)

        # Keep the metadata too: `represents_mana` and `appears_in_mana_costs` decide
        # what may legally appear in a cost line vs. only in rules text.
        (SYMBOL_DIR / "symbology.json").write_text(
            json.dumps(
                {
                    s["symbol"]: {
                        "file": f"{_filename(s['symbol'])}.svg",
                        "english": s["english"],
                        "represents_mana": s["represents_mana"],
                        "appears_in_mana_costs": s["appears_in_mana_costs"],
                    }
                    for s in data
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"vendored {written} symbols to {SYMBOL_DIR}"))
