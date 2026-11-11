using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace TouchlessPPTControllerLauncher
{
    internal sealed class ControllerAppContext : ApplicationContext
    {
        public const string ActivationEventName = @"Local\TouchlessPPTController.Activate.v3";
        internal readonly AppStatus Model = new AppStatus();
        internal readonly UiPreferences Preferences;
        internal readonly ControlPanel Panel;
        internal readonly PreviewForm Preview;
        private readonly IWorkerHost host;
        private readonly PreviewChannel channel;
        private readonly Control dispatcher = new Control();
        private readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
        private readonly Stopwatch uptime = Stopwatch.StartNew();
        private readonly Icon icon;
        private readonly string[] arguments;
        private NotifyIcon tray;
        private ContextMenuStrip trayMenu;
        private ToolStripMenuItem trayLock, trayPreview;
        private SettingsDialog settings;
        private EventWaitHandle activation;
        private RegisteredWaitHandle activationWait;
        private bool closing, restarting, finished, trayReady;
        private bool reportedStopped;
        private bool? sentVisibility;
        private long closeAt, lastReportAt;
        private int autoExitMs;
        private readonly bool observeOnly, componentTest;
        private string reportPath;
        internal int PreviewShowCount, PreviewHideCount;
        internal bool TrayReady { get { return trayReady; } }
        internal bool IsClosing { get { return closing; } }
        public ControllerAppContext(string[] args) : this(args, new BackendHost(AppDomain.CurrentDomain.BaseDirectory), UiPreferences.Load(UiPreferences.DataDirectory()), false) { }
        internal ControllerAppContext(string[] args, IWorkerHost backend, UiPreferences prefs, bool test)
        {
            componentTest = test; arguments = args; host = backend; Preferences = prefs;
            observeOnly = Array.IndexOf(args, "--observe-only") >= 0;
            for (int i = 0; i + 1 < args.Length; i++)
            { if (args[i] == "--auto-exit-ms") int.TryParse(args[i + 1], out autoExitMs); if (args[i] == "--ui-report") reportPath = Path.GetFullPath(args[i + 1]); }
            icon = LoadIcon(); channel = new PreviewChannel();
            IntPtr dispatchHandle = dispatcher.Handle;
            Panel = new ControlPanel(Command, delegate(string id) { Send("target", new Dictionary<string, object> { { "value", id } }); }, ShowSettings, TogglePreview, icon);
            Panel.CompactOnFirstShow = Preferences.Panel.Width == 0 || Preferences.Panel.Height == 0;
            Preview = new PreviewForm(Command, icon);
            Panel.CloseRequested += RequestPanelClose;
            Panel.FormClosing += SystemClosing; Preview.FormClosing += SystemClosing;
            Preview.HiddenRequested += HidePreview;
            Preview.VisibilityStateChanged += NotifyVisibility;
            Preview.ModeChanged += delegate(string mode) { Preferences.PreviewMode = mode; SavePreferences(); };
            Panel.ResizeEnd += delegate { Preferences.Panel.Capture(Panel); SavePreferences(); };
            Panel.Resize += delegate { if (Panel.Visible && Panel.WindowState != FormWindowState.Minimized) Preferences.Panel.Capture(Panel); };
            Preview.ResizeEnd += delegate { Preview.CapturePlacement(Preferences.Preview); SavePreferences(); };
            Preferences.Panel.Restore(Panel); Preferences.Preview.Restore(Preview);
            host.Message += Receive;
            if (!componentTest)
            {
                CreateTray();
                activation = new EventWaitHandle(false, EventResetMode.AutoReset, ActivationEventName);
                activationWait = ThreadPool.RegisterWaitForSingleObject(activation, delegate { Post(ShowPanel); }, null, Timeout.Infinite, false);
                SystemEvents.SessionEnding += OnSessionEnding;
                ShowPanel();
                if (Preferences.ShowPreviewOnStart && Array.IndexOf(args, "--headless") < 0) ShowPreview();
                timer.Interval = 40; timer.Tick += Tick; timer.Start();
                dispatcher.BeginInvoke(new Action(StartWorker));
            }
            if (Preferences.Warning != "") Model.LastOperation = Preferences.Warning;
            RefreshViews();
        }
        private static Icon LoadIcon()
        {
            foreach (string candidate in new string[] { Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "windows_launcher/TouchlessPPTController.ico"), Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "../windows_launcher/TouchlessPPTController.ico") })
                if (File.Exists(candidate)) { try { return new Icon(candidate); } catch { } }
            return (Icon)SystemIcons.Application.Clone();
        }
        private void CreateTray()
        {
            try
            {
                trayMenu = new ContextMenuStrip { BackColor = Theme.Surface, ForeColor = Theme.Text, ShowImageMargin = false };
                trayMenu.Items.Add("打开控制面板", null, delegate { ShowPanel(); });
                trayPreview = new ToolStripMenuItem("收起预览", null, delegate { TogglePreview(); }); trayMenu.Items.Add(trayPreview);
                trayLock = new ToolStripMenuItem("解锁控制", null, delegate { Command("toggle_lock"); }); trayMenu.Items.Add(trayLock);
                trayMenu.Items.Add(new ToolStripSeparator());
                trayMenu.Items.Add("设置", null, delegate { ShowSettings(); });
                trayMenu.Items.Add("收起所有窗口", null, delegate { HideAll(); });
                trayMenu.Items.Add(new ToolStripSeparator());
                trayMenu.Items.Add("完全退出程序", null, delegate { BeginExit(); });
                tray = new NotifyIcon { Icon = icon, Text = "PPT 控制器 · 正在启动", ContextMenuStrip = trayMenu, Visible = true };
                tray.DoubleClick += delegate { ShowPanel(); }; trayReady = true;
                Panel.ContextMenuStrip = trayMenu;
            }
            catch (Exception error) { trayReady = false; Model.LastOperation = "托盘创建失败，窗口不会被全部隐藏：" + error.Message; }
        }
        private void Post(Action action)
        {
            if (finished || dispatcher.IsDisposed) return;
            try { dispatcher.BeginInvoke(new Action(delegate { if (!finished) action(); })); } catch (InvalidOperationException) { }
        }
        private void Receive(Dictionary<string, object> message)
        { Post(delegate { Model.Update(message); RefreshViews(); }); }
        internal void StartWorker()
        {
            if (closing || finished) return;
            try { host.Start(channel.Name, arguments); reportedStopped = false; sentVisibility = null; NotifyVisibility(); }
            catch (Exception error) { Model.LastOperation = "后台启动失败，请在设置中检查或重启。"; Model.RawMessage = error.Message; RefreshViews(); ShowPanel(); }
        }
        internal void Command(string action)
        {
            if (action == "quit") { BeginExit(); return; }
            if (action == "swap")
            {
                bool swap = Model.Settings.ContainsKey("swap_hands") && Model.Settings["swap_hands"] is bool ? (bool)Model.Settings["swap_hands"] : true;
                Send("settings", new Dictionary<string, object> { { "values", new Dictionary<string, object> { { "swap_hands", !swap } } } }); return;
            }
            Send(action);
        }
        private void Send(string action, Dictionary<string, object> values = null)
        { if (!host.Send(action, values)) { Model.LastOperation = "后台尚未就绪或请求繁忙，请稍后重试。"; RefreshViews(); } }
        internal void ShowPanel()
        {
            if (finished || closing) return;
            Panel.RefreshStatus(Model, Preview.IsDrawable, observeOnly);
            if (componentTest) return;
            Panel.Show(); if (Panel.WindowState == FormWindowState.Minimized) Panel.WindowState = Preferences.Panel.Maximized ? FormWindowState.Maximized : FormWindowState.Normal;
            Panel.Activate();
        }
        internal void ShowPreview()
        {
            if (finished || closing) return;
            if (!componentTest)
            {
                Preview.Show(); Preview.RestoreFromMinimized();
                Preview.SetMode(Preferences.PreviewMode); Preview.Activate();
            }
            PreviewShowCount++; NotifyVisibility(); RefreshViews();
        }
        internal void HidePreview()
        {
            if (!trayReady && !Panel.Visible && !componentTest) { ShowPanel(); Model.LastOperation = "托盘不可用，已保留控制面板作为恢复入口。"; }
            Preview.CapturePlacement(Preferences.Preview); Preview.Hide(); Preview.Canvas.Clear("预览已收起"); PreviewHideCount++;
            SavePreferences(); NotifyVisibility(); RefreshViews();
        }
        internal void TogglePreview() { if (Preview.Visible && Preview.WindowState != FormWindowState.Minimized) HidePreview(); else ShowPreview(); }
        private void NotifyVisibility()
        {
            if (finished) return;
            bool visible = Preview.IsDrawable;
            if (!visible) { Preview.Canvas.Clear("等待恢复预览…"); Preview.LastFrameAt = 0; }
            if (sentVisibility != visible && !host.HasExited)
            { if (host.Send("preview_visibility", new Dictionary<string, object> { { "visible", visible } })) sentVisibility = visible; }
            RefreshViews();
        }
        internal void HideAll()
        {
            if (!trayReady && !componentTest) { Model.LastOperation = "托盘不可用，无法收起所有窗口。"; ShowPanel(); return; }
            Preferences.Panel.Capture(Panel); Panel.Hide(); HidePreview(); ShowBackgroundTip();
        }
        internal void RequestPanelClose()
        {
            if (closing) return;
            if (settings != null && !settings.IsDisposed) { settings.Activate(); return; }
            string choice = Preferences.CloseAction;
            if (choice == "ask")
            {
                using (var dialog = new CloseChoiceDialog(icon))
                {
                    var result = dialog.ShowDialog(Panel);
                    if (result != DialogResult.Yes && result != DialogResult.No) return;
                    choice = result == DialogResult.Yes ? "tray" : "exit";
                    if (dialog.RememberChoice) { Preferences.CloseAction = choice; SavePreferences(); }
                }
            }
            ApplyCloseChoice(choice);
        }
        internal void ApplyCloseChoice(string choice)
        {
            if (choice == "exit") { BeginExit(); return; }
            if (choice != "tray") return;
            if (!trayReady && !componentTest) { Model.LastOperation = "系统托盘不可用，请保持窗口打开，或选择完全退出。"; RefreshViews(); return; }
            Preferences.Panel.Capture(Panel); Panel.Hide(); SavePreferences(); ShowBackgroundTip();
        }
        private void ShowBackgroundTip()
        {
            if (Preferences.BackgroundTipShown) return;
            Preferences.BackgroundTipShown = true; SavePreferences();
            if (tray != null) tray.ShowBalloonTip(5000, "PPT 控制器仍在运行", "摄像头和识别仍在工作。双击右下角图标恢复；右键可锁定或完全退出。", ToolTipIcon.Info);
        }
        internal void ShowSettings()
        {
            if (finished || closing) return;
            if (settings != null && !settings.IsDisposed) { settings.Activate(); return; }
            ShowPanel();
            using (settings = new SettingsDialog(Preferences, Model, host.IsFrozen, ApplySettings, Command, Restart, DiagnosticsUi.OpenLogs,
                delegate { try { DiagnosticsUi.Export(settings); } catch (Exception error) { MessageBox.Show(settings, error.Message, "导出失败"); } }, icon))
            { settings.ShowDialog(Panel); }
            settings = null;
        }
        private bool ApplySettings(Dictionary<string, object> values)
        {
            if (!SavePreferences()) return false;
            Preview.SetMode(Preferences.PreviewMode);
            if (values.Count > 0 && !host.Send("settings", new Dictionary<string, object> { { "values", values } }))
            { Model.LastOperation = "界面偏好已保存；设备设置未应用，请在后台就绪后重试。"; RefreshViews(); return false; }
            return true;
        }
        private bool SavePreferences()
        {
            bool saved = Preferences.Save(); if (!saved) { Model.LastOperation = Preferences.Warning; RefreshViews(); } return saved;
        }
        internal void Restart()
        {
            if (closing || restarting) return;
            restarting = true; closeAt = uptime.ElapsedMilliseconds; host.Send("quit"); Model.LastOperation = "正在重启后台…重启后控制默认锁定。"; RefreshViews();
        }
        internal void BeginExit()
        {
            if (closing || finished) return;
            closing = true; closeAt = uptime.ElapsedMilliseconds;
            host.Send("quit"); Model.LastOperation = "正在退出并释放摄像头…"; RefreshViews();
            if (componentTest) return;
        }
        private void Tick(object sender, EventArgs e)
        {
            if (autoExitMs > 0 && uptime.ElapsedMilliseconds >= autoExitMs) BeginExit();
            if ((closing || restarting) && !host.HasExited && uptime.ElapsedMilliseconds - closeAt > 5000) host.KillOwned();
            if (closing && host.HasExited) { Finish(); return; }
            if (restarting && host.HasExited) { restarting = false; Model.Locked = true; Model.Ready = false; Model.ModelLoads = 0; StartWorker(); }
            if (!closing && !restarting && host.StartCount > 0 && host.HasExited && !reportedStopped)
            {
                reportedStopped = true; Model.Ready = false; Model.PresenterVisible = false; Model.Connected = false;
                Model.CameraState = "stopped"; Model.Targets.Clear(); Model.TargetId = "";
                Model.LastOperation = "后台已停止，请在高级设置中检查日志或重启后台。"; Model.RawMessage = host.LastError;
                Preview.Canvas.Clear("识别后台已停止，请打开控制面板查看。"); RefreshViews();
                if (!Panel.Visible && tray != null) tray.ShowBalloonTip(5000, "PPT 控制器后台已停止", "请双击托盘图标打开控制面板，检查或重启后台。", ToolTipIcon.Warning);
            }
            bool drawable = Preview.IsDrawable;
            timer.Interval = drawable ? 40 : 250;
            if (drawable)
            {
                try { var frame = channel.ReadLatest(); if (frame != null) Preview.ReceiveFrame(frame); }
                catch (Exception error) { Model.RawMessage = "预览读取失败：" + error.Message; }
                if (Preview.LastFrameAt > 0 && PreviewChannel.Now - Preview.LastFrameAt > 2) Preview.Canvas.Clear("等待新的摄像头画面…识别状态见控制面板");
            }
            if (uptime.ElapsedMilliseconds - lastReportAt >= 1000) { lastReportAt = uptime.ElapsedMilliseconds; WriteReport(false); }
        }
        private void RefreshViews()
        {
            if (finished || Panel == null || Preview == null) return;
            if (!Panel.IsDisposed && (Panel.Visible || componentTest)) Panel.RefreshStatus(Model, Preview.IsDrawable, observeOnly);
            if (tray != null)
            {
                string tip = "PPT 控制器 · " + (Model.Locked ? "已锁定" : "已启用") + " · " + Model.PersonText;
                tray.Text = tip.Substring(0, Math.Min(63, tip.Length));
                trayLock.Text = Model.Locked ? "解锁控制" : "锁定控制"; trayPreview.Text = Preview.IsDrawable ? "收起预览" : "显示预览";
            }
            if (!Preview.IsDisposed && Preview.Visible && Model.CameraState != "ready") Preview.Canvas.Clear(Model.CameraState == "stopped" ? "识别后台已停止，请在控制面板中重启。" : "等待摄像头连接…");
        }
        private void SystemClosing(object sender, FormClosingEventArgs e)
        { if (e.CloseReason == CloseReason.WindowsShutDown || e.CloseReason == CloseReason.TaskManagerClosing) { e.Cancel = false; BeginExit(); } }
        private void OnSessionEnding(object sender, SessionEndingEventArgs e) { host.Send("quit"); Post(BeginExit); }
        private void WriteReport(bool stopped)
        {
            if (reportPath == null) return;
            try
            {
                using (var process = Process.GetCurrentProcess())
                {
                    var data = new { version = Application.ProductVersion, phase = stopped ? "stopped" : "running", process_id = process.Id,
                        worker_process_id = host.ProcessId, worker_start_count = host.StartCount, model_loads = Model.ModelLoads,
                        worker_exited = host.HasExited, panel_visible = Panel.Visible, preview_visible = Preview.Visible,
                        preview_drawable = Preview.IsDrawable, preview_window_state = Preview.WindowState.ToString(),
                        panel_window_state = Panel.WindowState.ToString(), preview_mode = Preview.Mode, preview_read_frames = channel.FramesRead,
                        published_frames = Model.PublishedFrames, locked = Model.Locked, ready = Model.Ready,
                        tray_available = trayReady, preview_show_count = PreviewShowCount, preview_hide_count = PreviewHideCount,
                        ui_rss_bytes = process.WorkingSet64, ui_handles = process.HandleCount, elapsed_s = uptime.Elapsed.TotalSeconds };
                    Directory.CreateDirectory(Path.GetDirectoryName(reportPath)); string temp = reportPath + ".tmp";
                    File.WriteAllText(temp, new JavaScriptSerializer().Serialize(data));
                    if (File.Exists(reportPath)) File.Replace(temp, reportPath, null); else File.Move(temp, reportPath);
                }
            }
            catch { }
        }
        private void Finish()
        {
            if (finished) return;
            Preferences.Panel.Capture(Panel); Preview.CapturePlacement(Preferences.Preview); SavePreferences();
            WriteReport(true); DisposeResources(); ExitThread();
        }
        private void DisposeResources()
        {
            if (finished) return; finished = true; timer.Stop(); timer.Dispose();
            if (activationWait != null) activationWait.Unregister(null);
            if (activation != null) activation.Dispose();
            if (!componentTest) SystemEvents.SessionEnding -= OnSessionEnding;
            if (tray != null) { tray.Visible = false; tray.Dispose(); }
            if (trayMenu != null) trayMenu.Dispose();
            if (settings != null) settings.Dispose();
            Panel.AllowExit = true; Preview.AllowExit = true; Panel.Dispose(); Preview.Dispose();
            host.Dispose(); channel.Dispose(); dispatcher.Dispose(); icon.Dispose();
        }
        protected override void Dispose(bool disposing) { if (disposing) DisposeResources(); base.Dispose(disposing); }
    }
}
