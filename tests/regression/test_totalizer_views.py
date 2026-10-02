"""
Tests de las tres vistas del totalizador (fuente de verdad única).

Ítem 4 auditoría 2026-10-02.
"""
from django.test import TestCase

from api.core.utils.totalizer import resolve_totalizer_views, views_from_profile


class TotalizerViewsTests(TestCase):
    """stored / display / dga parten del mismo stored con transforms documentados."""

    def test_three_views_from_one_source(self):
        # Ejemplo auditoría Iansa P4: stored=687970, d6=10678672
        views = resolve_totalizer_views(
            stored_total=687970,
            addition=0,
            d6=10678672,
        )
        self.assertEqual(views["stored"], 687970)
        self.assertEqual(views["display"], 687970 + 10678672)
        self.assertEqual(views["dga"], 687970)

    def test_dga_subtracts_addition(self):
        views = resolve_totalizer_views(
            stored_total=1100,
            addition=100,
            d6=5000,
        )
        self.assertEqual(views["stored"], 1100)
        self.assertEqual(views["dga"], 1000)  # sin offset de resets
        self.assertEqual(views["display"], 6100)  # + d6

    def test_dga_never_negative(self):
        views = resolve_totalizer_views(stored_total=50, addition=100, d6=0)
        self.assertEqual(views["dga"], 0)

    def test_views_from_profile_dict(self):
        views = views_from_profile(
            "2000",
            {"addition": 200, "d6": 10},
        )
        self.assertEqual(views["stored"], 2000)
        self.assertEqual(views["dga"], 1800)
        self.assertEqual(views["display"], 2010)

    def test_none_and_empty_safe(self):
        views = resolve_totalizer_views(None, None, None)
        self.assertEqual(views["stored"], 0)
        self.assertEqual(views["display"], 0)
        self.assertEqual(views["dga"], 0)
