"""Panel geometry that needs no vision call: the P/T fallback (bd mtg-wfp)."""

from django.test import SimpleTestCase

from generation import panels

# Real detections, taken off five stored jobs across three cards on 2026-08-15. Each is
# (lowest rules strip, the shield the detector actually found on that card).
#
# THESE ARE NOT WHAT THE FALLBACK IS FOR, and fitting it to them is the bug this file used to
# enshrine. `pipeline` calls `infer_pt` only when `detected["pt"]` is ABSENT, so every card here is
# one it never runs on. Kept because the contrast with UNDETECTED below is the finding.
MEASURED = [
    ((0.102, 0.678, 0.893, 0.903), (0.794, 0.836, 0.946, 0.962)),
    ((0.106, 0.664, 0.888, 0.905), (0.784, 0.822, 0.930, 0.951)),
    ((0.093, 0.704, 0.863, 0.873), (0.736, 0.790, 0.891, 0.927)),
    ((0.108, 0.682, 0.887, 0.902), (0.769, 0.842, 0.912, 0.946)),
    ((0.101, 0.691, 0.897, 0.913), (0.765, 0.821, 0.921, 0.948)),
]

# The population the fallback DOES serve: five stored cards whose `pt` came back None, with the
# surface the model actually painted read off a labelled 0.02 grid by eye, +-0.005
# (spikes/measure_pt_shield.py, which re-draws the overlays these came from).
#
# The fourth is a horizontal plaque rather than a shield — the model answered the brief's "small
# shield-shaped boss" with different furniture — which is one reason nothing was reported in that
# corner at all. It stays in the sample because it is a card a customer would have been sent.
UNDETECTED = [
    ((0.101, 0.712, 0.904, 0.906), (0.838, 0.855, 0.905, 0.945)),
    ((0.061, 0.774, 0.928, 0.943), (0.845, 0.868, 0.925, 0.960)),
    ((0.100, 0.622, 0.900, 0.898), (0.795, 0.820, 0.905, 0.945)),
    ((0.077, 0.788, 0.919, 0.929), (0.775, 0.888, 0.905, 0.945)),
    ((0.136, 0.684, 0.862, 0.906), (0.785, 0.828, 0.895, 0.945)),
]


def _spill(guess, real):
    """How far the guess reaches outside the surface actually painted, as a fraction of the card.

    The number that matters, because `compositor._display` sets the P/T at half the box height and
    centres it: a box inside the shield prints glyphs on the shield, a box outside it prints glyphs
    hanging off the edge. Negative means the guess sits entirely within the painted surface.
    """
    return max(real[0] - guess[0], real[1] - guess[1], guess[2] - real[2], guess[3] - real[3])


class InferPtTests(SimpleTestCase):
    """Detection of this one surface is unreliable in a way wording does not fix.

    MEASURED 2026-08-15 by running `detect` repeatedly over the SAME stored blanks, so the image is
    fixed and every bit of variance is the detector's: it found the shield on 7 of 20 runs on cards
    where the shield is plainly painted. Restating the bullet at length made it WORSE, 4 of 20. And
    it is not being misfiled — across 7 consecutive misses, nothing was reported anywhere in that
    corner. So the fallback is geometric.
    """

    def test_the_guess_lands_on_the_surface_the_model_actually_painted(self):
        """The whole basis of the fallback, checked against the cards it really runs on.

        Its centre has to fall on the painted surface, because the P/T is centred in the box — a
        centre on the shield is a P/T on the shield.
        """
        for strip, real in UNDETECTED:
            with self.subTest(strip=strip):
                guess = panels.infer_pt({"rules": [strip]})
                cx, cy = (guess[0] + guess[2]) / 2, (guess[1] + guess[3]) / 2
                self.assertTrue(real[0] <= cx <= real[2] and real[1] <= cy <= real[3])

    def test_the_guess_does_not_hang_far_off_the_painted_surface(self):
        """What was actually wrong, and it was never the anchor.

        `PT_SIZE` was fitted on MEASURED — the detections — and applied only to UNDETECTED, and the
        two populations do not overlap in width, so it was the median of the large tail used on the
        small tail. The centre was always right; the box was half again too big, so the P/T came out
        oversized and overhung the shield on 5 of 5. Worst spill was +0.056 of the card and is now
        +0.035, so this guards the fit rather than asserting containment it does not achieve.
        """
        for strip, real in UNDETECTED:
            with self.subTest(strip=strip):
                self.assertLess(_spill(panels.infer_pt({"rules": [strip]}), real), 0.04)

    def test_detected_shields_are_bigger_than_the_ones_detection_misses(self):
        """The bias itself, so a future re-fit cannot quietly go back to the detections.

        If this ever fails because the two populations have converged, `PT_SIZE` is worth
        re-measuring over both together — until then, only UNDETECTED is evidence about it.
        """
        detected = min(shield[2] - shield[0] for _, shield in MEASURED)
        missed = max(real[2] - real[0] for _, real in UNDETECTED)
        self.assertGreater(detected, missed)

    def test_it_anchors_to_the_LOWEST_strip_when_there_are_several(self):
        """One strip per ability is the normal layout, and the shield hangs off the bottom one."""
        strips = [(0.1, 0.60, 0.9, 0.70), (0.1, 0.72, 0.9, 0.82), (0.1, 0.84, 0.9, 0.91)]
        low = panels.infer_pt({"rules": strips})
        high = panels.infer_pt({"rules": [strips[-1]]})
        self.assertEqual(low, high)

    def test_with_no_strip_to_anchor_to_it_declines_to_guess(self):
        """Leaving P/T unprinted is visible and honest; printing it somewhere invented is not."""
        self.assertIsNone(panels.infer_pt({}))
        self.assertIsNone(panels.infer_pt({"title": (0.1, 0.1, 0.9, 0.2)}))

    def test_the_box_never_leaves_the_card_or_enters_the_trim(self):
        """A strip running to the very corner would otherwise push the shield off the edge, and
        the outer margin is cut off when the card is printed (bd mtg-cjx)."""
        box = panels.infer_pt({"rules": [(0.1, 0.90, 1.0, 1.0)]})
        for value in box:
            self.assertGreaterEqual(value, 0.04)
            self.assertLessEqual(value, 0.96)
