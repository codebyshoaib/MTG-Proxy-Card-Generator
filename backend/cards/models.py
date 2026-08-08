"""Local cache of resolved Scryfall card objects.

Scryfall asks for 50-100ms between requests and card data changes rarely, while the same
commons recur in every deck someone submits. So resolved cards are kept, and a decklist
costs network only for what we have not seen.

The whole card object is stored as JSON rather than shredded into columns. Scryfall is the
source of truth for card data; a cache that reshapes its source drifts from it, and the
next field the compositor turns out to need (`flavor_text`, `image_uris.art_crop`,
`frame_effects`) is then a migration instead of a dictionary lookup.

This is NOT the generated-card record. BUILD-SPEC 9.1's FRONT/BACK record carries
`generated_image` and `generation_status` and belongs with the job in `generation/`; a DFC
is two of those sharing one row here. Two different things that both have a face position.
"""

from django.db import models


class Card(models.Model):
    """One Scryfall card, cached whole. `cards.scryfall` owns reading and writing it."""

    scryfall_id = models.UUIDField(primary_key=True)
    # Scryfall's own `name`, so a multi-face card is "Fire // Ice" here.
    name = models.CharField(max_length=255, db_index=True)
    layout = models.CharField(max_length=32)
    data = models.JSONField()
    fetched_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
