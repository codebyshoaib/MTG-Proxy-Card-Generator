"""The structure metrics, and the calibration they were fitted to.

Two kinds of test here, deliberately separated.

The synthetic ones are the real regression net: they build a card out of plate rims and a card
out of organic shapes and assert the metric can tell them apart. They run everywhere, including
a clean clone, because they depend on nothing outside this file.

The calibration ones read `Project Material/`, which lives outside the repo and is not committed
(CLAUDE.md: the client material is documents, not code). They SKIP when it is absent rather than
fail, because a clean checkout genuinely does not have it — but when it is there they are what
stops the thresholds drifting away from the corpus they were fitted to.
"""

from pathlib import Path

from django.test import SimpleTestCase
from PIL import Image, ImageDraw, ImageFilter

from generation import score

MATERIAL = Path(__file__).resolve().parents[4] / "Project Material"
CLIENT = MATERIAL / "CLIENT-FAVORITES-2026-08-19"
COMPOSITED = MATERIAL / "CLIENT-PACK-PIP-2026-08-19"

# The client's flat-graphic cards use boxed captions by design and are graded under `panel`.
# Everything else is graded under the default gates. Filed here rather than in `score` because
# it is a fact about this evidence folder, not about the product.
PANEL = {"Counterspell.png", "Memory_Jar.png", "Arcane_Signet.png", "Howling_Mine.png",
         "1-A.png", "1-B.png", "5-A.png", "5-B.png"}


SURFACES = ((0.04, 0.11), (0.55, 0.61), (0.63, 0.88))
"""Where a card's three text surfaces sit, as shares of the height. Same for both fixtures."""


def _art(size=None):
    """Painted ground: cloudy, textured, and free of full-width horizontal edges.

    Gaussian noise under a small blur, not row-wise colour ramps. The first version of this
    fixture drew one `line` per row, which put a hard edge across the FULL width of every row and
    scored 98 ruled rows on a card with no plates on it at all — the fixture was measuring
    itself. This one scores 0, which is what a painted card should score.
    """
    noise = Image.effect_noise(size or score.CANVAS, 64)
    return noise.filter(ImageFilter.GaussianBlur(2)).convert("RGB")


def _plated(surfaces=SURFACES):
    """A card built the way ours are: full-width rectangles stacked on the art."""
    card = _art()
    draw = ImageDraw.Draw(card)
    width, height = score.CANVAS
    for top, bottom in surfaces:
        draw.rectangle(
            (int(width * 0.07), int(height * top), int(width * 0.93), int(height * bottom)),
            fill=(28, 26, 24), outline=(210, 200, 170), width=6,
        )
    return card


def _organic():
    """A card built the way his are: the same surfaces, curved and narrower than the card."""
    card = _art()
    draw = ImageDraw.Draw(card)
    width, height = score.CANVAS
    for top, bottom in SURFACES:
        draw.ellipse(
            (int(width * 0.18), int(height * top), int(width * 0.82), int(height * bottom)),
            fill=(28, 26, 24), outline=(210, 200, 170), width=6,
        )
    return card


