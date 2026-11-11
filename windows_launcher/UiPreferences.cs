using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace TouchlessPPTControllerLauncher
{
    internal sealed class WindowPlacement
    {
        public int Left, Top, Width, Height;
        public bool Maximized;
        public void Capture(Form form)
        {
            if (form.WindowState == FormWindowState.Minimized) return;
            Rectangle bounds = form.WindowState == FormWindowState.Normal ? form.Bounds : form.RestoreBounds;
            float scale = form.DeviceDpi / 96F;
            Left = (int)(bounds.Left / scale); Top = (int)(bounds.Top / scale);
            Width = (int)(bounds.Width / scale); Height = (int)(bounds.Height / scale);
            Maximized = form.WindowState == FormWindowState.Maximized;
        }
        public void Restore(Form form)
        {
            if (Width < 300 || Height < 200 || Width > 5000 || Height > 4000) return;
            float scale = form.DeviceDpi / 96F;
            Rectangle bounds = new Rectangle((int)(Left * scale), (int)(Top * scale), (int)(Width * scale), (int)(Height * scale));
            bool reachable = false;
            foreach (Screen screen in Screen.AllScreens) if (Rectangle.Intersect(screen.WorkingArea, bounds).Width >= 100 && Rectangle.Intersect(screen.WorkingArea, bounds).Height >= 80) reachable = true;
            if (reachable) { form.StartPosition = FormStartPosition.Manual; form.Bounds = bounds; }
            if (Maximized) form.WindowState = FormWindowState.Maximized;
        }
    }

    internal sealed class UiPreferences
    {
        public int SchemaVersion = 1;
        public string CloseAction = "ask";
        public bool ShowPreviewOnStart = true;
        public string PreviewMode = "normal";
        public WindowPlacement Panel = new WindowPlacement();
        public WindowPlacement Preview = new WindowPlacement();
        public bool BackgroundTipShown;
        public string Warning = "";
        public readonly string DirectoryPath;
        public string FilePath { get { return Path.Combine(DirectoryPath, "ui-settings.json"); } }
        public UiPreferences(string directory) { DirectoryPath = directory; }
        public static string DataDirectory()
        {
            string value = Environment.GetEnvironmentVariable("TOUCHLESS_PPT_DATA_DIR");
            return String.IsNullOrEmpty(value) ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TouchlessPPTController") : Path.GetFullPath(value);
        }
        public static UiPreferences Load(string directory)
        {
            var result = new UiPreferences(directory);
            if (!File.Exists(result.FilePath)) return result;
            try
            {
                var data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(result.FilePath));
                if (data == null || !data.ContainsKey("schema_version") || !(data["schema_version"] is int) || (int)data["schema_version"] != 1) throw new FormatException("不支持的界面设置版本");
                result.CloseAction = ReadChoice(data, "close_action", new string[] { "ask", "tray", "exit" }, "ask");
                result.PreviewMode = ReadChoice(data, "preview_mode", new string[] { "normal", "overlay", "fullscreen" }, "normal");
                result.ShowPreviewOnStart = ReadBool(data, "show_preview", true);
                result.BackgroundTipShown = ReadBool(data, "background_tip_shown", false);
                result.Panel = ReadPlacement(data, "panel"); result.Preview = ReadPlacement(data, "preview");
            }
            catch (Exception error)
            {
                result = new UiPreferences(directory); result.Warning = "界面设置无法读取，已恢复默认：" + error.Message;
                try { File.Move(result.FilePath, Path.Combine(directory, "ui-settings.broken-" + DateTime.UtcNow.Ticks + ".json")); } catch { }
            }
            return result;
        }
        private static bool ReadBool(Dictionary<string, object> data, string key, bool fallback)
        { if (!data.ContainsKey(key)) return fallback; if (!(data[key] is bool)) throw new FormatException("设置类型错误：" + key); return (bool)data[key]; }
        private static string ReadChoice(Dictionary<string, object> data, string key, string[] choices, string fallback)
        { if (!data.ContainsKey(key)) return fallback; string value = data[key] as string; if (Array.IndexOf(choices, value) < 0) throw new FormatException("无效设置：" + key); return value; }
        private static WindowPlacement ReadPlacement(Dictionary<string, object> data, string key)
        {
            var result = new WindowPlacement();
            if (!data.ContainsKey(key)) return result;
            var value = data[key] as Dictionary<string, object>;
            if (value == null) throw new FormatException("窗口位置格式错误");
            string[] keys = new string[] { "left", "top", "width", "height" }; int[] numbers = new int[4];
            for (int i = 0; i < keys.Length; i++) { if (!value.ContainsKey(keys[i]) || !(value[keys[i]] is int)) throw new FormatException("窗口位置类型错误"); numbers[i] = (int)value[keys[i]]; }
            result.Left = numbers[0]; result.Top = numbers[1]; result.Width = numbers[2]; result.Height = numbers[3]; result.Maximized = ReadBool(value, "maximized", false);
            if (Math.Abs((long)result.Left) > 100000 || Math.Abs((long)result.Top) > 100000 || result.Width < 0 || result.Width > 5000 || result.Height < 0 || result.Height > 4000) throw new FormatException("窗口位置越界");
            return result;
        }
        private static object Placement(WindowPlacement p) { return new { left = p.Left, top = p.Top, width = p.Width, height = p.Height, maximized = p.Maximized }; }
        public bool Save()
        {
            string temporary = null;
            try
            {
                Directory.CreateDirectory(DirectoryPath);
                temporary = Path.Combine(DirectoryPath, "ui-settings-" + Guid.NewGuid().ToString("N") + ".tmp");
                var data = new { schema_version = SchemaVersion, close_action = CloseAction, show_preview = ShowPreviewOnStart, preview_mode = PreviewMode,
                    background_tip_shown = BackgroundTipShown, panel = Placement(Panel), preview = Placement(Preview) };
                File.WriteAllText(temporary, new JavaScriptSerializer().Serialize(data));
                if (File.Exists(FilePath)) File.Replace(temporary, FilePath, null); else File.Move(temporary, FilePath);
                return true;
            }
            catch (Exception error) { Warning = "界面设置保存失败：" + error.Message; return false; }
            finally { if (temporary != null && File.Exists(temporary)) { try { File.Delete(temporary); } catch { } } }
        }
    }
}
