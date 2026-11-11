# Third-party components and model provenance

The application source is provided under AGPL-3.0; see `LICENSE`.

The bundled pose weights originate from Ultralytics YOLO26. The source checkpoint is
`yolo26s-pose.pt`, from the official Ultralytics assets release:

https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26s-pose.pt

Source SHA-256:
`a083adb42303728ae14c4bd6bd56d80da46f82fb2564dbd6f31dcc92ea321646`

The ONNX file is a format conversion of the same model, not a new trained model.
Conversion does not remove the original model's licensing requirements. Exact model
hashes and export options are in `models/manifest.json` and the release build report.

Runtime distributions include Python, NumPy, OpenCV, ONNX Runtime and optional
pywin32 for the COM control candidate. The release builder copies available license
and notice files into `third_party_licenses/` and records component versions.
OpenCV includes additional third-party components; retain its bundled notices.
PyInstaller has a bootloader distribution exception; retain the relevant license.

The desktop icon was generated for this project. It does not use the Microsoft
PowerPoint logo. Microsoft PowerPoint is an external proprietary prerequisite and
is not included with this software. The project is not affiliated with Microsoft.

This release includes corresponding application source and a separate backup containing
both the original checkpoint and its tested ONNX conversion. Retain these notices and
the bundled runtime license files when redistributing. A new export/build must be
checked against its own actual file inventory; these notices do not certify arbitrary
later modifications or remove any upstream obligations.
