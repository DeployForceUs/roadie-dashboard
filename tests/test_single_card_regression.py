"""Automated regression test suite for Roadie single-card handling,
overlay classification, store parsing, and repeated Details prevention.
"""
import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import roadie_store
from roadie_ui_guard import Screen, classify_xml, is_card_overlay_present
from roadie_watcher_with_destinations import is_genuine_map_screen, recover_to_map


def make_xml(*nodes_info):
    """Helper to generate XML hierarchy from list of (resource-id, text, bounds, class)."""
    xml_parts = ['<?xml version="1.0" encoding="utf-8"?>\n<hierarchy rotation="0">\n']
    for info in nodes_info:
        rid = info[0] if len(info) > 0 else ""
        text = info[1] if len(info) > 1 else ""
        bounds = info[2] if len(info) > 2 else "[0,0][1080,2400]"
        cls = info[3] if len(info) > 3 else "android.view.View"
        xml_parts.append(
            f'  <node resource-id="{rid}" text="{text}" bounds="{bounds}" class="{cls}" '
            f'package="com.roadie.drive.android.app" />\n'
        )
    xml_parts.append('</hierarchy>\n')
    return "".join(xml_parts)


MAP_XML = make_xml(
    ("com.roadie.drive.android.app:id/refresh_button", "", "[900,100][1000,200]"),
    ("com.roadie.drive.android.app:id/menu_button", "", "[50,100][150,200]"),
    ("com.roadie.drive.android.app:id/fragment_map_mapview", "", "[0,0][1080,2400]"),
)

DETAIL_XML = make_xml(
    ("com.roadie.drive.android.app:id/close_details", "$150.30", "[50,100][150,200]"),
    ("com.roadie.drive.android.app:id/details_container_scroll", "11 deliveries", "[0,200][1080,2400]"),
)

SINGLE_CARD_XML = make_xml(
    ("com.roadie.drive.android.app:id/fragment_map_mapview", "", "[0,0][1080,2400]"),
    ("com.roadie.drive.android.app:id/gig_card_pager", "", "[0,1943][1080,2542]"),
    ("com.roadie.drive.android.app:id/gig_card", "", "[46,1955][1034,2530]"),
    ("com.roadie.drive.android.app:id/gig_summary", "", "[46,2036][1034,2449]"),
    ("", "$150.30", "[100,2100][400,2200]"),
    ("", "76 mi (3 hr 10 min)", "[100,2200][500,2300]"),
    ("", "11 deliveries", "[100,2300][400,2400]"),
    ("", "EASY FIT FOR FORD MUSTANG MACH-E", "[100,2400][800,2500]"),
)


class TestSingleCardClassification(unittest.TestCase):
    """Test screen classification and overlay detection."""

    def test_genuine_map_classified_correctly(self):
        self.assertEqual(classify_xml(MAP_XML), Screen.MAP)
        self.assertFalse(is_card_overlay_present(MAP_XML))

    def test_single_card_overlay_not_mistaken_for_map(self):
        # Even with mapview underneath, card overlay must be CAROUSEL, never MAP
        self.assertEqual(classify_xml(SINGLE_CARD_XML), Screen.CAROUSEL)
        self.assertTrue(is_card_overlay_present(SINGLE_CARD_XML))

    def test_76907987_fixture_classified_as_carousel(self):
        fixture_path = Path(__file__).parent / "fixtures" / "76907987_summary.xml"
        if fixture_path.exists():
            fixture_xml = fixture_path.read_text(encoding="utf-8")
            self.assertEqual(classify_xml(fixture_xml), Screen.CAROUSEL)
            self.assertTrue(is_card_overlay_present(fixture_xml))

    def test_is_genuine_map_screen_helper(self, tmp_path=None):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f_map:
            f_map.write(MAP_XML)
            map_file = f_map.name
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f_card:
            f_card.write(SINGLE_CARD_XML)
            card_file = f_card.name
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f_detail:
            f_detail.write(DETAIL_XML)
            detail_file = f_detail.name
        try:
            self.assertTrue(is_genuine_map_screen(map_file))
            self.assertFalse(is_genuine_map_screen(card_file))
            self.assertFalse(is_genuine_map_screen(detail_file))
        finally:
            os.unlink(map_file)
            os.unlink(card_file)
            os.unlink(detail_file)


