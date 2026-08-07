#!/usr/bin/env python3
"""Assert the composited-text fonts cover every character MTG cards actually use.

Exists because Debian/Ubuntu ships EBGaramond12-Bold.ttf as a 127-glyph stub with no
em dash — which would have rendered a tofu box in the type line of every card.
Run this after any font change or dependency bump.

    python3 check_fonts.py
"""
import sys
from fontTools.ttLib import TTFont

# ponytail: system paths for now; switch to the vendored fonts/ dir once they're pinned.
FONT_DIR = "/usr/share/fonts/truetype/ebgaramond/"
FACES = {
    "regular": "EBGaramond12-Regular.ttf",
    "italic": "EBGaramond12-Italic.ttf",
    # NOTE: EBGaramond12-Bold.ttf is deliberately absent — the packaged file is a stub.
    # Vendor the real Bold from the upstream release before using a bold weight.
}

# Characters that appear in real Scryfall data. Each maps to why it matters.
REQUIRED = {
    0x2014: "em dash — every type line: 'Legendary Creature — Kavu Pilot'",
    0x2212: "minus sign − planeswalker loyalty costs: '−3:'",
    0x2022: "bullet • modal spells: 'Choose one •'",
    0x00C6: "Æ — Æther Vial, Æther Revolt",
    0x00FB: "û — Lim-Dûl the Necromancer",
    0x00E1: "á — Márton Stromgald",
    0x00ED: "í — Dandân / Ifh-Bíff Efreet",
    0x00F6: "ö — Sögnu",
    0x2019: "’ right single quote — flavour text",
    0x201C: "“ left double quote — flavour text",
    0x201D: "” right double quote — flavour text",
}

# Known-missing and accepted, with the reason. Keeps the check honest instead of loose.
ACCEPTED_MISSING = {
    0x221E: "∞ appears on exactly one card (Mox Lotus); special-case if it ever matters",
}


def main() -> int:
    failures = []
    for label, filename in FACES.items():
        path = FONT_DIR + filename
        try:
            cmap = TTFont(path).getBestCmap()
        except Exception as exc:  # missing file, corrupt file
            failures.append(f"{label} ({filename}): cannot read — {exc}")
            continue

        missing = [f"U+{cp:04X} {why}" for cp, why in REQUIRED.items() if cp not in cmap]
        if missing:
            failures.append(f"{label} ({filename}) missing:\n    " + "\n    ".join(missing))

        # A face this small is a stub, not a real font — catch it explicitly.
        if len(cmap) < 500:
            failures.append(
                f"{label} ({filename}): only {len(cmap)} glyphs — this is a stub file, "
                "vendor the real one from upstream"
            )
        print(f"{label:8s} {filename:28s} {len(cmap):5d} glyphs")

    for cp, why in ACCEPTED_MISSING.items():
        print(f"accepted-missing U+{cp:04X}: {why}")

    if failures:
        print("\nFAIL")
        for f in failures:
            print("  " + f)
        return 1
    print("\nOK — all required glyphs present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