class Synthetic(SimpleTestCase):
    """What the metric is for: telling chrome from drawn objects."""

    def test_painted_art_alone_is_not_ruled(self):
        """The fixture must not measure itself — see `_art`. Guards the whole file."""
        self.assertEqual(0, score.measure(_art())["ruled_rows"])

    def test_plates_are_ruled_and_organic_surfaces_are_not(self):
        plated, organic = score.measure(_plated()), score.measure(_organic())
        self.assertGreater(plated["ruled_rows"], organic["ruled_rows"])
        self.assertGreater(plated["widest_edge"], organic["widest_edge"])
        # The point of the gate, not just of the number.
        self.assertTrue(any(p.code == "ruled" for p in score.grade(plated)))
        self.assertEqual([], [p for p in score.grade(organic) if p.code == "ruled"])

    def test_a_full_width_rim_is_reported_on_its_own(self):
        """`widest_edge` and `ruled_rows` answer different questions and both are needed.

        One plate spanning the whole card is only a couple of ruled rows and still reads as
        chrome, which is what `wide_rim` catches and `ruled` misses.
        """
        card = _art()
        draw = ImageDraw.Draw(card)
        width, height = score.CANVAS
        draw.rectangle((0, int(height * 0.5), width, int(height * 0.53)), fill=(20, 20, 20))
        metrics = score.measure(card)
        self.assertLessEqual(metrics["ruled_rows"], score.gates()["ruled_rows"])
        self.assertTrue(any(p.code == "wide_rim" for p in score.grade(metrics)))

    def test_panel_archetype_is_allowed_its_boxes(self):
        """A flat-graphic card's boxed captions are correct in that idiom, so they must not fail.

        Without the exemption the gate fails a fifth of the client's own favorites — his
        Counterspell, Memory Jar and the token murals all carry straight-rimmed caption boxes,
        scoring 6, 3 and up to 11 ruled rows against a corpus mean of 2.3.

        Two surfaces rather than three, so the card lands between the two gates instead of on
        the `panel` boundary — a test sitting exactly on a threshold passes or fails on rounding.
        """
        metrics = score.measure(_plated(SURFACES[:2]))
        self.assertGreater(metrics["ruled_rows"], score.gates()["ruled_rows"])
        self.assertLess(metrics["ruled_rows"], score.gates("panel")["ruled_rows"])
        self.assertTrue(any(p.code == "ruled" for p in score.grade(metrics)))
        self.assertEqual([], [p for p in score.grade(metrics, "panel") if p.code == "ruled"])

    def test_a_flat_surround_reads_as_low_band_structure(self):
        """`band_structure` separates a flat margin from a painted one — Phase 4 depends on it.

        Reported, never gated: 7 of the client's own 19 sit below 1.0, because his Avacyn, both
        Command Towers and four others place an illustrated frame inside a flat dark surround.
        """
        width, height = score.CANVAS
        matted = Image.new("RGB", score.CANVAS, (0, 0, 0))
        matted.paste(_art((int(width * 0.8), int(height * 0.8))), (int(width * 0.1), int(height * 0.1)))
        self.assertLess(score.measure(matted)["band_structure"], 1.0)
        self.assertGreater(score.measure(_art())["band_structure"], 1.0)


class Calibration(SimpleTestCase):
    """The thresholds against the corpus they were fitted to, when that corpus is present."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not CLIENT.is_dir():
            raise cls.skipException(f"{CLIENT} is not checked out — client material is not code")

    def _measured(self, root):
        return [
            (path.name, score.measure(path))
            for path in sorted(root.rglob("*.png"))
            if not path.stem.endswith("-blank") and path.stem != "sheet"
        ]

    def test_the_client_corpus_passes_its_own_gates(self):
        """MEASURED 2026-08-20: 19 cards, at most one outlier tolerated.

        Not 19 of 19. His Giada scores 8 ruled rows under the `portal` archetype — it is the one
        card in the folder that genuinely does use two stacked full-width bars, and it is also
        the card that looks closest to our own output. Fitting the gate around it would open it
        wide enough to pass the batch it exists to fail.
        """
        measured = self._measured(CLIENT)
        self.assertEqual(19, len(measured), "the folder changed — recalibrate before trusting it")
        failed = [
            name for name, metrics in measured
            if score.grade(metrics, "panel" if name in PANEL else None)
        ]
        self.assertLessEqual(len(failed), 1, f"gates drifted off the client corpus: {failed}")

    def test_the_metric_separates_our_composited_output_from_his(self):
        """The property that makes it a ruler: his corpus and ours must not overlap on it.

        MEASURED 2026-08-20 — his 2.32 ruled rows per card against our composited pack's 12.80.
        If a change ever brings these within 2x of each other this assertion should be read as
        good news and rewritten, not deleted.
        """
        if not COMPOSITED.is_dir():
            self.skipTest(f"{COMPOSITED} is not checked out")
        his = [m["ruled_rows"] for _n, m in self._measured(CLIENT)]
        ours = [m["ruled_rows"] for _n, m in self._measured(COMPOSITED)]
        his_mean, our_mean = sum(his) / len(his), sum(ours) / len(ours)
        self.assertGreater(our_mean, his_mean * 2)
