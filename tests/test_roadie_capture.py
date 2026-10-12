import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from roadie_capture import CaptureError, capture_xml
from roadie_ui_guard import Screen

XML = b'<hierarchy><node resource-id="pkg:id/refresh_button"/><node resource-id="pkg:id/menu_button"/></hierarchy>'

class CaptureTests(unittest.TestCase):
    def test_atomic_success(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d)/'start.xml'
            def adb(args):
                if args[0] == 'pull':
                    Path(args[2]).write_bytes(XML)
                return SimpleNamespace(returncode=0)
            self.assertEqual(capture_xml(dest, adb, min_bytes=1), Screen.MAP)
            self.assertEqual(dest.read_bytes(), XML)

    def test_failed_pull_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d)/'start.xml'
            dest.write_text('previous')
            def adb(args):
                return SimpleNamespace(returncode=1 if args[0] == 'pull' else 0)
            with self.assertRaises(CaptureError):
                capture_xml(dest, adb, min_bytes=1)
            self.assertEqual(dest.read_text(), 'previous')

    def test_failed_dump_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d)/'start.xml'
            dest.write_text('previous')
            def adb(args):
                return SimpleNamespace(returncode=1 if args[0] == 'shell' and args[1] == 'uiautomator' else 0)
            with self.assertRaises(CaptureError):
                capture_xml(dest, adb, min_bytes=1)
            self.assertEqual(dest.read_text(), 'previous')

    def test_unknown_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d)/'start.xml'
            def adb(args):
                if args[0] == 'pull':
                    Path(args[2]).write_bytes(b'<hierarchy><node/></hierarchy>')
                return SimpleNamespace(returncode=0)
            with self.assertRaises(CaptureError):
                capture_xml(dest, adb, min_bytes=1)
            self.assertFalse(dest.exists())

if __name__ == '__main__':
    unittest.main()
