"""Panel geometry that needs no vision call."""

from django.test import SimpleTestCase

from generation import panels

# Shields measured off stored cards on 2026-08-13/15, kept as evidence for the CORNER CROP.
# They were originally fitted to `panels.infer_pt`, which was deleted on 2026-08-16 once
# detection reached 24/24 over the same blanks (bd mtg-1uv). The fallback is gone; where the
# shields actually sit is still the thing `PT_CROP` has to cover, so the numbers stay.
#
# MEASURED is what the detector found; UNDETECTED is what it missed, read off a labelled 0.02
# grid by eye, +-0.005. The two populations do not overlap in width — the detector found big
# shields and missed small ones — which is why the crop has to reach the small tail too.
MEASURED = [
    ((0.102, 0.678, 0.893, 0.903), (0.794, 0.836, 0.946, 0.962)),
    ((0.106, 0.664, 0.888, 0.905), (0.784, 0.822, 0.930, 0.951)),
    ((0.093, 0.704, 0.863, 0.873), (0.736, 0.790, 0.891, 0.927)),
    ((0.108, 0.682, 0.887, 0.902), (0.769, 0.842, 0.912, 0.946)),
    ((0.101, 0.691, 0.897, 0.913), (0.765, 0.821, 0.921, 0.948)),
]


UNDETECTED = [
    ((0.101, 0.712, 0.904, 0.906), (0.838, 0.855, 0.905, 0.945)),
    ((0.061, 0.774, 0.928, 0.943), (0.845, 0.868, 0.925, 0.960)),
    ((0.100, 0.622, 0.900, 0.898), (0.795, 0.820, 0.905, 0.945)),
    ((0.077, 0.788, 0.919, 0.929), (0.775, 0.888, 0.905, 0.945)),
    ((0.136, 0.684, 0.862, 0.906), (0.785, 0.828, 0.895, 0.945)),
]



class CornerDetailTests(SimpleTestCase):
    """The shield is found by looking closer, in the SAME call (bd mtg-1uv).

    `detect` reports it on 7 of 20 runs over the same stored blanks and three rounds of rewording
    never moved that, because it is a resolution problem: the smallest shield measured is 0.067 of
    the card wide, ~120px in a 1792x2400 frame the model also has to read four other surfaces out
    of. The corner is attached as a second image part rather than as a third AI call — a card
    already pays for two.
    """

    def _png(self, size=(400, 536)):
        import io

        from PIL import Image

        out = io.BytesIO()
        Image.new("RGB", size, (30, 30, 30)).save(out, format="PNG")
        return out.getvalue()

    def test_the_corner_is_cut_from_the_bottom_right_and_enlarged(self):
        import io

        from PIL import Image

        card = self._png()
        crop = Image.open(io.BytesIO(panels._corner(card)))
        region, scale = panels.PT_CROP, panels.PT_CROP_SCALE
        # Computed the way the crop is taken — from the rounded edges, not from the rounded span.
        self.assertEqual(crop.size, (
            (400 - int(region[0] * 400)) * scale,
            (536 - int(region[1] * 536)) * scale,
        ))
        self.assertGreater(crop.width, 0.4 * 400, "the corner is enlarged, not shrunk")

    def test_the_crop_covers_every_shield_ever_measured(self):
        """A shield outside the crop is one the second image cannot help with."""
        for _strip, shield in MEASURED + UNDETECTED:
            self.assertGreaterEqual(shield[0], panels.PT_CROP[0], "shield starts left of the crop")
            self.assertGreaterEqual(shield[1], panels.PT_CROP[1], "shield starts above the crop")

    def test_a_box_in_the_crop_maps_back_to_the_card(self):
        """The model answers in the crop's coordinates; the arithmetic is ours, so it is testable."""
        whole = panels._from_crop((0.0, 0.0, 1.0, 1.0))
        self.assertEqual(whole, panels.PT_CROP)
        x0, y0, x1, y1 = panels.PT_CROP
        centre = panels._from_crop((0.5, 0.5, 0.5, 0.5))
        self.assertAlmostEqual(centre[0], (x0 + x1) / 2)
        self.assertAlmostEqual(centre[1], (y0 + y1) / 2)

    def test_terror_would_have_been_placed_on_the_shield_not_its_rim(self):
        """The card that exposed this (job 519273ac). The guess put the glyphs at y 0.794-0.840,
        opening on the bright rim; the shield's inner face starts about 0.801. A detail box
        reported against the enlarged corner maps back onto the face instead."""
        # The inner face as it appears in the crop's own coordinates.
        face_in_crop = (0.39, 0.55, 0.83, 0.82)
        mapped = panels._from_crop(face_in_crop)
        self.assertGreater(mapped[1], 0.801, "the box must start below the shield's rim")
        self.assertLess(mapped[3], 0.940, "and finish inside the shield's point")
