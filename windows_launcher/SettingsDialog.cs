using System;
using System.Collections.Generic;
using System.Drawing;
using System.Windows.Forms;

namespace TouchlessPPTControllerLauncher
{
    internal sealed class Choice
    {
        public readonly string Key, Text;
        public Choice(string key, string text) { Key = key; Text = text; }
        public override string ToString() { return Text; }
    }
    internal sealed class SettingsDialog : Form
    {
        private readonly UiPreferences preferences;
        private readonly Func<Dictionary<string, object>, bool> apply;
        private readonly Dictionary<string, object> changes = new Dictionary<string, object>();
        private readonly ComboBox closeAction = Theme.Combo(), previewMode = Theme.Combo();
        private readonly CheckBox startup = new CheckBox { Text = "启动时显示摄像头预览", AutoSize = true };
        private readonly Panel body = new Panel { Dock = DockStyle.Fill, AutoScroll = true };
        private readonly Panel[] pages = new Panel[3];
        internal readonly RoundedButton[] Navigation = new RoundedButton[3];
        public SettingsDialog(UiPreferences prefs, AppStatus model, bool frozen, Func<Dictionary<string, object>, bool> save,
                              Action<string> action, Action restart, Action logs, Action export, Icon icon)
        {
            preferences = prefs; apply = save; Theme.Style(this); Icon = icon; Text = "设置 · Touchless PPT Controller";
            ClientSize = new Size(650, 540); MinimumSize = new Size(600, 540); ShowInTaskbar = false;
            var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3, Padding = new Padding(22), BackColor = Theme.Background };
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize)); root.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            var navigation = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, Padding = new Padding(0, 0, 0, 14), WrapContents = false };
            string[] names = new string[] { "常规", "设备与识别", "高级与诊断" };
            for (int i = 0; i < names.Length; i++)
            {
                int index = i; Navigation[i] = Theme.Button(names[i], delegate { ShowPage(index); }); navigation.Controls.Add(Navigation[i]);
                pages[i] = new Panel { Dock = DockStyle.Fill, AutoScroll = true, BackColor = Theme.Background }; body.Controls.Add(pages[i]);
            }
            root.Controls.Add(navigation, 0, 0); root.Controls.Add(body, 0, 1);
            var buttons = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, FlowDirection = FlowDirection.RightToLeft, Padding = new Padding(0, 14, 0, 0), WrapContents = false };
            var saveButton = Theme.Button("应用并保存", Save, true); var cancel = Theme.Button("取消", delegate { DialogResult = DialogResult.Cancel; Close(); });
            buttons.Controls.Add(saveButton); buttons.Controls.Add(cancel); root.Controls.Add(buttons, 0, 2); Controls.Add(root);
            AcceptButton = saveButton; CancelButton = cancel;

            var general = Page(pages[0], "关闭和预览");
            Fill(closeAction, new Choice[] { new Choice("ask", "每次询问（首次默认）"), new Choice("tray", "收起到系统托盘，继续运行"), new Choice("exit", "完全退出程序") }, prefs.CloseAction);
            Row(general, "关闭控制面板时", closeAction);
            startup.Checked = prefs.ShowPreviewOnStart; startup.ForeColor = Theme.Text; startup.Margin = new Padding(0, 15, 0, 15); general.Controls.Add(startup);
            Fill(previewMode, new Choice[] { new Choice("normal", "普通窗口"), new Choice("overlay", "置顶小窗"), new Choice("fullscreen", "全屏") }, prefs.PreviewMode);
            Row(general, "预览显示方式", previewMode);
            Hint(general, "关闭预览只收起画面。两个窗口都收起后，摄像头和识别仍会继续工作，可从右下角系统托盘恢复或完全退出。");
            Hint(general, "最小化仍保留在任务栏。软件不会自动开机启动，也不会安装系统服务。");

            var devices = Page(pages[1], "设备与识别");
            var camera = new NumericUpDown { Minimum = 0, Maximum = 15, BackColor = Theme.Input, ForeColor = Theme.Text, BorderStyle = BorderStyle.FixedSingle, Width = 120 };
            int cameraNumber; int.TryParse(AppStatus.Value(model.Settings, "camera_index", "0"), out cameraNumber); camera.Value = Math.Max(0, Math.Min(15, cameraNumber));
            Row(devices, "摄像头编号", camera); camera.ValueChanged += delegate { changes["camera_index"] = (int)camera.Value; };
            var swap = Check(devices, "交换左右手映射", Bool(model.Settings, "swap_hands", true)); swap.CheckedChanged += delegate { changes["swap_hands"] = swap.Checked; };
            var glow = Check(devices, "骨架发光效果（仅预览显示时绘制）", Bool(model.Settings, "glow", true)); glow.CheckedChanged += delegate { changes["glow"] = glow.Checked; };
            var backend = Theme.Combo();
            var backendChoices = frozen ? new Choice[] { new Choice("onnx", "ONNX · 轻量运行") } : new Choice[] { new Choice("torch", "PyTorch · 开发兼容"), new Choice("onnx", "ONNX · 轻量运行") };
            string selectedBackend = AppStatus.Value(model.Settings, "backend", frozen ? "onnx" : "torch");
            Fill(backend, backendChoices, selectedBackend); if (backend.SelectedIndex < 0) { backend.SelectedIndex = 0; changes["backend"] = ((Choice)backend.SelectedItem).Key; }
            Row(devices, "推理方式", backend); backend.SelectedIndexChanged += delegate { if (backend.SelectedItem != null) changes["backend"] = ((Choice)backend.SelectedItem).Key; };
            var device = Theme.Combo();
            Fill(device, frozen ? new Choice[] { new Choice("auto", "自动选择（此包使用 CPU）"), new Choice("cpu", "CPU · 兼容模式") }
                : new Choice[] { new Choice("auto", "自动选择"), new Choice("cpu", "CPU · 兼容模式"), new Choice("cuda", "NVIDIA GPU（不可用会降级）") }, AppStatus.Value(model.Settings, "device", "auto"));
            if (device.SelectedIndex < 0) { device.SelectedIndex = 0; changes["device"] = "auto"; }
            Row(devices, "运行设备", device); device.SelectedIndexChanged += delegate { if (device.SelectedItem != null) changes["device"] = ((Choice)device.SelectedItem).Key; };
            Hint(devices, frozen ? "此便携包不包含 PyTorch / CUDA，界面仅提供包内可用选项。" : "切换设备可能重新加载模型；不会改变你的手动锁定选择。");

            var advanced = Page(pages[2], "高级与诊断");
            var ppt = Theme.Combo(); Fill(ppt, new Choice[] { new Choice("com", "COM · 推荐控制方式"), new Choice("keys", "定向按键 · 尽力兼容") }, AppStatus.Value(model.Settings, "ppt_backend", "com"));
            Row(advanced, "PPT 控制方式", ppt); ppt.SelectedIndexChanged += delegate { if (ppt.SelectedItem != null) changes["ppt_backend"] = ((Choice)ppt.SelectedItem).Key; };
            Hint(advanced, "定向按键只表示消息已发送，不保证 PPT 已执行；结果未知时不会自动重发。");
            var repair = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Top, WrapContents = true, Margin = new Padding(0, 8, 0, 12) };
            repair.Controls.Add(Theme.Button("重试设备 / 模型", delegate { action("retry"); })); repair.Controls.Add(Theme.Button("重启后台", restart)); repair.Controls.Add(Theme.Button("刷新人物", delegate { action("reselect"); })); advanced.Controls.Add(repair);
            var diagnostic = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Top, WrapContents = true, Margin = new Padding(0, 0, 0, 12) };
            diagnostic.Controls.Add(Theme.Button("打开日志", logs)); diagnostic.Controls.Add(Theme.Button("导出诊断文本", export)); advanced.Controls.Add(diagnostic);
            var text = new TextBox { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, Height = 100, Dock = DockStyle.Top,
                BackColor = Theme.Input, ForeColor = Theme.Muted, BorderStyle = BorderStyle.FixedSingle, Text = model.TechnicalText, Font = Theme.Font(9), Margin = new Padding(0, 0, 0, 8) }; advanced.Controls.Add(text);
            Hint(advanced, "诊断不包含摄像头图片，不会自动上传。分享导出文本前仍请检查。");
            ShowPage(0);
        }
        private static bool Bool(Dictionary<string, object> values, string key, bool fallback) { return values.ContainsKey(key) && values[key] is bool ? (bool)values[key] : fallback; }
        private static void Fill(ComboBox combo, Choice[] choices, string value)
        { foreach (var choice in choices) combo.Items.Add(choice); for (int i = 0; i < combo.Items.Count; i++) if (((Choice)combo.Items[i]).Key == value) combo.SelectedIndex = i; }
        private static TableLayoutPanel Page(Panel parent, string title)
        { var stack = Theme.Stack(); stack.Padding = new Padding(0, 4, 16, 4); stack.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); stack.Controls.Add(Theme.Label(title, 14, true)); parent.Controls.Add(stack); return stack; }
        private static void Row(TableLayoutPanel stack, string title, Control field)
        {
            var row = new TableLayoutPanel { ColumnCount = 2, AutoSize = true, Dock = DockStyle.Top, Margin = new Padding(0, 11, 0, 7) };
            row.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 155)); row.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            var label = Theme.Label(title); label.Margin = new Padding(0, 7, 12, 0); row.Controls.Add(label, 0, 0); field.Dock = DockStyle.Fill; row.Controls.Add(field, 1, 0); stack.Controls.Add(row);
        }
        private static CheckBox Check(TableLayoutPanel stack, string title, bool value)
        { var check = new CheckBox { Text = title, Checked = value, AutoSize = true, ForeColor = Theme.Text, Margin = new Padding(0, 10, 0, 7) }; stack.Controls.Add(check); return check; }
        private static void Hint(TableLayoutPanel stack, string text)
        { var label = Theme.Label(text, 9); label.ForeColor = Theme.Muted; label.MaximumSize = new Size(550, 0); label.Margin = new Padding(0, 12, 0, 3); stack.Controls.Add(label); }
        internal void ShowPage(int index)
        {
            for (int i = 0; i < pages.Length; i++) { pages[i].Visible = i == index; Navigation[i].Primary = i == index; Navigation[i].Invalidate(); }
            pages[index].BringToFront();
        }
        private void Save()
        {
            preferences.CloseAction = ((Choice)closeAction.SelectedItem).Key; preferences.PreviewMode = ((Choice)previewMode.SelectedItem).Key; preferences.ShowPreviewOnStart = startup.Checked;
            if (!apply(changes)) return;
            DialogResult = DialogResult.OK; Close();
        }
    }

    internal sealed class CloseChoiceDialog : Form
    {
        private readonly CheckBox remember = new CheckBox { Text = "记住我的选择（可在设置中修改）", Checked = true, AutoSize = true };
        public bool RememberChoice { get { return remember.Checked; } }
        public CloseChoiceDialog(Icon icon)
        {
            Theme.Style(this); Icon = icon; Text = "关闭控制面板"; ClientSize = new Size(545, 245); MinimumSize = Size; MaximizeBox = false; MinimizeBox = false; ShowInTaskbar = false;
            var root = Theme.Stack(); root.Dock = DockStyle.Fill; root.Padding = new Padding(24);
            root.Controls.Add(Theme.Label("关闭窗口后，要继续在后台运行吗？", 13, true));
            var hint = Theme.Label("收起到右下角系统托盘后，摄像头和识别仍会运行，预览窗口保持原样。可从托盘恢复或完全退出。", 10);
            hint.MaximumSize = new Size(495, 0); hint.ForeColor = Theme.Muted; hint.Margin = new Padding(0, 12, 0, 15); root.Controls.Add(hint);
            remember.ForeColor = Theme.Text; remember.Margin = new Padding(0, 0, 0, 18); root.Controls.Add(remember);
            var buttons = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Top, WrapContents = false };
            var tray = Theme.Button("收起到托盘", delegate { DialogResult = DialogResult.Yes; Close(); }, true);
            var quit = Theme.Button("完全退出", delegate { DialogResult = DialogResult.No; Close(); });
            var cancel = Theme.Button("取消", delegate { DialogResult = DialogResult.Cancel; Close(); });
            buttons.Controls.Add(tray); buttons.Controls.Add(quit); buttons.Controls.Add(cancel); root.Controls.Add(buttons); Controls.Add(root); AcceptButton = tray; CancelButton = cancel;
        }
    }
}
