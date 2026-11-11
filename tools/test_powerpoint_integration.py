"""Exercise only disposable test presentations; never touch an existing user deck."""
from __future__ import annotations
import json
import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep-open-seconds', type=float, default=0, help='Keep disposable fixtures briefly for UI validation')
    args = parser.parse_args()
    import pythoncom
    import win32com.client
    from powerpoint_bridge import NativeWindows, PowerPointBridge, com_int
    output = ROOT / 'validation/powerpoint'
    output.mkdir(parents=True, exist_ok=True)
    pythoncom.CoInitialize()
    app = None
    documents, shows = [], []
    report = {'tests': {}, 'fixture_only': True}
    try:
        try:
            existing = win32com.client.GetActiveObject('PowerPoint.Application')
        except Exception:
            existing = None
        if existing is not None and int(existing.Presentations.Count):
            report['skipped'] = 'User presentations are already open; leaving them untouched.'
            return
        app = win32com.client.DispatchEx('PowerPoint.Application')
        app.Visible = True
        report['office_version'] = str(app.Version)
        for name in ('A', 'B'):
            doc = app.Presentations.Add(True)
            documents.append(doc)
            for index in range(1, 26):
                slide = doc.Slides.Add(index, 12)
                shape = slide.Shapes.AddTextbox(1, 40, 40, 600, 100)
                shape.TextFrame.TextRange.Text = 'Touchless validation %s / %d' % (name, index)
            if name == 'B':
                doc.Slides.Item(1).TimeLine.MainSequence.AddEffect(doc.Slides.Item(1).Shapes.Item(1), 1)
            path = output / ('fixture-%s-%d.pptx' % (name, time.time_ns()))
            doc.SaveAs(str(path), 24)
            doc.SlideShowSettings.ShowType = 2  # Windowed test, not a full-screen takeover.
            shows.append(doc.SlideShowSettings.Run())
            pythoncom.PumpWaitingMessages()
            time.sleep(.3)
        native = NativeWindows()
        bridge = PowerPointBridge('com', windows=native, com_factory=lambda: app)
        first, second = shows
        targets = native.targets()
        report['show_count'] = int(app.SlideShowWindows.Count)
        report['show_documents'] = [str(show.Presentation.Name) for show in shows]
        report['targets'] = [{'id': item.id, 'title': item.title, 'slideshow': item.slideshow} for item in targets]
        def show_id(show):
            stem = Path(str(show.Presentation.Name)).stem.casefold()
            matches = [item for item in native.targets() if item.slideshow and stem in item.title.casefold()]
            if len(matches) != 1:
                raise RuntimeError('Test slideshow did not map to exactly one native window: ' + stem)
            return matches[0].id
        first_id, second_id = show_id(first), show_id(second)
        bridge.select_target(first_id)
        first.View.GotoSlide(1)
        for _ in range(20):
            bridge.next_slide()
        report['tests']['forward_20'] = int(first.View.Slide.SlideIndex) == 21
        report['tests']['other_document_untouched'] = int(second.View.Slide.SlideIndex) == 1
        for _ in range(20):
            bridge.previous_slide()
        report['tests']['back_20'] = int(first.View.Slide.SlideIndex) == 1
        bridge.select_target(second_id)
        before = (int(second.View.Slide.SlideIndex), int(second.View.GetClickIndex()))
        result = bridge.next_slide()
        after = (int(second.View.Slide.SlideIndex), int(second.View.GetClickIndex()))
        report['animation'] = {'before': before, 'after': after, 'state': result.state}
        report['tests']['com_next_preserves_animation_step'] = after[0] == before[0] and after[1] > before[1]
        back_result = bridge.previous_slide()
        animation_back = (int(second.View.Slide.SlideIndex), int(second.View.GetClickIndex()))
        report['animation']['after_previous'] = animation_back
        report['animation']['previous_state'] = back_result.state
        report['tests']['com_previous_preserves_animation_step'] = animation_back[0] == before[0] and animation_back[1] == before[1]
        first.View.GotoSlide(1)
        bridge.backend = 'keys'
        bridge.select_target(first_id)
        sent = bridge.next_slide()
        until = time.perf_counter() + 1.5
        while time.perf_counter() < until and int(first.View.Slide.SlideIndex) == 1:
            pythoncom.PumpWaitingMessages()
            time.sleep(.03)
        report['targeted_keys'] = {'state': sent.state, 'slide_after': int(first.View.Slide.SlideIndex)}
        report['tests']['targeted_key_reaches_slideshow'] = int(first.View.Slide.SlideIndex) == 2
        first.View.Exit()
        bridge.refresh()
        report['tests']['closed_target_no_reassignment'] = not bridge.status().connected
        report['automatic_promotion'] = False
        if args.keep_open_seconds > 0:
            end = time.perf_counter() + min(120, args.keep_open_seconds)
            print('Disposable fixtures ready for UI inspection; no user documents involved.', flush=True)
            while time.perf_counter() < end:
                pythoncom.PumpWaitingMessages()
                time.sleep(.1)
    except Exception as error:
        import traceback
        report['error'] = str(error)
        report['traceback'] = traceback.format_exc()
    finally:
        for show in shows:
            try:
                show.View.Exit()
            except Exception:
                pass
        for doc in documents:
            try:
                doc.Saved = True
                doc.Close()
            except Exception:
                pass
        if app is not None:
            try:
                if int(app.Presentations.Count) == 0:
                    app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
        (output / 'integration.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
