# Build and development

Target: Windows x64, CPython 3.12.13. Use isolated environments. Do not copy an entire
development Conda environment into the distributed application.

## 1. Restore the published model (recommended)

To restore the exact tested model files from this release, use the explicit standard-library
restore command. It needs no Torch or training environment:

```powershell
python tools/restore_models.py
```

Alternatively download `models.zip` from release `v0.2.0-beta.3` and extract `models/`
into the source root. See [RESTORE.md](RESTORE.md). Normal application startup never
downloads weights. Both the original PT and converted ONNX are archived in the Release.

### Optional: export again from the source checkpoint

Install `requirements/export-lock.txt` into a dedicated export environment. A compatible
CPU or CUDA PyTorch wheel may be selected from the official PyTorch package index.

```powershell
python -m venv .venv-export
.venv-export\Scripts\python.exe -m pip install -r requirements/export-lock.txt
.venv-export\Scripts\python.exe tools/fetch_model.py
.venv-export\Scripts\python.exe tools/export_model.py
```

The fetcher validates the pinned source SHA-256. Export is a developer/build operation;
end users do not run export, training, or model downloads at application startup.

## 2. Create a runtime/build environment

```powershell
python -m venv .venv-release
.venv-release\Scripts\python.exe -m pip install -r requirements/build-lock.txt
.venv-release\Scripts\python.exe -m unittest discover -s tests -v
.venv-release\Scripts\python.exe ppt_controller.py --self-check --backend onnx
```

The ONNX runtime environment must not require importing Torch or Ultralytics.

## 3. Run or build

```powershell
.venv-release\Scripts\python.exe ppt_controller.py --backend onnx
.venv-release\Scripts\python.exe tools/build_launcher.py --backend onnx
.\build\development\TouchlessPPTController.exe
.venv-release\Scripts\python.exe tools/build_release.py
```

The native C# compiler from .NET Framework is used for the control panel. A generated
`launcher.runtime.json` points to the local development interpreter. It is ignored by
Git and must not be reused as the release configuration. Release configuration points
only to the packaged worker and resources.

Re-exporting or rebuilding on another toolchain is not a byte-for-byte reproducibility
claim. Record new model/package hashes and retest, rather than reuse this Release's sums.

To additionally build the installer, provide a locally installed Inno Setup compiler:

```powershell
.venv-release\Scripts\python.exe tools/build_release.py --iscc "path\to\ISCC.exe"
```

Inno Setup is a build tool and is not included with the application. The installer uses
per-user installation, does not require administrator privileges, and creates no service,
startup task, or telemetry uploader. Build scripts do not install the compiler themselves.

## Tests and diagnostics

`tools/benchmark_startup.py` performs repeated fresh-process trials, explicitly not OS
cold-start trials. `tools/compare_backends.py` checks decoding against the checkpoint.
Its default example-image augmentations are not a representative real-gesture dataset.
`tools/test_powerpoint_integration.py` creates disposable test decks only when no user
presentation is already open; otherwise it records a skip.

Logs and temporary test data must be kept out of the public repository. No tool needs
Windows security exceptions or a disabled antivirus to build or pass checks.

## Source and model release assets

After building and testing the runtime, explicitly create the restoration attachments:

```powershell
.venv-release\Scripts\python.exe tools/build_model_backup.py
.venv-release\Scripts\python.exe tools/prepare_public_source.py
```

The model backup includes PT/ONNX/manifest only. The source archive is an explicit allowlist
and excludes environments, model binaries, private validation, logs and earlier packages.
`SHA256SUMS.txt` includes the current portable, installer (if present), source and model
assets. These commands do not create a GitHub repository, upload or publish anything.

## Native UI and tray checks

```powershell
.venv-release\Scripts\python.exe tools/check_native_ui.py
```

This compiles the native component harness separately from the application, exercises
window/close policies without a camera, and renders synthetic UI at several layout scales.
It is not a substitute for actual monitor DPI, system tray, camera or human gesture checks.
The application build excludes `NativeUiTests.cs` as an entry point.

The native supervisor owns the tray, worker and windows. A session-local, random 8 MiB
mapping carries only the newest BGR frame; a sequence guard drops incomplete copies.
The Python GUI worker is launched with `--native-preview-map` and creates no OpenCV window.
`preview_visibility` is display-only and must never invalidate commands, reset gestures,
reopen the camera, or alter the explicit lock choice.

`ui-settings.json` is owned by the native layer, separate from worker `settings.json`.
Diagnostic-only `--observe-only`, `--auto-exit-ms`, `--ui-report` and `--metrics` are available
for scoped local acceptance; no UI report or frame recording is enabled in normal use.