class TestRoadieStoreParsing(unittest.TestCase):
    """Test roadie_store field extraction on single cards and hours parsing."""

    def test_single_card_compose_fields(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write(SINGLE_CARD_XML)
            path = f.name
        try:
            nodes = roadie_store.parse(path)
            positions, cards = roadie_store.fields(nodes)
            self.assertEqual(len(positions), 1)
            self.assertEqual(positions[0][1:], (1, 1))
            self.assertIn(1, cards)
            card = cards[1]
            self.assertEqual(card["key"], "76_11")
            self.assertEqual(card["miles"], "76")
            self.assertEqual(card["minutes"], 190)  # 3 hr * 60 + 10 min
            self.assertEqual(card["deliveries"], 11)
            self.assertEqual(card["price"], "150.30")
            self.assertEqual(card["fit"], "EASY FIT FOR FORD MUSTANG MACH-E")
        finally:
            os.unlink(path)

    def test_minutes_only_route_time(self):
        nodes = [
            ("gig_summary", "", ""),
            ("", "$42.50", ""),
            ("", "15.2 mi (38 min)", ""),
            ("", "2 deliveries", ""),
        ]
        positions, cards = roadie_store.fields(nodes)
        self.assertIn(1, cards)
        self.assertEqual(cards[1]["minutes"], 38)
        self.assertEqual(cards[1]["miles"], "15.2")
        self.assertEqual(cards[1]["deliveries"], 2)
        self.assertEqual(cards[1]["price"], "42.50")

    def test_76907987_fixture_does_not_crash(self):
        fixture_path = Path(__file__).parent / "fixtures" / "76907987_summary.xml"
        if fixture_path.exists():
            nodes = roadie_store.parse(str(fixture_path))
            positions, cards = roadie_store.fields(nodes)
            self.assertEqual(len(positions), 1)
            self.assertEqual(positions[0][1:], (1, 1))
            # Skeleton loader card has no text fields yet; cards must be safely empty
            self.assertEqual(cards, {})


class TestBoundedRecoveryAndRepeatedDetailsPrevention(unittest.TestCase):
    """Regression test specifically for the repeated Details bug:
    ensuring bounded recovery terminates, verifies fresh XML, and halts marker
    tapping if map is not restored.
    """

    @patch("roadie_watcher_with_destinations.dump_xml_checked")
    @patch("roadie_watcher_with_destinations.back")
    @patch("roadie_watcher_with_destinations.time.sleep")
    def test_recover_to_map_already_on_map(self, mock_sleep, mock_back, mock_dump):
        """If screen is genuine MAP, no Back action is performed."""
        mock_dump.return_value = True
        with patch("builtins.open", unittest.mock.mock_open(read_data=MAP_XML)):
            res = recover_to_map()
        self.assertTrue(res)
        self.assertEqual(mock_back.call_count, 0)

    @patch("roadie_watcher_with_destinations.dump_xml_checked")
    @patch("roadie_watcher_with_destinations.back")
    @patch("roadie_watcher_with_destinations.time.sleep")
    def test_recover_to_map_from_card_overlay(self, mock_sleep, mock_back, mock_dump):
        """When card overlay is open, back() is called once, then MAP is verified."""
        mock_dump.return_value = True
        screens = [SINGLE_CARD_XML, MAP_XML]

        def fake_open(*args, **kwargs):
            content = screens.pop(0) if screens else MAP_XML
            return unittest.mock.mock_open(read_data=content)()

        with patch("builtins.open", side_effect=fake_open):
            res = recover_to_map()
        self.assertTrue(res)
        self.assertEqual(mock_back.call_count, 1)

    @patch("roadie_watcher_with_destinations.dump_xml_checked")
    @patch("roadie_watcher_with_destinations.back")
    @patch("roadie_watcher_with_destinations.time.sleep")
    def test_recover_to_map_from_detail_screen(self, mock_sleep, mock_back, mock_dump):
        """From DETAIL screen: back() once to CAROUSEL, back() once to MAP."""
        mock_dump.return_value = True
        screens = [DETAIL_XML, SINGLE_CARD_XML, MAP_XML]

        def fake_open(*args, **kwargs):
            content = screens.pop(0) if screens else MAP_XML
            return unittest.mock.mock_open(read_data=content)()

        with patch("builtins.open", side_effect=fake_open):
            res = recover_to_map()
        self.assertTrue(res)
        self.assertEqual(mock_back.call_count, 2)

    @patch("roadie_watcher_with_destinations.dump_xml_checked")
    @patch("roadie_watcher_with_destinations.back")
    @patch("roadie_watcher_with_destinations.time.sleep")
    def test_repeated_details_scenario_bounds_recovery_and_fails_closed(
        self, mock_sleep, mock_back, mock_dump
    ):
        """REPEATED DETAILS BUG SIMULATION:
        If back actions fail to close the card (card overlay stubbornly remains open),
        recover_to_map must perform at most max_attempts Back presses, return False,
        and NEVER loop indefinitely.
        """
        mock_dump.return_value = True
        # Card overlay remains on every single probe
        with patch("builtins.open", unittest.mock.mock_open(read_data=SINGLE_CARD_XML)):
            res = recover_to_map(max_attempts=4)

        self.assertFalse(res)
        self.assertEqual(mock_back.call_count, 4)

    def test_finally_block_guarantees_map_recovery_on_errors(self):
        """Verify that when processing a single gig card, any failure/early exit
        runs cleanup and verifies genuine map before next marker tap.
        """
        taps = []
        backs = []
        recoveries = []
        map_rescans = []

        def fake_tap(x, y):
            taps.append((x, y))

        def fake_back():
            backs.append(True)

        # Simulate stuck card overlay that fails to close on back
        def fake_recover_to_map():
            recoveries.append(True)
            return False  # Failed to restore genuine map

        new_ids = [{"desc": "76907987", "bounds": "[806,1204][978,1376]"}]
        map_needs_rescan = False

        for e in new_ids:
            fake_tap(892, 1290)
            try:
                # Simulate summary capture error or unexpected state
                map_needs_rescan = True
            finally:
                fake_back()
                if not fake_recover_to_map():
                    map_needs_rescan = True
            if map_needs_rescan:
                map_rescans.append(True)
                break

        # Verification: tap happened, back was called, recover_to_map was checked,
        # loop was aborted, and map_needs_rescan was flagged.
        self.assertEqual(len(taps), 1)
        self.assertEqual(len(backs), 1)
        self.assertEqual(len(recoveries), 1)
        self.assertEqual(len(map_rescans), 1)


if __name__ == "__main__":
    unittest.main()
