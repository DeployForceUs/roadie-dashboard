#!/usr/bin/env python3
"""Automated validation tests for roadie-dashboard cargo fields integration."""

import unittest
import json
import sqlite3
import tempfile
import os
from pathlib import Path

DASHBOARD_DIR = Path("/Users/dmitriikarpov/Projects/roadie-dashboard")

class TestDashboardCargoIntegration(unittest.TestCase):

    def test_publish_payload_structure(self):
        import sys
        sys.path.insert(0, str(DASHBOARD_DIR))
        import publish
        
        # Test with a mock database containing cargo columns
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tf:
            temp_db = Path(tf.name)
        try:
            con = sqlite3.connect(temp_db)
            con.executescript("""
            CREATE TABLE gigs (
                gig_key TEXT PRIMARY KEY,
                miles TEXT NOT NULL,
                deliveries INTEGER NOT NULL,
                destination TEXT,
                origin TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                last_price TEXT,
                last_minutes INTEGER,
                fit TEXT,
                total_weight_lbs REAL,
                max_weight_lbs REAL,
                max_dimension_in REAL,
                max_dimension_raw TEXT,
                total_items INTEGER
            );
            CREATE TABLE changes (
                id INTEGER PRIMARY KEY,
                seen_at TEXT,
                gig_key TEXT,
                event TEXT,
                old_price TEXT,
                new_price TEXT
            );
            CREATE TABLE map_scans (
                scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                observed_at TEXT,
                direct_ids_json TEXT,
                cluster_count INTEGER
            );
            CREATE TABLE direct_gig_details (
                gig_id TEXT PRIMARY KEY,
                observed_at TEXT,
                details_json TEXT
            );
            """)
            con.execute("""
            INSERT INTO gigs VALUES (
                '117_13', '117', 13, 'Palm Beach Gardens, FL', 'Miami, FL',
                '2026-10-10T12:00:00', '2026-10-10T15:30:00', '168.35', 203,
                'TIGHT FIT FOR FORD MUSTANG MACH-E', 111.0, 25.0, 34.0, '34" L', 13
            )""")
            direct_json = json.dumps({
                "Price": "$52.00", "Distance": "10 mi", "Time": "30 min",
                "To": "Fort Lauderdale, FL",
                "Total Weight": "52 lbs", "Heaviest Item": "52 lbs",
                "Max Dimension": "39\" W", "Total Items": "1"
            })
            con.execute("INSERT INTO map_scans (observed_at, direct_ids_json, cluster_count) VALUES ('2026-10-10T15:35:00', '[\"50536070\"]', 0)")
            con.execute("INSERT INTO direct_gig_details (gig_id, observed_at, details_json) VALUES ('50536070', '2026-10-10T15:35:00', ?)", (direct_json,))
            con.commit()
            con.close()

            orig_db = publish.DB
            publish.DB = temp_db
            try:
                payload = publish.make_payload()
            finally:
                publish.DB = orig_db

            # Verify history
            self.assertEqual(len(payload["history"]), 1)
            h = payload["history"][0]
            self.assertEqual(h["key"], "117_13")
            self.assertEqual(h["total_weight"], 111.0)
            self.assertEqual(h["heaviest_item"], 25.0)
            self.assertEqual(h["max_dimension"], '34" L')
            self.assertEqual(h["total_items"], 13)

            # Verify current
            self.assertEqual(len(payload["current"]), 1)
            c = payload["current"][0]
            self.assertEqual(c["key"], "50536070")
            self.assertEqual(c["total_weight"], 52.0)
            self.assertEqual(c["heaviest_item"], 52.0)
            self.assertEqual(c["max_dimension"], '39" W')
            self.assertEqual(c["total_items"], 1)
        finally:
            if temp_db.exists():
                os.unlink(temp_db)

    def test_data_json_syntax_and_fields(self):
        data_file = DASHBOARD_DIR / "data.json"
        self.assertTrue(data_file.exists())
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("generated_at", data)
        self.assertIn("history", data)
        self.assertIn("current", data)
        for row in data["history"][:5]:
            self.assertIn("total_weight", row)
            self.assertIn("heaviest_item", row)
            self.assertIn("max_dimension", row)
            self.assertIn("total_items", row)

    def test_index_html_has_cargo_display(self):
        html_file = DASHBOARD_DIR / "index.html"
        self.assertTrue(html_file.exists())
        content = html_file.read_text(encoding="utf-8")
        self.assertIn(".cargo", content)
        self.assertIn("Total Weight", content)
        self.assertIn("Heaviest Item", content)
        self.assertIn("Max Dim", content)
        self.assertIn("Total Items", content)

if __name__ == "__main__":
    unittest.main()
