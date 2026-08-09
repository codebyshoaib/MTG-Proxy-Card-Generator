"""The image call, behind one function (bd mtg-7qz).

Nano Banana Pro is `gemini-3-pro-image`. 3:4 at 2K is exactly the 1792 x 2400 we store
(BUILD-SPEC §4), so the canvas needs no resampling.

Everything model-specific lives here: a per-user API key or a different provider replaces
this file, not the pipeline.
"""

import os

from google import genai
from google.genai import types

MODEL = "gemini-3-pro-image"

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


def generate(prompt, reference=None):
    """PNG bytes for one prompt.

    `reference` is image bytes — Scryfall's `art_crop` — attached ahead of the prompt so the
    model reads the original artwork before the brief that modifies it.

    A response with no image raises, carrying the model's own `finish_reason`. There are two
    ways to get one and they are not the same failure: an empty part list is the transient
    miss measured once in 24 generations (handover §7) and is worth a retry, while a
    `finish_reason` of PROHIBITED_CONTENT or SAFETY will repeat for that prompt forever.
    Both cost a generation, so neither may pass as an empty file.
    """
    parts = []
    if reference:
        parts.append(types.Part.from_bytes(data=reference, mime_type="image/jpeg"))
    parts.append(prompt)

    response = client().models.generate_content(
        model=MODEL,
        contents=parts,
        config=types.GenerateContentConfig(
            image_config=types.ImageConfig(aspect_ratio="3:4", image_size="2K"),
        ),
    )
    # Every level of this is optional in a refusal: no candidates, a candidate with no
    # content, or content with no parts. Walking it blind turns a refusal into a TypeError
    # that says nothing about why the card failed.
    candidate = (response.candidates or [None])[0]
    parts = getattr(getattr(candidate, "content", None), "parts", None) or []
    for part in parts:
        if part.inline_data:
            return part.inline_data.data
    raise NoImage(
        f"{MODEL} returned no image "
        f"(finish_reason={getattr(candidate, 'finish_reason', None)}). "
        f"Model said: {getattr(response, 'text', None)!r}"
    )
