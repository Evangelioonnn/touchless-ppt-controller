# Acceptance scope — v0.2.0-beta.3

This is a public **beta / prerelease**, not a claim that every Windows/Office/camera
combination or full human lecture workflow has passed. The native executable and worker
from local UI acceptance are preserved; publication refreshes documentation and adds
model-restoration tooling, not recognition/gesture thresholds.

## Completed checks

| Area | Evidence and limits |
| --- | --- |
| Core Python behavior | 56 synthetic/fault regression cases: one-shot gestures, relaxed upper-body use, absence/reentry, explicit lock intent, stale commands, bounded camera recovery, mocked GPU failure, target routing and preview protocol |
| Model restoration | 4 additional offline fixture tests: round-trip/idempotence, refuse overwriting a bad local file, reject corrupt weights before installing either model, reject unexpected/traversal ZIP members |
| Native UI | 143 component assertions, including persistent preferences, corrupt/unwritable settings, independent close behavior, keyboard handling, 20 view cycles, bounded native GDI use and torn/stale/invalid-frame rejection |
| Layout | Offscreen scale simulations at 100/125/150/200%, visually inspected; not real OS DPI-switch/multi-monitor tests |
| Real Windows UI | Camera preview and panel independently hidden; preview titlebar X, minimize/maximize/restore, fullscreen/mouse exit and shortcuts checked; hide/show preserves unlock and the worker/model instance |
| User confirmations | System-tray double-click restored the panel; saved full-exit preference and titlebar X ended the owned worker, confirmed by logs |
| Final-binary observation | Approximately 600.7 seconds of observe-only camera/UI operation; one model load/worker start; no PPT commands or saved camera images. Only about 49.3 seconds were explicitly sampled with both windows hidden, not ten minutes of pure background human use |
| Package relocation | Same reference computer, Chinese/space paths on two drives and system-only PATH; dependencies loaded inside the package, Torch not imported |
| Installer | Reference-machine install/inference/uninstall succeeded; uninstall preserved user data and unowned sentinel files |
| PowerPoint bridge | Unchanged bridge previously tested with disposable local Office 16 decks: 20 forward/backward operations, multi-document targeting and animation steps; not a new full human end-to-end test for this release |

Run checks yourself with `tools/run_checks.py`, `tools/check_native_ui.py` and
`ppt_controller.py --self-check --backend onnx`. The first two need development/build
dependencies; ordinary users do not need to run them. Fault-injection tests intentionally
log simulated busy cameras, driver errors and device loss; those are not actual failures.

The release notes record the final remote-clone/model-download restoration outcome and
asset checksums. No CI success is claimed until its remote workflow actually succeeds.

## Not yet covered

- Complete real-user seated/standing/partial-body lectures, especially hidden-window
  gestures, leaving/reentry and everyday false-trigger rates.
- A representative 100-frame cross-backend dataset and real gesture-event replay;
  example-image variations are not a substitute. ONNX remains a candidate backend.
- A truly clean Windows machine with no developer environment, actual offline-network
  testing, multiple Office builds/cameras/CPUs and read-only-install combinations.
- Real multi-monitor/DPI transitions, OS logoff/shutdown and three actual OS cold starts.
- A long final-binary, both-windows-hidden, human-use endurance run.

## Intended behavior and known boundaries

Windows x64 and local Microsoft PowerPoint are required. WPS, browser slides, macOS,
Linux and Windows ARM are not claimed as supported. ONNX CPU may start lighter without
running faster than NVIDIA CUDA. The unsigned EXE is not a reason to disable security.

This is a single-lecturer controller, not face recognition or identity verification.
Absence pauses commands but does not lock; another visible person may become the primary
person. Manually lock when leaving it unattended. A normal-looking raised arm can match
the unchanged gesture geometry.

Brief missing observations pause a hold for up to 0.30 s without counting missing time;
longer interruptions cancel unfinished timing, not the user's unlock choice. Freshness
adapts to CPU latency with a 3 s ceiling; genuinely stale input cannot control slides.
Visible-body wrists resting below a desk can rearm after 0.35 s; prolonged wrist-only
detection loss can consequently resemble release. A fully absent body never rearms.

COM is the default; ambiguity/multiple PowerPoint processes are refused rather than
guessed. Targeted-key mode is best effort: a sent Windows message is not verified slide
progress, and the reference windowed show did not advance through that path. COM next
may advance an animation step instead of a whole slide.

Normal GUI uses the native launcher and tray. Direct Python/OpenCV is a development
compatibility path with different Esc/Q window semantics, as documented in README.
