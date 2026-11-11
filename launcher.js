const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const projectRoot = __dirname;
const nativeLauncher = path.join(projectRoot, "build", "development", "TouchlessPPTController.exe");
const localPython = path.join(projectRoot, ".venv-release", "Scripts", "python.exe");
const python = process.env.TOUCHLESS_PPT_PYTHON || (fs.existsSync(localPython) ? localPython : "python");
const native = fs.existsSync(nativeLauncher);
const executable = native ? nativeLauncher : python;
const args = native ? process.argv.slice(2) : [
  "-B", "-u", path.join(projectRoot, "ppt_controller.py"),
  "--backend", process.env.TOUCHLESS_PPT_BACKEND || "onnx",
  ...process.argv.slice(2),
];
console.log("Starting Touchless PPT Controller...");
const child = spawn(executable, args, {
  cwd: projectRoot,
  env: { ...process.env, PYTHONUNBUFFERED: "1" },
  windowsHide: true,
  stdio: "inherit",
});
child.on("error", error => {
  console.error("Could not start the controller: " + error.message);
  process.exitCode = 1;
});
child.on("exit", code => process.exit(code ?? 1));
process.on("SIGINT", () => { if (!child.killed) child.kill(); });
process.on("SIGTERM", () => { if (!child.killed) child.kill(); });

