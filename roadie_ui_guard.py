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
    evidence = [
        (Screen.MAP, {"refresh_button", "menu_button"} <= ids),
        (Screen.CAROUSEL, {"gig_card_pager", "position_in_stack"} <= ids),
        (Screen.DETAIL, {"close_details", "details_container_scroll"} <= ids),
    ]
    found = [s for s, present in evidence if present]
    return found[0] if len(found) == 1 else Screen.UNKNOWN

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
