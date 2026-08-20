# MTG Proxy Card Generator

Paste a card name or a decklist, pick a look, get back printable proxy cards.
The card's real game text is never invented — it comes from Scryfall.

**Current state — Milestone 1 is not closed, and the approach is being changed.**
The client rejected the ten-style pack (`../Project Material/CLIENT-PACK-PIP-2026-08-19/`).
Measuring our output against his own 19 example cards on 2026-08-20 found the cause: his
cards average 2.3 straight plate rims each, ours 12.9. Colour, texture, canvas and model
already match his corpus almost exactly — the gap is that we compose text into rectangles
and he draws it into objects.

So the primary path becomes: show the model exemplar cards, let it letter every field
including the mana cost, and grade every glyph and symbol against Scryfall. `--composited`
becomes the fallback after three failed attempts. `--name-lettered` is being deleted
(measured 0/7). Proxies have no set symbol. Art Only paints no furniture and no text.

Read before touching the pipeline: `../SPEC-CHANGE-2026-08-20.md` (what changed and why),
`../PLAN-EXEMPLAR-PIVOT-2026-08-20.md` (the phased plan), `../STATUS-2026-08-20.md`
(measurements). The acceptance criterion is
`../Project Material/CLIENT-FAVORITES-2026-08-19/` and his seven-card sheet `5 (1).png` —
not the reference site.

Proposal: `../Project Material/`. Prototype UI: `frontend/`.

## Layout

```
backend/    Django + DRF. Scryfall lookup, prompt building, Gemini calls,
            grading and the repaint loop all live in one process, because
            verification has to re-read the *finished* card, not the raw
            AI output. Compositing is the fallback path.
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
- `backend/assets/exemplars/<archetype>/` — reference cards attached to each image
  request, **not committed**, built by `manage.py prepare_exemplars`. They are the
  client's own third-party proxy art; an owned set is Milestone 2 and a prerequisite for
  shipping. A clean clone has none, so `generation/exemplars.py` raises rather than
  quietly generating an unconditioned card. See its docstring.

```bash
# One card through the exemplar path. Without --archetype the older prose brief runs.
uv run python manage.py prepare_exemplars '../../Project Material/CLIENT-FAVORITES-2026-08-19'
uv run python manage.py compose_card 'Toski, Bearer of Secrets' \
    --lettered --archetype tangle --exemplars 3 --out /tmp/cards
uv run python manage.py score /tmp/cards --baseline '../../Project Material/CLIENT-FAVORITES-2026-08-19'
```

## Two decisions worth knowing before reading the code

**Creative Full is lettered by the AI.** The model paints name, type, rules and P/T into
the scene, so a name can live in an arch and rules text can follow a curve. Accuracy is
not guaranteed by construction; it is guaranteed by inspection — every finished card is
transcribed back and compared character-for-character against Scryfall, and any mismatch
is a repaint. The grader is never shown the expected text, because a checker given the
answer grades the answer. Art Only paints no text at all.

The **mana cost is the one field we still stamp** by default, and handing it over is built and
measured behind `cost_lettered`, awaiting the switch in Phase 5. The measurement: the model
takes ordinary costs of four pips or fewer essentially always, and every miss it has ever made
is one pattern — ten pips painted as nine, six as five, hybrid `{G/W}` split into two plain
pips, Phyrexian `{G/P}` drawn as plain green. On the seven-card A/B, handing it over took
`cost_no_room` from 3 of 7 to 0 of 7 with no cost of straight-line structure, and one card put
its cost on a medallion row under the plate unprompted.

**A drawn cost is read twice, and both readings have to agree**, and that is the least obvious
thing in this repo. It is read once off the whole card and once off a crop containing the pips
and not the name (`panels.cost_read`), and `check._cost_disagreement` repaints the card when
the two differ. Neither reader is trustworthy alone, and they were both caught: the whole-card
one recognises the card from the name printed on it and reports the cost it *remembers*, and
the cropped one, handed a definition of a hybrid pip and a coloured disc inside a pale ring,
finds the two colours the definition asks for. Each let a wrong cost ship on 2026-08-20, one
of them stored `ok`, and never the same card. Requiring them to concur was right 5 of 5 on the
hardest costs in the format and cost no extra repaint across seven ordinary ones.

The general lesson, worth more than the mechanism: **one vision reading is not evidence.** Ask
twice, differently, and treat disagreement as the defect — a cost a careful reader misreads is
a cost a player misreads.

**A cost that will not fit the title plate goes on a medallion row under it**, rather than
being dropped — which is what shipped a card with no cost at all. That is also where the
cost sits on 12 of the client's 19 examples, so the fallback is his layout, not a
compromise. The plate placement stays the default because it is the one signed off.
See `PLAN-EXEMPLAR-PIVOT`, Phase 3.

**Mana pips are Scryfall SVGs, not the Mana font** — on the `--composited` fallback path,
which is the only path that still stamps anything. The Mana font's glyphs are monochrome
and hybrid/Phyrexian pips aren't glyphs at all: `.ms-wu` is two half-glyphs layered by CSS
over a coloured background. Scryfall ships all 84 symbols as complete full-colour SVGs.
