"""A generation job — the unit the frontend polls.

Their shape, kept deliberately: POST returns a job id, the client polls status. A Creative Full
card is two AI calls and about a minute; a decklist is that times N. Nothing survives a request
that long, so the work happens off the request and the row is the only thing both sides share.
"""

import uuid

from django.db import models


class Job(models.Model):
    QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # `frame_version` in their payload: ART_ONLY or CREATIVE_FULL.
    mode = models.CharField(max_length=20)
    options = models.JSONField(default=dict)
    status = models.CharField(max_length=10, default=QUEUED)
    error = models.TextField(blank=True, default="")

    # Everything the confirm screen needs, decided from Scryfall before a single credit is spent:
    # what we will generate, what Scryfall does not know, and what layout we do not support.
    cards = models.JSONField(default=list)
    unresolved = models.JSONField(default=list)
    unsupported = models.JSONField(default=list)

    # One entry per FACE, appended as each finishes, so a decklist shows cards arriving rather
    # than a spinner: {name, status, image, problems, log}.
    results = models.JSONField(default=list)

    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.mode} {self.id} ({self.status})"
