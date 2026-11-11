# Privacy

Camera frames are processed locally in memory. The default program does not save
photos, record video, upload camera data, register faces, or send usage telemetry.

Settings and bounded diagnostic logs are saved to the current user's local data
directory, normally `%LOCALAPPDATA%\TouchlessPPTController`. Settings contain device
and display preferences. Logs can include device names, local resource paths,
selected window identifiers, errors, and action results. They are never uploaded
automatically. Review and redact them before sharing an issue report.

The diagnostics-only `--observe-only` mode disables outbound PowerPoint commands.
An optional `--metrics` report records resource counts, timing, and camera/runtime
states, not camera frames or body keypoint coordinates. It is not enabled by default.

Presenter binding uses short-lived spatial continuity, not biometric identity.
Ambiguous or lost targets require reselection. Data in memory is discarded on exit.

Build tools may explicitly download pinned dependencies or the model when invoked
by a developer. Normal packaged startup uses local files and does not need a network.
