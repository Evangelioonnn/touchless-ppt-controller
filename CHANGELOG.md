# Changelog

## v0.2.0-beta.3 — 2026-11-11

First public source snapshot and Windows x64 beta release. Earlier local iterations are
not published in this repository.

- Use the official pretrained YOLO26s Pose model locally; no custom training or dataset.
- Keep the approved single-lecturer raised-hand gestures, one-shot holds and automatic
  return after leaving the frame, without changing the explicit lock choice.
- Separate native control and camera-preview windows from the resident worker lifetime.
- Add independent preview close/minimize/maximize/restore/fullscreen and mouse controls.
- Add ask / close-to-tray / full-exit preferences, persistent settings, tray restoration
  and single-instance activation without a second camera or model load.
- Simplify the dark panel, keep the C1 rounded icon and move advanced controls to settings.
- Suspend preview drawing when hidden/minimized, not inference; use a bounded latest-frame
  local mapping with stale/incomplete-frame guards and no frame recording or upload.
- Keep per-window shortcuts compatible with IME: Escape restores/hides preview, Q exits.
- Preserve owned-process supervision, local diagnostics, bounded retries and COM routing.
- Provide portable, installer, corresponding-source and pinned-model restoration assets.

### Validation and limitations

The tested native executable and worker are preserved in this publication. Documentation
and release metadata are refreshed without changing gesture/model/window behavior.
Core Python regression and native component checks passed. Real-camera window/tray tests,
path relocation and local installer/uninstaller checks were performed. This does not claim
full human-gesture acceptance, a clean Windows VM, actual multi-monitor DPI changes,
OS cold starts, OS shutdown or compatibility with every Office/device combination.
See [acceptance scope](docs/ACCEPTANCE.md) and [restoration guide](docs/RESTORE.md).
