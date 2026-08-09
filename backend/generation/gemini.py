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


def generate(prompt, reference=None):
    """PNG bytes for one prompt.

    `reference` is image bytes — Scryfall's `art_crop` — attached ahead of the prompt so the
    model reads the original artwork before the brief that modifies it.

    A response with no image raises. Measured once in 24 generations (handover §7): it is
    transient, but it costs a generation either way, so it must never pass as an empty file.
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
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return part.inline_data.data
    raise RuntimeError(f"{MODEL} returned no image. Model said: {response.text!r}")
