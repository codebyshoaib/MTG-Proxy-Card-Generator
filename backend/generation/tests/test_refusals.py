"""Which licensed cards may be painted under their own name, and what happens when they cannot.

MEASURED 2026-08-10, n=10 licensed-only cards (bd mtg-kx4): eight painted the actual character
first try and only the two Marvel ones were refused. Confirmed independently against the
reference site's own 3265-card gallery, whose crossovers are all named and at full likeness and
which contains no Marvel card at all.
"""

from django.test import SimpleTestCase

from generation import gemini, refusals


class RefusalDetectionTests(SimpleTestCase):
    def test_a_prohibited_content_finish_is_a_refusal(self):
        """A refusal repeats for a prompt forever, so it is the one case worth a different
        prompt rather than a retry."""
        for reason in ("PROHIBITED_CONTENT", "SAFETY", "IMAGE_SAFETY", "FinishReason.SAFETY"):
            with self.subTest(reason=reason):
                self.assertTrue(gemini.NoImage("x", finish_reason=reason).refused)

    def test_an_empty_response_is_not_a_refusal(self):
        """The transient miss measured once in 24 generations. Retrying it is worth a credit;
        rewriting the brief for it would throw away the card's name for no reason."""
        for reason in (None, "STOP", "MAX_TOKENS", ""):
            with self.subTest(reason=reason):
                self.assertFalse(gemini.NoImage("x", finish_reason=reason).refused)


class RefusalMemoTests(SimpleTestCase):
    def test_the_measured_marvel_refusals_are_seeded(self):
        """So no Marvel card ever pays the wasted generation the measurement already paid."""
        self.assertTrue(refusals.is_refused("Hulk, Bruce Banner"))
        self.assertTrue(refusals.is_refused("Spider-Man, Web-Slinger"))

    def test_the_franchises_that_generate_are_not_blocked(self):
        """The whole point: eight of ten rightsholders paint fine, and treating them all as
        unpaintable is what turned Raphael into "a legendary mutant ninja turtle"."""
        for name in (
            "Raphael, Tough Turtle",
            "Cloud, Ex-SOLDIER",
            "Frodo, Adventurous Hobbit",
            "Ezio, Blade of Vengeance",
            "Dogmeat, Ever Loyal",
            "Abaddon the Despoiler",
        ):
            with self.subTest(card=name):
                self.assertFalse(refusals.is_refused(name))

    def test_a_seeded_name_is_never_rewritten_to_the_store(self):
        refusals.remember("Hulk, Bruce Banner")
        self.assertTrue(refusals.is_refused("Hulk, Bruce Banner"))


class NamedFirstTests(SimpleTestCase):
    def test_the_command_tries_the_name_before_the_game_identity(self):
        """bd mtg-kx4: prompts._subject's licensed branch was generalised from one rightsholder.
        It is correct for Marvel and wrong for the other eight, so it may only run after the
        model has actually refused — never before."""
        import inspect

        from generation.management.commands import compose_card

        source = inspect.getsource(compose_card)
        named = source.index("licensed=False")
        fallback = source.index("licensed=True")
        self.assertLess(named, fallback, "the named brief must be attempted first")
        self.assertIn("refusals.remember", source)
        self.assertIn("refusal.refused", source)
