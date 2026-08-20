"""The API the prototype UI talks to.

Nothing here reaches Scryfall or Gemini: `resolve_decklist` and the worker are both patched, so
what is under test is the contract — their field names in, a job id out, and every rejection
that has to happen BEFORE a card costs a credit.
"""

from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

from generation import prompts
from generation.models import Job

FACE = {"name": "Lightning Bolt", "face_position": "SINGLE"}


def _plan(entries=1, unresolved=(), unsupported=()):
    return {
        "entries": [
            {
                "quantity": 4,
                "card": SimpleNamespace(name=f"Card {n}"),
                "faces": [dict(FACE, name=f"Card {n}")],
            }
            for n in range(entries)
        ],
        "unresolved": list(unresolved),
        "unsupported": list(unsupported),
    }


class OptionsTests(TestCase):
    def test_the_frontend_reads_the_catalogue_from_us(self):
        """One source of truth for 48/21/20. A copy in the frontend is a copy that drifts."""
        body = self.client.get("/api/options/").json()
        self.assertEqual(len(body["art_styles"]), 48)
        self.assertEqual(len(body["art_directions"]), 21)
        self.assertEqual(len(body["color_palettes"]), 20)
        self.assertEqual(body["modes"], ["ART_ONLY", "CREATIVE_FULL"])
        self.assertIn(
            {"value": "dark_fantasy", "label": "Dark Fantasy", "group": "Dark"},
            body["art_styles"],
        )
        # Every option carries the group it belongs to, which is what the `<optgroup>` headings
        # are built from — 48 flat rows is a scroll, not a choice.
        self.assertTrue(all(option["group"] for group in
                            ("art_styles", "art_directions", "color_palettes")
                            for option in body[group]))


