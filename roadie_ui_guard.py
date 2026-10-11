"""Conservative Roadie UI screen classification. No ADB or database side effects."""
from enum import Enum
import xml.etree.ElementTree as ET

class Screen(str, Enum):
    MAP = "map"
    CAROUSEL = "carousel"
    DETAIL = "detail"
    UNKNOWN = "unknown"

def classify_xml(xml_text: str) -> Screen:
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError):
        return Screen.UNKNOWN
    ids = {n.get("resource-id", "").split("/")[-1] for n in root.iter()}
    # A direct map marker opens a single AVAILABLE GIG summary card.
    # It has gig_card_pager but NO position_in_stack. The map remains
    # mounted behind the overlay, so MAP markers can coexist with it.
    if {"close_details", "details_container_scroll"} <= ids:
        return Screen.DETAIL
    if "gig_card_pager" in ids and (
        "position_in_stack" in ids or "gig_summary_card" in ids
    ):
        return Screen.CAROUSEL
    # The Roadie map can remain mounted without a refresh control.
    # Require both the map container and Google Map accessibility node;
    # menu_button alone is not sufficient. Carousel/detail take precedence.
    descriptions = {n.get("content-desc", "") for n in root.iter()}
    if ("fragment_map_mapview" in ids and "Google Map" in descriptions):
        return Screen.MAP
    if {"refresh_button", "menu_button"} <= ids:
        return Screen.MAP
    return Screen.UNKNOWN

def allowed_action(screen: Screen, action: str) -> bool:
    return (screen, action) in {
        (Screen.MAP, "refresh"),
        (Screen.MAP, "open_cluster"),
        (Screen.MAP, "open_single"),
        (Screen.CAROUSEL, "swipe_cards"),
        (Screen.CAROUSEL, "back_to_map"),
        (Screen.CAROUSEL, "open_detail"),
        (Screen.DETAIL, "close_detail"),
    }

def refresh_bounds(xml_text: str):
    """Return a verified refresh control's bounds, or None.

    A MAP classification alone does not prove that refresh is available.
    No guessed coordinates or default centers are permitted.
    """
    if classify_xml(xml_text) is not Screen.MAP:
        return None
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError):
        return None
    matches = [
        n.get("bounds")
        for n in root.iter()
        if n.get("resource-id", "").split("/")[-1] == "refresh_button"
        and n.get("bounds") not in ("", None, "[0,0][0,0]")
    ]
    return matches[0] if len(matches) == 1 else None
