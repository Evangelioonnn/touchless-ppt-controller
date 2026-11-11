import unittest
from types import SimpleNamespace
from powerpoint_bridge import PowerPointBridge, PowerPointTarget


class Windows:
    def __init__(self):
        self.items = []
        self.keys = []
        self.scans = 0

    def targets(self):
        self.scans += 1
        return self.items.copy()

    def is_window(self, hwnd):
        return any(t.hwnd == hwnd for t in self.items)

    def post_key(self, hwnd, key):
        self.keys.append((hwnd, key))
        return True


class PowerPointTests(unittest.TestCase):
    def test_S01_no_ppt_not_connected(self):
        windows = Windows()
        bridge = PowerPointBridge(windows=windows, clock=lambda: 0)
        self.assertFalse(bridge.status().connected)
        self.assertEqual(bridge.next_slide().state, 'failed')
        self.assertEqual(windows.keys, [])

    def test_S02_explicit_multi_target_and_S07_sent_is_not_success(self):
        windows = Windows()
        windows.items = [PowerPointTarget(str(i), 'PPT%d' % i, i, 123, True) for i in (11, 22)]
        bridge = PowerPointBridge(windows=windows)
        self.assertFalse(bridge.status().connected)
        bridge.select_target('22')
        result = bridge.next_slide()
        self.assertEqual(result.state, 'sent')
        self.assertFalse(result)
        self.assertEqual(windows.keys, [(22, 0x27)])

    def test_S05_does_not_switch_to_another_ppt(self):
        windows = Windows()
        windows.items = [PowerPointTarget('11', 'A', 11, 123, True)]
        bridge = PowerPointBridge(windows=windows)
        windows.items = [PowerPointTarget('22', 'B', 22, 123, True)]
        bridge.refresh()
        self.assertFalse(bridge.status().connected)
        self.assertEqual(bridge.previous_slide().state, 'failed')

    def test_L04_disconnected_scan_throttled(self):
        windows = Windows()
        bridge = PowerPointBridge(windows=windows, clock=lambda: 0)
        for i in range(100):
            bridge.refresh_if_needed(i / 200)
        self.assertEqual(windows.scans, 1)

    def test_main_window_never_binds_to_another_document_show_by_pid_only(self):
        windows = Windows()
        main = PowerPointTarget('11', 'document A', 11, 123, False)
        other = PowerPointTarget('22', 'document B show', 22, 123, True)
        windows.items = [main, other]
        bridge = PowerPointBridge(windows=windows, clock=lambda: 0)
        bridge.select_target('11')
        self.assertEqual(bridge.status().target_id, '11')
        self.assertFalse(bridge.status().connected)
        self.assertEqual(bridge.start_slideshow().state, 'sent')
        self.assertEqual(windows.keys, [(11, 0x74)])
        windows.items.append(PowerPointTarget('33', 'new A show', 33, 123, True))
        bridge.refresh()
        self.assertEqual(bridge.status().target_id, '33')
        self.assertTrue(bridge.status().connected)

    def test_S04_com_animation_not_repeated_and_unknown_no_fallback(self):
        windows = Windows()
        windows.items = [PowerPointTarget('11', 'A', 11, 123, True)]
        calls = []
        def advance():
            calls.append('next')
        view = SimpleNamespace(Slide=SimpleNamespace(SlideIndex=1), Next=advance)
        show = SimpleNamespace(HWND=11, View=view)
        collection = SimpleNamespace(Count=1, Item=lambda index: show)
        app = SimpleNamespace(SlideShowWindows=collection)
        bridge = PowerPointBridge('com', windows=windows, com_factory=lambda: app)
        self.assertEqual(bridge.next_slide().state, 'accepted')
        self.assertEqual(calls, ['next'])
        def fail_after_send():
            calls.append('next')
            raise RuntimeError('disconnected after command')
        view.Next = fail_after_send
        self.assertEqual(bridge.next_slide().state, 'unknown')
        self.assertEqual(calls, ['next', 'next'])
        self.assertEqual(windows.keys, [])


if __name__ == '__main__':
    unittest.main()
