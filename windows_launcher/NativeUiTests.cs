using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Reflection;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace TouchlessPPTControllerLauncher
{
    internal sealed class FakeWorker : IWorkerHost
    {
        public event Action<Dictionary<string, object>> Message;
        public bool HasExited { get; private set; }
        public bool IsFrozen { get { return true; } }
        public string LastError { get { return ""; } }
        public int StartCount { get; private set; }
        public int ProcessId { get { return 0; } }
        public bool Disposed;
        public readonly List<string> Actions = new List<string>();
        public void Start(string channel, string[] args) { StartCount++; HasExited = false; }
        public bool Send(string action, Dictionary<string, object> values = null) { Actions.Add(action); if (action == "quit") HasExited = true; return true; }
        public void KillOwned() { HasExited = true; }
        public void Dispose() { Disposed = true; HasExited = true; }
        public void Emit(Dictionary<string, object> data) { if (Message != null) Message(data); }
    }

    internal static class NativeUiTests
    {
        private static readonly List<object> checks = new List<object>();
        private static readonly List<string> failures = new List<string>();
        private static readonly List<object> layouts = new List<object>();
        private static void Check(bool condition, string name)
        { checks.Add(new { name = name, passed = condition }); if (!condition) failures.Add(name); }
        private static void Run(string name, Action test)
        { try { test(); } catch (Exception error) { Check(false, name + ": " + error); } }
        [STAThread]
        private static int Main(string[] args)
        {
            string output = Path.GetFullPath(args[0]); Directory.CreateDirectory(output);
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            Run("Preferences", delegate { TestPreferences(output); });
            Run("Channel", TestChannel);
            Run("Lifecycle", delegate { TestLifecycle(output); });
            Run("PreviewKeys", TestPreviewKeys);
            Run("Native view resources", TestViewResources);
            Run("Layouts", delegate { TestLayouts(output); });
            string report = new JavaScriptSerializer().Serialize(new { passed = failures.Count == 0, checks = checks, failures = failures, layouts = layouts,
                scope = "Native components and offscreen scale simulation, not actual desktop DPI or real camera acceptance" });
            File.WriteAllText(Path.Combine(output, "native-checks.json"), report); Console.WriteLine(report);
            return failures.Count == 0 ? 0 : 1;
        }
        private static void TestPreferences(string output)
        {
            string directory = Path.Combine(output, "preferences-" + Guid.NewGuid().ToString("N"));
            var prefs = UiPreferences.Load(directory); Check(prefs.CloseAction == "ask", "TRAY-01 fresh install asks");
            prefs.CloseAction = "tray"; prefs.ShowPreviewOnStart = false; prefs.PreviewMode = "overlay";
            prefs.Panel.Width = 680; prefs.Panel.Height = 500; Check(prefs.Save(), "TRAY-01 atomic save");
            var loaded = UiPreferences.Load(directory);
            Check(loaded.CloseAction == "tray" && !loaded.ShowPreviewOnStart && loaded.PreviewMode == "overlay" && loaded.Panel.Width == 680, "TRAY-01 preferences survive restart");
            File.WriteAllText(prefs.FilePath, "{broken"); var recovered = UiPreferences.Load(directory);
            Check(recovered.CloseAction == "ask" && recovered.Warning != "" && Directory.GetFiles(directory, "ui-settings.broken-*.json").Length == 1, "TRAY-01 damaged settings recover with backup");
            string blocked = Path.Combine(directory, "not-a-directory"); File.WriteAllText(blocked, "fixture");
            Check(!new UiPreferences(blocked).Save(), "TRAY-01 unwritable preferences fail without crashing");
        }
        private static void TestChannel()
        {
            using (var channel = new PreviewChannel())
            {
                Check(channel.ReadLatest() == null, "PERF-01 empty mapping");
                channel.View.Write(0, 0x31565054); channel.View.Write(4, 1); channel.View.Write(8, (long)1);
                channel.View.Write(16, 2); channel.View.Write(20, 1); channel.View.Write(24, 6); channel.View.Write(28, 6); channel.View.Write(32, PreviewChannel.Now);
                channel.View.WriteArray(64, new byte[] { 10, 20, 30, 40, 50, 60 }, 0, 6);
                Check(channel.ReadLatest() == null, "PERF-01 incomplete odd frame is ignored");
                channel.View.Write(8, (long)2);
                using (var frame = channel.ReadLatest()) Check(frame != null && frame.GetPixel(0, 0).R == 30 && frame.GetPixel(1, 0).B == 40, "PERF-01 BGR contract and padded bitmap rows");
                Check(channel.ReadLatest() == null, "PERF-01 duplicate frame is not repainted");
                channel.View.Write(8, (long)4); channel.View.Write(32, PreviewChannel.Now - 10);
                Check(channel.ReadLatest() == null, "PERF-01 stale frame is not displayed");
                channel.View.Write(32, PreviewChannel.Now); channel.View.Write(16, 10000);
                Check(channel.ReadLatest() == null, "PERF-01 corrupt dimensions bounded");
            }
        }
        private static void TestLifecycle(string output)
        {
            var fake = new FakeWorker(); var prefs = new UiPreferences(Path.Combine(output, "lifecycle-" + Guid.NewGuid().ToString("N"))) { CloseAction = "tray" };
            using (var context = new ControllerAppContext(new string[0], fake, prefs, true))
            {
                context.StartWorker(); context.Model.Locked = false;
                IntPtr panelHandle = context.Panel.Handle, previewHandle = context.Preview.Handle;
                context.Preview.StartPosition = FormStartPosition.Manual; context.Preview.Location = new Point(-20000, -20000); context.Preview.ShowInTaskbar = false; context.Preview.Opacity = 0; context.Preview.Show();
                context.Panel.Close(); Check(!context.IsClosing && !fake.Disposed && !context.Panel.IsDisposed && context.Preview.Visible, "WIN-04 closing panel to tray keeps visible preview and backend alive");
                context.Preview.Close(); Check(!context.Preview.IsDisposed && !context.Panel.IsDisposed && !context.IsClosing, "WIN-01 closing preview keeps panel and backend alive");
                for (int i = 0; i < 20; i++) { context.ShowPreview(); context.HidePreview(); }
                Check(fake.StartCount == 1 && context.PreviewShowCount == 20, "PERF-02 twenty view cycles do not restart worker");
                Check(!context.Model.Locked && !fake.Actions.Contains("lock") && !fake.Actions.Contains("settings") && !fake.Actions.Contains("quit"), "WIN-05 visibility does not lock or reconfigure");
                context.Model.Ready = true; fake.KillOwned();
                typeof(ControllerAppContext).GetMethod("Tick", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(context, new object[] { null, EventArgs.Empty });
                Check(!context.Model.Ready && context.Model.CameraState == "stopped" && fake.StartCount == 1, "LIFE-01 unexpected worker stop is reported without a restart loop");
                context.ApplyCloseChoice("exit"); Check(context.IsClosing && fake.Actions.Contains("quit"), "LIFE-02 explicit exit sends quit regardless of tray preference");
            }
            Check(fake.Disposed, "LIFE-01 supervisor disposal terminates owned host");
        }
        private static void Key(PreviewForm form, Keys key)
        { typeof(Control).GetMethod("OnKeyDown", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(form, new object[] { new KeyEventArgs(key) }); }
        private static void TestPreviewKeys()
        {
            var commands = new List<string>(); int hidden = 0;
            using (var form = new PreviewForm(delegate(string action) { commands.Add(action); }, SystemIcons.Application))
            {
                IntPtr handle = form.Handle; form.HiddenRequested += delegate { hidden++; };
                form.StartPosition = FormStartPosition.Manual; form.Location = new Point(-20000, -20000); form.Opacity = 0; form.ShowInTaskbar = false; form.Show(); Application.DoEvents();
                Check(form.ImeMode == ImeMode.Disable && form.Canvas.ImeMode == ImeMode.Disable, "WIN-03 preview shortcuts are not text input for IME");
                form.SetMode("fullscreen"); Check(form.FormBorderStyle == FormBorderStyle.None && form.Mode == "fullscreen", "WIN-03 enter fullscreen");
                Key(form, Keys.Escape); Check(form.Mode == "normal" && form.FormBorderStyle == FormBorderStyle.Sizable && hidden == 0, "WIN-03 Escape restores window instead of quitting");
                Key(form, Keys.Escape); Check(hidden == 1 && !commands.Contains("quit"), "WIN-03 Escape in normal view only hides preview");
                Key(form, Keys.Q); Check(commands.Contains("quit"), "WIN-03 Q retains explicit full exit");
                form.WindowState = FormWindowState.Maximized; form.WindowState = FormWindowState.Minimized; form.RestoreFromMinimized();
                Check(form.WindowState == FormWindowState.Maximized, "WIN-02 restore from minimized preserves maximized state");
                foreach (Keys key in new Keys[] { Keys.L, Keys.S, Keys.R, Keys.M, Keys.C }) Key(form, key);
                Check(commands.Contains("toggle_lock") && commands.Contains("start") && commands.Contains("refresh") && commands.Contains("swap") && commands.Contains("reselect"), "REG-01 native preview keeps the other shortcuts");
            }
        }
        [DllImport("user32.dll")] private static extern int GetGuiResources(IntPtr process, int kind);
        private static void TestViewResources()
        {
            using (var process = Process.GetCurrentProcess())
            using (var form = new PreviewForm(delegate { }, SystemIcons.Application))
            {
                form.StartPosition = FormStartPosition.Manual; form.Location = new Point(-20000, -20000); form.Opacity = 0; form.ShowInTaskbar = false;
                form.Show(); form.ReceiveFrame(new Bitmap(320, 180)); form.Hide(); Application.DoEvents();
                GC.Collect(); GC.WaitForPendingFinalizers(); int before = GetGuiResources(process.Handle, 0);
                for (int i = 0; i < 20; i++) { form.Show(); form.ReceiveFrame(new Bitmap(320, 180)); Application.DoEvents(); form.Canvas.Clear("fixture"); form.Hide(); }
                Application.DoEvents(); GC.Collect(); GC.WaitForPendingFinalizers(); int after = GetGuiResources(process.Handle, 0);
                Check(after <= before + 8, "PERF-02 twenty native view/frame cycles have bounded GDI objects");
            }
        }
        private static void SaveLayout(Form form, string path, float scale)
        {
            form.AutoScaleMode = AutoScaleMode.None;
            var fonts = new Dictionary<Control, Font>(); CaptureFonts(form, fonts);
            form.Scale(new SizeF(scale, scale));
            foreach (var pair in fonts) pair.Key.Font = new Font(pair.Value.FontFamily, pair.Value.Size * scale, pair.Value.Style);
            // WinForms does not paint children of an invisible, uncreated form.
            // Materialize only our own test components offscreen, with no input.
            form.StartPosition = FormStartPosition.Manual; form.Location = new Point(-20000, -20000);
            form.ShowInTaskbar = false; form.Opacity = 0; form.Show(); Application.DoEvents(); form.PerformLayout();
            using (var bitmap = new Bitmap(form.Width, form.Height))
            {
                form.DrawToBitmap(bitmap, new Rectangle(0, 0, bitmap.Width, bitmap.Height)); bitmap.Save(path, ImageFormat.Png);
                var colors = new HashSet<int>();
                for (int y = 50; y < bitmap.Height - 10; y += 7) for (int x = 10; x < bitmap.Width - 10; x += 7) colors.Add(bitmap.GetPixel(x, y).ToArgb());
                Check(colors.Count > 8, "UI-04 content actually rendered " + Path.GetFileName(path));
            }
            Check(form.ClientSize.Width >= 400 * scale, "UI-04 layout width " + Path.GetFileName(path));
            CheckCombos(form, Path.GetFileName(path));
            layouts.Add(new { name = Path.GetFileName(path), client_width = form.ClientSize.Width, client_height = form.ClientSize.Height,
                root_preferred_height = form.Controls[0].PreferredSize.Height, root_actual_height = form.Controls[0].Height,
                vertical_scroll = form.VerticalScroll.Visible, root_scroll = ((ScrollableControl)form.Controls[0]).VerticalScroll.Visible });
            if (Path.GetFileName(path) == "panel-100.png") Check(!((ScrollableControl)form.Controls[0]).VerticalScroll.Visible, "UI-01 main panel has no unnecessary default scrollbar");
            if (form is ControlPanel)
            {
                Check(form.ClientSize.Height <= form.Controls[0].PreferredSize.Height + 24, "UI-01 compact default panel " + Path.GetFileName(path));
                Check(form.ClientSize.Height >= form.Controls[0].PreferredSize.Height, "UI-04 compact panel keeps all content " + Path.GetFileName(path));
            }
        }
        private static void CheckCombos(Control parent, string name)
        {
            foreach (Control control in parent.Controls)
            {
                var combo = control as ComboBox;
                if (combo != null) Check(combo.ItemHeight >= combo.Font.Height + 4, "UI-04 combo text height " + name);
                CheckCombos(control, name);
            }
        }
        private static void CaptureFonts(Control control, Dictionary<Control, Font> fonts)
        { fonts[control] = control.Font; foreach (Control child in control.Controls) CaptureFonts(child, fonts); }
        private static void TestLayouts(string output)
        {
            string directory = Path.Combine(output, "layouts"); Directory.CreateDirectory(directory);
            foreach (float scale in new float[] { 1, 1.25F, 1.5F, 2 })
            {
                int percent = (int)(scale * 100);
                using (var panel = new ControlPanel(delegate { }, delegate { }, delegate { }, delegate { }, SystemIcons.Application))
                {
                    panel.RefreshStatus(new AppStatus(), true, false); SaveLayout(panel, Path.Combine(directory, "panel-" + percent + ".png"), scale);
                    Check(panel.Targets.Items.Count == 1 && !panel.Targets.Enabled && panel.Targets.Text.Contains("尚未找到"), "UI-02 empty PPT placeholder " + percent);
                }
                for (int page = 0; page < 3; page++)
                using (var dialog = new SettingsDialog(new UiPreferences(output), new AppStatus(), true, delegate { return true; }, delegate { }, delegate { }, delegate { }, delegate { }, SystemIcons.Application))
                { dialog.ShowPage(page); SaveLayout(dialog, Path.Combine(directory, "settings-" + page + "-" + percent + ".png"), scale); }
                using (var close = new CloseChoiceDialog(SystemIcons.Application)) SaveLayout(close, Path.Combine(directory, "close-" + percent + ".png"), scale);
            }
        }
    }
}
