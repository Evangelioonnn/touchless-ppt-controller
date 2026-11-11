using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;

namespace TouchlessPPTControllerLauncher
{
    internal static class DiagnosticsUi
    {
        public static void OpenLogs()
        {
            string directory = Path.Combine(UiPreferences.DataDirectory(), "logs");
            Directory.CreateDirectory(directory); Process.Start(new ProcessStartInfo(directory) { UseShellExecute = true });
        }
        public static void Export(IWin32Window owner)
        {
            using (var dialog = new SaveFileDialog { Filter = "诊断文本 (*.txt)|*.txt", FileName = "Touchless-Diagnostics.txt", OverwritePrompt = true })
            {
                if (dialog.ShowDialog(owner) != DialogResult.OK) return;
                string directory = UiPreferences.DataDirectory();
                var report = new StringBuilder("Touchless PPT Controller " + Application.ProductVersion + "\r\n分享前请检查。软件不会自动上传。\r\n");
                var paths = new List<string>();
                foreach (string name in new string[] { "settings.json", "ui-settings.json", "last-startup.json" }) if (File.Exists(Path.Combine(directory, name))) paths.Add(Path.Combine(directory, name));
                if (Directory.Exists(Path.Combine(directory, "logs"))) foreach (string path in Directory.GetFiles(Path.Combine(directory, "logs")))
                {
                    string name = Path.GetFileName(path);
                    if ((name.StartsWith("controller.log") || name.StartsWith("launcher-stderr.log")) && new FileInfo(path).Length <= 4 * 1024 * 1024) paths.Add(path);
                }
                foreach (string path in paths)
                {
                    string content = File.ReadAllText(path, Encoding.UTF8);
                    foreach (string personal in new string[] { directory, AppDomain.CurrentDomain.BaseDirectory, Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) })
                        if (!String.IsNullOrEmpty(personal)) content = Regex.Replace(content, Regex.Escape(personal), "<LOCAL_PATH>", RegexOptions.IgnoreCase);
                    content = Regex.Replace(content, @"(?i)[A-Z]:\\[^\r\n""<>]+", "<PATH>");
                    report.AppendLine("\r\n--- " + Path.GetFileName(path) + " ---\r\n" + content);
                }
                File.WriteAllText(dialog.FileName, report.ToString(), Encoding.UTF8);
                MessageBox.Show(owner, "已导出脱敏文本。分享前仍请检查；没有自动上传。", "诊断导出", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        }
    }
}
