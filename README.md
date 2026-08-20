# MTG Proxy Card Generator

Paste a card name or a decklist, pick a look, get back printable proxy cards.
The card's real game text is never invented — it comes from Scryfall.

**Current state — Milestone 1 is not closed.** The client rejected the ten-style
pack (`../Project Material/CLIENT-PACK-PIP-2026-08-19/`): look ≠ his examples,
mana still off the title frames, text boxes must flow through the card. Creative
Full lets Gemini letter the card (name, type, rules, P/T). We stamp only the mana
cost from Scryfall. `--composited` stamps every field. `--name-lettered` letters
only the name.
Do not send a pack until a daily run of his seven against `5 (1).png` looks like
his examples. Proxies have no set symbol. Art Only paints no furniture and no text.
Prototype UI is in `frontend/`.

Spec: `../BUILD-SPEC.md`. Proposal: `../Project Material/`.

## Layout

```
backend/    Django + DRF. Scryfall lookup, prompt building, Gemini calls,
            text compositing and the verify loop all live in one process,
            because verification has to re-read the *composited* card.
frontend/   Next.js prototype UI.
            Not part of the running system; kept so the numbers stay checkable.
```

One repo, two directories: a change to the generation API and the UI that calls it
lands in one commit, and the client receives one handover at Milestone 3.

## Running the backend

```bash
cd backend
cp .env.example .env          # add GEMINI_API_KEY
uv run python manage.py migrate
uv run python manage.py test
uv run python manage.py runserver
```

`uv` manages the venv; there is no `pip install` step.

## Assets

Fonts and mana symbols are **vendored and committed**, never loaded from the system.

- `backend/assets/fonts/` — EB Garamond (SIL OFL). The Debian-packaged Bold is a
  127-glyph stub with no em dash, which would tofu the type line of every card;
  `cards/tests/test_fonts.py` fails if that ever creeps back in.
- `backend/assets/symbols/` — the 84 official Scryfall symbol SVGs, fetched by
  `manage.py fetch_symbols`. Refresh only when Scryfall adds a symbol.

## Two decisions worth knowing before reading the code

**Creative Full is lettered.** The AI paints name, type, rules and P/T into the
scene so the name can live in an arch or banner and art can cross the words —
that is the only path that has looked like his `5 (1).png`. We stamp Scryfall's
mana pips into a reserved well on the name object (the one field the model got
wrong more than once). `--composited` stamps every field. `--name-lettered` letters
only the name. Art Only paints no text at all.

**Mana pips are Scryfall SVGs, not the Mana font.** BUILD-SPEC §16 picked the Mana
font; that turned out not to work. Its glyphs are monochrome and hybrid/Phyrexian pips
aren't glyphs at all — `.ms-wu` is two half-glyphs layered by CSS over a coloured
background. Scryfall ships all 84 symbols as complete full-colour SVGs, which is also
what the reference site composites.
