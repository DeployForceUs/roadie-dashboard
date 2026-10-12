"""Regression tests for single-card Roadie carousel and ambiguous screens."""
import unittest
from roadie_ui_guard import classify_xml, Screen


def xml(*ids):
    return '<hierarchy>' + ''.join(
        '<node resource-id="com.roadie:id/' + value + '" />' for value in ids
    ) + '</hierarchy>'


class ScreenClassifierTests(unittest.TestCase):
    def test_single_card_carousel_without_position(self):
        self.assertEqual(classify_xml(xml("gig_card_pager")), Screen.CAROUSEL)

    def test_multi_card_carousel(self):
        self.assertEqual(classify_xml(xml("gig_card_pager", "position_in_stack")), Screen.CAROUSEL)

    def test_map(self):
        self.assertEqual(classify_xml(xml("refresh_button", "menu_button")), Screen.MAP)

    def test_detail(self):
        self.assertEqual(classify_xml(xml("close_details", "details_container_scroll")), Screen.DETAIL)

    def test_conflicting_screen_markers_still_fail_closed(self):
        self.assertEqual(classify_xml(xml("gig_card_pager", "refresh_button", "menu_button")), Screen.UNKNOWN)

    def test_position_alone_not_carousel(self):
        self.assertEqual(classify_xml(xml("position_in_stack")), Screen.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
