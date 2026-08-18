# MTG Proxy Card Generator

Paste a card name or a decklist, pick a look, get back printable proxy cards.
The card's real game text is never invented — it comes from Scryfall.

**Current state — Milestone 1 engineering is done.** Waiting on client sign-off
of the ten-style pack (`../Project Material/CLIENT-PACK-PIP-2026-08-19/`) to
close M1. Creative Full letters the card so the scene can cross the words; we
stamp only the mana cost from Scryfall's symbol artwork. Proxies have no set
symbol. Art Only paints no furniture and no text. Prototype UI is in `frontend/`.

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

**Creative Full is lettered.** The AI paints the art and the game text as one picture —
that is the only way a vine can sit in front of the words. We stamp only the mana cost
(Scryfall SVGs). `check.proofread` reads every other field back against Scryfall; a
mismatch repaints. Art Only paints no text at all.

**Mana pips are Scryfall SVGs, not the Mana font.** BUILD-SPEC §16 picked the Mana
font; that turned out not to work. Its glyphs are monochrome and hybrid/Phyrexian pips
aren't glyphs at all — `.ms-wu` is two half-glyphs layered by CSS over a coloured
background. Scryfall ships all 84 symbols as complete full-colour SVGs, which is also
what the reference site composites.
