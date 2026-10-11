"""Regression tests for Roadie map without refresh_button (2026-10-11 incident).

The incident map must classify as MAP even without refresh_button.
The watcher must separately guard the refresh action; classification alone
must never authorize a blind coordinate tap.
"""
import unittest
from roadie_ui_guard import Screen, classify_xml

def xml(*nodes):
    return '<hierarchy>' + ''.join(
        f'<node resource-id="{rid}" content-desc="{desc}" />'
        for rid, desc in nodes
    ) + '</hierarchy>'

class MapWithoutRefreshTests(unittest.TestCase):
    def test_map_without_refresh_is_still_map(self):
        payload = xml(
            ("com.roadie.drive.android.app:id/fragment_map_mapview", ""),
            ("", "Google Map"),
            ("", "76510555"),
            ("com.roadie.drive.android.app:id/menu_button", ""),
            ("com.roadie.drive.android.app:id/my_location_button", ""),
        )
        self.assertIs(classify_xml(payload), Screen.MAP)

    def test_card_overlay_takes_precedence_over_map(self):
        payload = xml(
            ("com.roadie.drive.android.app:id/fragment_map_mapview", ""),
            ("", "Google Map"),
            ("com.roadie.drive.android.app:id/gig_card_pager", ""),
            ("com.roadie.drive.android.app:id/gig_summary_card", ""),
        )
        self.assertIs(classify_xml(payload), Screen.CAROUSEL)

    def test_detail_overlay_takes_precedence_over_map(self):
        payload = xml(
            ("com.roadie.drive.android.app:id/fragment_map_mapview", ""),
            ("", "Google Map"),
            ("com.roadie.drive.android.app:id/close_details", ""),
            ("com.roadie.drive.android.app:id/details_container_scroll", ""),
        )
        self.assertIs(classify_xml(payload), Screen.DETAIL)

    def test_menu_only_is_not_map(self):
        payload = xml(("com.roadie.drive.android.app:id/menu_button", ""))
        self.assertIs(classify_xml(payload), Screen.UNKNOWN)

    def test_existing_refresh_map(self):
        payload = xml(
            ("com.roadie.drive.android.app:id/refresh_button", ""),
            ("com.roadie.drive.android.app:id/menu_button", ""),
        )
        self.assertIs(classify_xml(payload), Screen.MAP)

if __name__ == "__main__":
    unittest.main()
