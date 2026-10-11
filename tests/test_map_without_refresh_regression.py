"""Regression tests for Roadie map without refresh_button (2026-10-11 incident).

These tests deliberately fail against the current classifier until the watcher
can safely distinguish MAP from refresh availability. Do not deploy a
classifier-only fix: main() currently taps fixed refresh coordinates unconditionally.
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