class GenerateTests(TestCase):
    def _post(self, body, plan=None):
        with mock.patch(
            "generation.views.scryfall.resolve_decklist", return_value=plan or _plan()
        ) as resolve, mock.patch("generation.views.jobs.start") as start:
            response = self.client.post("/api/generate/", body, content_type="application/json")
        return response, resolve, start

    def test_a_decklist_becomes_a_job_and_the_worker_is_started(self):
        response, _, start = self._post({"decklist": "4 Lightning Bolt"})
        self.assertEqual(response.status_code, 202)
        job = Job.objects.get(pk=response.json()["id"])
        self.assertEqual(job.mode, "CREATIVE_FULL")
        self.assertEqual(job.cards[0]["quantity"], 4)
        start.assert_called_once()

    def test_the_seven_options_arrive_under_their_own_names(self):
        """Their payload field names survive from the select element to the brief — no mapping
        table means nothing to keep in sync (STATUS 2026-08-11)."""
        response, _, _ = self._post({
            "decklist": "Lightning Bolt",
            "frame_version": "ART_ONLY",
            "art_style": "dark_fantasy",
            "art_direction": "cinematic",
            "color_palette": "fire",
            "custom_art_notes": "a wolf in the background",
            "include_flavor_text": True,
            "use_original_art_reference": False,
        })
        job = Job.objects.get(pk=response.json()["id"])
        self.assertEqual(job.mode, "ART_ONLY")
        self.assertEqual(job.options, {
            "art_style": "dark_fantasy",
            "art_direction": "cinematic",
            "color_palette": "fire",
            "custom_art_notes": "a wolf in the background",
            "include_flavor_text": True,
            "use_original_art_reference": False,
            "borderless": True,
            # OURS, not theirs, and never accepted from the body. Creative Full is lettered:
            # the model paints every field except the mana cost. Recorded either way:
            # `job.options` is the only record of what produced a stored card.
            "lettered": True,
            "name_lettered": False,
        })

    def test_custom_style_free_text_folds_into_the_style_field(self):
        """Their payload has two style fields; ours is one field that takes a key or free text,
        which is the same rule `prompts._style_text` already follows."""
        response, _, _ = self._post({"decklist": "x", "custom_style": "wet chalk on slate"})
        job = Job.objects.get(pk=response.json()["id"])
        self.assertEqual(job.options["art_style"], "wet chalk on slate")

    def test_borderless_is_the_default_and_can_be_turned_off(self):
        """Client, 2026-08-13."""
        response, _, _ = self._post({"decklist": "x"})
        self.assertIs(Job.objects.get(pk=response.json()["id"]).options["borderless"], True)
        response, _, _ = self._post({"decklist": "x", "borderless": False})
        self.assertIs(Job.objects.get(pk=response.json()["id"]).options["borderless"], False)

    def test_creative_full_is_lettered_and_the_body_cannot_turn_it_off(self):
        """CLIENT 2026-08-19 favorites: names in objects, furniture in the scene. The model
        letters the card; we stamp mana. Not a payload field — their API has no such switch."""
        response, _, _ = self._post({"decklist": "x"})
        job = Job.objects.get(pk=response.json()["id"])
        self.assertIs(job.options["lettered"], True)
        self.assertIs(job.options["name_lettered"], False)
        Job.objects.all().delete()
        response, _, _ = self._post({"decklist": "x", "lettered": False, "name_lettered": True})
        job = Job.objects.get(pk=response.json()["id"])
        self.assertIs(job.options["lettered"], True)
        self.assertIs(job.options["name_lettered"], False)

    def test_an_unknown_mode_is_refused(self):
        response, resolve, _ = self._post({"decklist": "x", "frame_version": "FRAME_v1"})
        self.assertEqual(response.status_code, 400)
        resolve.assert_not_called()

    def test_an_empty_decklist_is_refused_before_scryfall_is_touched(self):
        response, resolve, _ = self._post({"decklist": "   "})
        self.assertEqual(response.status_code, 400)
        resolve.assert_not_called()

    def test_free_text_over_the_limit_is_refused(self):
        """Their two free-text fields are 500 characters. Unbounded text is a prompt-length bill
        and a way to shout down the brief around it."""
        response, resolve, _ = self._post({"decklist": "x", "custom_art_notes": "a" * 501})
        self.assertEqual(response.status_code, 400)
        resolve.assert_not_called()

    def test_a_decklist_with_nothing_generatable_reports_why(self):
        """No job, no credit, and the confirm screen still gets both lists."""
        plan = _plan(0, unresolved=["Lightnin Bolt"], unsupported=[{"name": "Plane", "layout": "planar"}])
        response, _, start = self._post({"decklist": "Lightnin Bolt"}, plan)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["unresolved"], ["Lightnin Bolt"])
        self.assertEqual(response.json()["unsupported"][0]["layout"], "planar")
        start.assert_not_called()
        self.assertFalse(Job.objects.exists())

    def test_a_decklist_over_the_card_limit_is_refused(self):
        """Every card is two paid calls. An uncapped paste is a bill nobody authorised."""
        from generation import jobs

        response, _, start = self._post({"decklist": "x"}, _plan(jobs.MAX_CARDS + 1))
        self.assertEqual(response.status_code, 400)
        start.assert_not_called()

    def test_unresolved_names_ride_along_on_a_job_that_does_run(self):
        """A 60-card deck with one typo still generates the other 59, and says so."""
        response, _, _ = self._post({"decklist": "x"}, _plan(1, unresolved=["Lightnin Bolt"]))
        self.assertEqual(response.json()["unresolved"], ["Lightnin Bolt"])


class JobStatusTests(TestCase):
    def test_polling_returns_the_faces_finished_so_far(self):
        job = Job.objects.create(
            mode="CREATIVE_FULL",
            cards=[{"quantity": 1, "name": "Lightning Bolt", "faces": [FACE]}],
            results=[{"name": "Lightning Bolt", "status": "ok", "image": "/media/x.png"}],
            status=Job.RUNNING,
        )
        body = self.client.get(f"/api/jobs/{job.pk}/").json()
        self.assertEqual(body["status"], "running")
        self.assertEqual(body["faces"], 1)
        self.assertEqual(body["results"][0]["image"], "/media/x.png")

    def test_an_unknown_job_is_a_404(self):
        self.assertEqual(
            self.client.get("/api/jobs/8e2b0e6c-0000-4000-8000-000000000000/").status_code, 404
        )


class CatalogueTests(TestCase):
    def test_every_catalogue_value_is_one_the_brief_understands(self):
        """The select's values are the keys the brief expands. A value the brief does not know
        would pass through verbatim as a prompt — a silently wrong card, not an error."""
        for value in [option["value"] for option in _values("art_directions")]:
            self.assertIn(value, prompts.DIRECTIONS)
        for value in [option["value"] for option in _values("color_palettes")]:
            self.assertIn(value, prompts.PALETTES)
        for value in [option["value"] for option in _values("art_styles")]:
            self.assertIn(value, prompts.STYLES)


def _values(group):
    from django.test import Client

    return Client().get("/api/options/").json()[group]
