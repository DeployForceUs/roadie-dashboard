"""Fail-closed XML capture for Roadie Watcher. Does not issue input events.

Caller injects an ADB runner returning subprocess.CompletedProcess-like objects.
On any failure the previously published destination remains untouched.
"""
import os
from pathlib import Path
import tempfile
import uuid
import xml.etree.ElementTree as ET
from roadie_ui_guard import classify_xml, Screen

class CaptureError(RuntimeError):
    pass

def capture_xml(destination, run_adb, min_bytes=3600):
    destination = Path(destination)
    remote = '/sdcard/roadie_' + uuid.uuid4().hex + '.xml'
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.roadie_', suffix='.xml', dir=destination.parent)
    os.close(fd)
    try:
        dumped = run_adb(['shell', 'uiautomator', 'dump', remote])
        if dumped.returncode != 0:
            raise CaptureError('ADB UI dump failed')
        pulled = run_adb(['pull', remote, temp])
        if pulled.returncode != 0:
            raise CaptureError('ADB XML pull failed')
        data = Path(temp).read_bytes()
        if len(data) < min_bytes:
            raise CaptureError('ADB XML dump too small')
        try:
            ET.fromstring(data)
        except ET.ParseError as exc:
            raise CaptureError('Invalid ADB XML') from exc
        screen = classify_xml(data.decode('utf-8'))
        if screen is Screen.UNKNOWN:
            raise CaptureError('Unrecognized or conflicting Android screen')
        os.replace(temp, destination)
        return screen
    finally:
        try:
            run_adb(['shell', 'rm', '-f', remote])
        except Exception:
            pass
        if os.path.exists(temp):
            os.unlink(temp)
