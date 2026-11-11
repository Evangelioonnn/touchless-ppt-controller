import unittest
from types import SimpleNamespace
from powerpoint_bridge import PowerPointBridge, PowerPointTarget, com_matches_window
from test_powerpoint import Windows


class ComMatchingTests(unittest.TestCase):
    def test_office_without_hwnd_maps_document_name(self):
        target = PowerPointTarget('11', 'PowerPoint 幻灯片放映 - lecture.pptx', 11, 123, True)
        show = SimpleNamespace(Presentation=SimpleNamespace(Name='lecture.pptx'))
        self.assertTrue(com_matches_window(show, target))
        self.assertFalse(com_matches_window(show, PowerPointTarget('22', 'another.pptx', 22,123,True)))

    def test_ambiguous_com_document_names_are_not_executed(self):
        windows = Windows()
        windows.items = [PowerPointTarget('11','PowerPoint Slide Show - lecture.pptx',11,123,True)]
        calls = []
        shows = [SimpleNamespace(Presentation=SimpleNamespace(Name='lecture.pptx'),
                 View=SimpleNamespace(Slide=SimpleNamespace(SlideIndex=1), Next=lambda: calls.append(1))) for _ in range(2)]
        app = SimpleNamespace(SlideShowWindows=SimpleNamespace(Count=2, Item=lambda i: shows[i-1]))
        bridge = PowerPointBridge('com', windows=windows, com_factory=lambda: app)
        self.assertEqual(bridge.next_slide().state, 'failed')
        self.assertEqual(calls, [])

    def test_filename_prefix_is_not_a_match_for_another_document(self):
        target = PowerPointTarget('11', 'PowerPoint Slide Show - lecture12.pptx',11,123,True)
        self.assertFalse(com_matches_window(SimpleNamespace(Name='lecture1.pptx'), target))
        self.assertFalse(com_matches_window(SimpleNamespace(Name='PowerPoint.pptx'), target))

    def test_multiple_powerpoint_processes_refuse_com_routing(self):
        windows = Windows()
        windows.items = [PowerPointTarget('11','a',11,123,True), PowerPointTarget('22','b',22,456,True)]
        bridge = PowerPointBridge('com', windows=windows, com_factory=lambda: self.fail('must not call ambiguous COM app'))
        bridge.select_target('11')
        self.assertEqual(bridge.next_slide().state, 'failed')
