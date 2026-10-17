"""Regression tests for single-card Roadie carousel and ambiguous screens."""
import unittest
from pathlib import Path
from roadie_ui_guard import classify_xml, Screen, is_card_overlay_present


def xml(*ids):
    return '<hierarchy>' + ''.join(
        '<node resource-id="com.roadie:id/' + value + '" />' for value in ids
    ) + '</hierarchy>'


class ScreenClassifierTests(unittest.TestCase):
    def test_single_card_carousel_without_position(self):
        # Single cards in Compose UI have gig_card_pager with gig_summary, gig_card, or gig_summary_card
        self.assertEqual(classify_xml(xml("gig_card_pager", "gig_summary")), Screen.CAROUSEL)
        self.assertEqual(classify_xml(xml("gig_card_pager", "gig_card")), Screen.CAROUSEL)
        self.assertEqual(classify_xml(xml("gig_card_pager", "gig_summary_card")), Screen.CAROUSEL)

    def test_bare_pager_fails_closed_without_card_markers(self):
        # Bare pager in transition without card elements fails closed to UNKNOWN
        self.assertEqual(classify_xml(xml("gig_card_pager")), Screen.UNKNOWN)

    def test_multi_card_carousel(self):
        self.assertEqual(classify_xml(xml("gig_card_pager", "position_in_stack")), Screen.CAROUSEL)

    def test_map(self):
        self.assertEqual(classify_xml(xml("refresh_button", "menu_button")), Screen.MAP)

    def test_detail(self):
        self.assertEqual(classify_xml(xml("close_details", "details_container_scroll")), Screen.DETAIL)

    def test_conflicting_screen_markers_still_fail_closed(self):
        self.assertEqual(classify_xml(xml("gig_card_pager", "refresh_button", "menu_button")), Screen.UNKNOWN)
        self.assertEqual(classify_xml(xml("close_details", "details_container_scroll", "refresh_button", "menu_button")), Screen.UNKNOWN)

    def test_position_alone_not_carousel(self):
        self.assertEqual(classify_xml(xml("position_in_stack")), Screen.UNKNOWN)

    def test_76907987_fixture_classified_as_carousel(self):
        fixture_path = Path(__file__).parent / "tests" / "fixtures" / "76907987_summary.xml"
        if fixture_path.exists():
            fixture_xml = fixture_path.read_text(encoding="utf-8")
            self.assertEqual(classify_xml(fixture_xml), Screen.CAROUSEL)
            self.assertTrue(is_card_overlay_present(fixture_xml))


if __name__ == "__main__":
    unittest.main()
