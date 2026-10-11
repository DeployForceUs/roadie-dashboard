import unittest
from roadie_ui_guard import Screen, classify_xml, allowed_action

def xml(*ids):
    return '<hierarchy>' + ''.join('<node resource-id="pkg:id/%s"/>' % i for i in ids) + '</hierarchy>'

class ScreenTests(unittest.TestCase):
    def test_map(self):
        self.assertEqual(classify_xml(xml('refresh_button','menu_button')), Screen.MAP)
    def test_carousel(self):
        self.assertEqual(classify_xml(xml('gig_card_pager','position_in_stack')), Screen.CAROUSEL)
    def test_detail(self):
        self.assertEqual(classify_xml(xml('close_details','details_container_scroll')), Screen.DETAIL)
    def test_unknown(self):
        self.assertEqual(classify_xml(xml('unrelated')), Screen.UNKNOWN)
    def test_malformed(self):
        self.assertEqual(classify_xml('<hierarchy>'), Screen.UNKNOWN)
    def test_conflicting(self):
        self.assertEqual(classify_xml(xml('refresh_button','menu_button','close_details','details_container_scroll')), Screen.UNKNOWN)
    def test_detail_cannot_refresh(self):
        self.assertFalse(allowed_action(Screen.DETAIL,'refresh'))
    def test_unknown_cannot_back(self):
        self.assertFalse(allowed_action(Screen.UNKNOWN,'back_to_map'))
    def test_carousel_cannot_refresh(self):
        self.assertFalse(allowed_action(Screen.CAROUSEL,'refresh'))
    def test_map_can_refresh(self):
        self.assertTrue(allowed_action(Screen.MAP,'refresh'))

if __name__ == '__main__':
    unittest.main()
