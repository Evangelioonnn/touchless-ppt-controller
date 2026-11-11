using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace TouchlessPPTControllerLauncher
{
    internal interface IWorkerHost : IDisposable
    {
        event Action<Dictionary<string, object>> Message;
        bool HasExited { get; }
        bool IsFrozen { get; }
        string LastError { get; }
        int StartCount { get; }
        int ProcessId { get; }
        void Start(string channelName, string[] arguments);
        bool Send(string action, Dictionary<string, object> values = null);
        void KillOwned();
    }

    internal sealed class BackendHost : IWorkerHost
    {
        public event Action<Dictionary<string, object>> Message;
        private Process child;
        private OwnedJob job;
        private readonly object inputLock = new object();
        private readonly Queue<string> pending = new Queue<string>();
        private readonly AutoResetEvent ready = new AutoResetEvent(false);
        private readonly object logLock = new object();
        private bool disposed;
        private readonly string root;
        private string configRoot;
        public bool IsFrozen { get; private set; }
        public string LastError { get; private set; }
        public int StartCount { get; private set; }
        public int ProcessId { get { try { return child == null ? 0 : child.Id; } catch { return 0; } } }
        public bool HasExited { get { try { return child == null || child.HasExited; } catch { return true; } } }
        public BackendHost(string directory)
        {
            root = directory; LastError = "";
            var writer = new Thread(WriteCommands); writer.IsBackground = true; writer.Start();
        }
        public void Start(string channelName, string[] arguments)
        {
            if (!HasExited) throw new InvalidOperationException("后台仍在运行");
            if (job != null) { job.Dispose(); job = null; }
            if (child != null) { child.Dispose(); child = null; }
            lock (inputLock) pending.Clear();
            string path = Path.Combine(root, "launcher.runtime.json");
            if (!File.Exists(path)) path = Path.GetFullPath(Path.Combine(root, "..", "launcher.runtime.json"));
            configRoot = Path.GetDirectoryName(path);
            var config = File.Exists(path) ? new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(path, Encoding.UTF8)) : new Dictionary<string, object>();
            string worker = Path.GetFullPath(Path.Combine(configRoot, Value(config, "worker", "runtime/ControllerWorker.exe")));
            string executable, command;
            IsFrozen = File.Exists(worker);
            if (IsFrozen) { executable = worker; command = "--protocol --default-backend " + Value(config, "backend", "onnx"); }
            else
            {
                executable = Value(config, "python", "python");
                if (executable.Contains("/") || executable.Contains("\\")) executable = Path.GetFullPath(Path.Combine(configRoot, executable));
                string script = Path.GetFullPath(Path.Combine(configRoot, Value(config, "script", "ppt_controller.py")));
                if (!File.Exists(script)) throw new FileNotFoundException("找不到后台文件，请使用完整软件包。", script);
                command = "-B -u " + Quote(script) + " --protocol --default-backend " + Value(config, "backend", "torch");
            }
            command += " --native-preview-map " + Quote(channelName);
            for (int i = 0; i < arguments.Length; i++)
            {
                if (arguments[i] == "--observe-only" || arguments[i] == "--headless") command += " " + arguments[i];
                if (arguments[i] == "--metrics" && i + 1 < arguments.Length) command += " --metrics " + Quote(arguments[++i]);
            }
            var info = new ProcessStartInfo(executable, command) { WorkingDirectory = configRoot, UseShellExecute = false,
                CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden, RedirectStandardInput = true,
                RedirectStandardOutput = true, RedirectStandardError = true, StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8 };
            info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"; info.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
            string extra = Value(config, "extra_site", "");
            if (extra.Length > 0) info.EnvironmentVariables["TOUCHLESS_PPT_EXTRA_SITE"] = Path.GetFullPath(Path.Combine(configRoot, extra));
            child = new Process { StartInfo = info, EnableRaisingEvents = true };
            child.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e)
            {
                if (e.Data == null || e.Data.Length > 65536 || !e.Data.StartsWith("{")) return;
                try
                {
                    var data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(e.Data);
                    var handler = Message; if (handler != null) handler(data);
                }
                catch (Exception error) { Log("Protocol: " + error.Message); }
            };
            child.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (!String.IsNullOrEmpty(e.Data)) { LastError = e.Data; Log(e.Data); } };
            child.Start(); job = new OwnedJob(child); StartCount++;
            child.BeginOutputReadLine(); child.BeginErrorReadLine();
        }
        public bool Send(string action, Dictionary<string, object> values = null)
        {
            if (disposed || HasExited) return false;
            var data = values == null ? new Dictionary<string, object>() : new Dictionary<string, object>(values);
            data["action"] = action;
            string line = new JavaScriptSerializer().Serialize(data);
            lock (inputLock)
            {
                if (action == "quit") pending.Clear();
                if (pending.Count >= 64) return false;
                pending.Enqueue(line);
            }
            ready.Set(); return true;
        }
        private void WriteCommands()
        {
            while (true)
            {
                ready.WaitOne();
                if (disposed) return;
                while (true)
                {
                    string line;
                    lock (inputLock) { if (pending.Count == 0) break; line = pending.Dequeue(); }
                    try { Process process = child; if (process != null && !process.HasExited) { process.StandardInput.WriteLine(line); process.StandardInput.Flush(); } } catch { }
                }
            }
        }
        private void Log(string line)
        {
            try
            {
                lock (logLock)
                {
                    string directory = Path.Combine(UiPreferences.DataDirectory(), "logs"); Directory.CreateDirectory(directory);
                    string path = Path.Combine(directory, "launcher-stderr.log");
                    if (File.Exists(path) && new FileInfo(path).Length > 1024 * 1024)
                    {
                        if (File.Exists(path + ".2")) File.Delete(path + ".2");
                        if (File.Exists(path + ".1")) File.Move(path + ".1", path + ".2");
                        File.Move(path, path + ".1");
                    }
                    File.AppendAllText(path, line + Environment.NewLine, Encoding.UTF8);
                }
            }
            catch { }
        }
        public void KillOwned()
        {
            if (job != null) { job.Dispose(); job = null; }
            try { if (child != null && !child.HasExited) child.Kill(); } catch { }
        }
        public void Dispose()
        {
            disposed = true; ready.Set(); KillOwned();
            if (child != null) { child.Dispose(); child = null; }
        }
        public static string Value(Dictionary<string, object> values, string key, string fallback)
        { return values != null && values.ContainsKey(key) && values[key] != null ? Convert.ToString(values[key]) : fallback; }
        private static string Quote(string text) { return "\"" + text.Replace("\"", "\\\"") + "\""; }
    }
}
