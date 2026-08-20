"""The image call, behind one function (bd mtg-7qz).

Nano Banana Pro is `gemini-3-pro-image`. 3:4 at 2K is exactly the 1792 x 2400 we store
(BUILD-SPEC §4), so the canvas needs no resampling.

Everything model-specific lives here: a per-user API key or a different provider replaces
this file, not the pipeline.
"""

import os
import time

from google import genai
from google.genai import errors, types

MODEL = "gemini-3-pro-image"

# Waits between attempts after an upstream 5xx, in seconds.
#
# MEASURED, twice, in the wild: 'Worldgorger Dragon' died on 503 UNAVAILABLE "Deadline expired
# before operation could complete" on 2026-08-10, and an Elesh Norn repaint died the same way on
# 2026-08-15 (job d15398fc) — the second one on the RETRY call, after the first image had already
# been paid for. A 503 is the upstream being briefly busy and says nothing about the prompt, so
# giving up on it throws away a card the user is paying for (bd mtg-a6u).
#
# Three tries over ~9s, not more: the request itself already carries a long deadline, the caller
# may be one of sixty faces in a deck, and a provider that is still 503ing after this is down
# rather than busy — at which point failing the card quickly beats holding a worker for a minute.
BACKOFF = (1, 3, 5)

_client = None


def client():
    """The genai client, made once. Missing key fails here, before anything is downloaded."""
    global _client
    if _client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set (backend/.env)")
        _client = genai.Client(api_key=key)
    return _client


class NoImage(RuntimeError):
    """The call succeeded and produced no image. Named so a retry loop can catch just this."""

    def __init__(self, message, finish_reason=None):
        super().__init__(message)
        self.finish_reason = finish_reason

    @property
    def refused(self):
        """True when the model declined this prompt rather than merely missing.

        The distinction decides whether retrying is worth a credit. An empty part list is the
        transient miss measured once in 24 generations and is worth one retry; a refusal repeats
        for that prompt forever, so the only useful response is a different prompt.
        """
        return str(self.finish_reason or "").upper().endswith(
            ("PROHIBITED_CONTENT", "SAFETY", "IMAGE_SAFETY", "BLOCKLIST", "RECITATION")
        )


def _call(parts):
    """One image request, retried through a transient upstream 5xx.

    ONLY 5xx. A refusal and a bad request repeat forever for the same prompt, so retrying them
    burns credits to reach the same answer — which is the same distinction `NoImage.refused`
    draws one level up.
    """
    for attempt, wait in enumerate(BACKOFF):
        try:
            return client().models.generate_content(
                model=MODEL,
                contents=parts,
                config=types.GenerateContentConfig(
                    image_config=types.ImageConfig(aspect_ratio="3:4", image_size="2K"),
                ),
            )
        except errors.ServerError:
            # No sleep after the last attempt — there is nothing left to wait for, and this runs
            # inside a worker holding one of four slots for a whole deck.
            if attempt == len(BACKOFF) - 1:
                raise
            time.sleep(wait)


def generate(prompt, reference=None, exemplars=()):
    """PNG bytes for one prompt.

    THE ATTACHMENT ORDER IS A CONTRACT, not an implementation detail:

        exemplar_1 ... exemplar_N,  reference,  prompt

    `prompts.exemplar_full` refers to these images BY POSITION — "the first N images", "the last
    image" — because a model told which image is which can act on it and a model left to guess
    cannot. Reordering them here silently misdescribes them in the brief, which is a fault no
    test downstream can see: the card comes back merely worse.

    The two kinds of image are opposites and that is the whole point of separating them.
    `reference` is Scryfall's `art_crop` and supplies WHO the subject is, with `prompts.REFERENCE`
    forbidding anything about how it is drawn. `exemplars` are the client's own cards and supply
    exactly that — frame construction, surface treatment, lettering — and nothing about subject
    or colour. Passing an exemplar as the reference would take the subject from the wrong image.

    A response with no image raises, carrying the model's own `finish_reason`. There are two
    ways to get one and they are not the same failure: an empty part list is the transient
    miss measured once in 24 generations (handover §7) and is worth a retry, while a
    `finish_reason` of PROHIBITED_CONTENT or SAFETY will repeat for that prompt forever.
    Both cost a generation, so neither may pass as an empty file.
    """
    parts = []
    # PNG: `prepare_exemplars` writes PNG, and mislabelling the mime type of an attached image
    # is the kind of thing that works until the day it does not.
    parts += [types.Part.from_bytes(data=image, mime_type="image/png") for image in exemplars]
    if reference:
        parts.append(types.Part.from_bytes(data=reference, mime_type="image/jpeg"))
    parts.append(prompt)

    response = _call(parts)
    # Every level of this is optional in a refusal: no candidates, a candidate with no
    # content, or content with no parts. Walking it blind turns a refusal into a TypeError
    # that says nothing about why the card failed.
    candidate = (response.candidates or [None])[0]
    parts = getattr(getattr(candidate, "content", None), "parts", None) or []
    for part in parts:
        if part.inline_data:
            return part.inline_data.data
    finish_reason = getattr(candidate, "finish_reason", None)
    raise NoImage(
        f"{MODEL} returned no image (finish_reason={finish_reason}). "
        f"Model said: {getattr(response, 'text', None)!r}",
        finish_reason=finish_reason,
    )
