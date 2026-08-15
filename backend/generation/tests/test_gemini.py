"""The image call's retry policy. No network: the client is mocked and only the loop is under test.

A 503 costs a card the user has paid for, and it has now happened twice in the wild — Worldgorger
Dragon on 2026-08-10 and an Elesh Norn repaint on 2026-08-15 (job d15398fc), the second on the
retry call after the first image had already been paid for (bd mtg-a6u).
"""

from unittest import mock

from django.test import SimpleTestCase
from google.genai import errors

from generation import gemini


def _busy():
    """A 503 shaped the way google.genai raises one."""
    return errors.ServerError("503 UNAVAILABLE", None)


class RetryTests(SimpleTestCase):
    def setUp(self):
        sleep = mock.patch.object(gemini.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def _client(self, side_effect):
        models = mock.Mock()
        models.generate_content.side_effect = side_effect
        return mock.patch.object(gemini, "client", return_value=mock.Mock(models=models)), models

    def test_a_transient_503_is_retried_and_the_card_survives(self):
        patch, models = self._client([_busy(), _busy(), "the-response"])
        with patch:
            self.assertEqual(gemini._call(["prompt"]), "the-response")
        self.assertEqual(models.generate_content.call_count, 3)

    def test_it_gives_up_rather_than_holding_a_worker_forever(self):
        patch, models = self._client([_busy()] * 10)
        with patch, self.assertRaises(errors.ServerError):
            gemini._call(["prompt"])
        self.assertEqual(models.generate_content.call_count, len(gemini.BACKOFF))

    def test_it_does_not_sleep_after_the_final_attempt(self):
        """Nothing is left to wait for, and this runs inside a worker holding one of four slots."""
        patch, _ = self._client([_busy()] * 10)
        with patch, self.assertRaises(errors.ServerError):
            gemini._call(["prompt"])
        self.assertEqual(self.sleep.call_count, len(gemini.BACKOFF) - 1)

    def test_a_refusal_is_not_retried(self):
        """A refusal repeats for the same prompt forever, so retrying it buys the same answer
        twice — the same distinction `NoImage.refused` draws one level up."""
        patch, models = self._client(errors.ClientError("400 INVALID_ARGUMENT", None))
        with patch, self.assertRaises(errors.ClientError):
            gemini._call(["prompt"])
        self.assertEqual(models.generate_content.call_count, 1)

    def test_a_first_try_success_costs_no_extra_call(self):
        patch, models = self._client(["straight-through"])
        with patch:
            self.assertEqual(gemini._call(["prompt"]), "straight-through")
        self.assertEqual(models.generate_content.call_count, 1)
        self.sleep.assert_not_called()
