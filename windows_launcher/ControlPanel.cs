using System;
using System.Drawing;
using System.Windows.Forms;

namespace TouchlessPPTControllerLauncher
{
    internal sealed class ControlPanel : Form
    {
        private readonly Label state = Theme.Label("控制已锁定", 12, true);
        private readonly Label feedback = Theme.Label("正在准备本地识别…");
        private readonly StatusTile camera = new StatusTile("摄像头");
        private readonly StatusTile person = new StatusTile("人物识别");
        private readonly StatusTile ppt = new StatusTile("PowerPoint");
        internal readonly ComboBox Targets = Theme.Combo();
        internal readonly RoundedButton LockButton, PreviewButton;
        private readonly TableLayoutPanel root;
        private bool updating;
        internal bool CompactOnFirstShow = true;
        public bool AllowExit;
        public event Action CloseRequested;
        public ControlPanel(Action<string> action, Action<string> target, Action settings, Action togglePreview, Icon icon)
        {
            Theme.Style(this); Text = "Touchless PPT Controller"; Icon = icon;
            ClientSize = new Size(660, 530); MinimumSize = new Size(610, 465);
            root = Theme.Stack(); root.Dock = DockStyle.Fill; root.AutoSize = false; root.AutoScroll = true; root.Padding = new Padding(24, 21, 24, 18);
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            var header = new TableLayoutPanel { ColumnCount = 2, Dock = DockStyle.Fill, AutoSize = true, Margin = new Padding(0, 0, 0, 5) };
            header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); header.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            header.Controls.Add(Theme.Label("无接触 PPT 控制器", 17, true), 0, 0);
            header.Controls.Add(Theme.Button("设置", settings), 1, 0);
            root.Controls.Add(header); state.Margin = new Padding(0, 3, 0, 10); root.Controls.Add(state);
            var tiles = new TableLayoutPanel { ColumnCount = 3, Dock = DockStyle.Fill, Height = 88, Margin = new Padding(0, 0, 0, 12) };
            for (int i = 0; i < 3; i++) tiles.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F / 3));
            ppt.Margin = Padding.Empty; tiles.Controls.Add(camera, 0, 0); tiles.Controls.Add(person, 1, 0); tiles.Controls.Add(ppt, 2, 0); root.Controls.Add(tiles);
            root.Controls.Add(Theme.Label("目标文稿 / 放映", 10, true));
            var targetRow = new TableLayoutPanel { ColumnCount = 2, AutoSize = true, Dock = DockStyle.Fill, Margin = new Padding(0, 0, 0, 12) };
            targetRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); targetRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            targetRow.Controls.Add(Targets, 0, 0);
            var refresh = Theme.Button("刷新 PPT", delegate { action("refresh"); }); refresh.Margin = new Padding(10, 0, 0, 0); targetRow.Controls.Add(refresh, 1, 0); root.Controls.Add(targetRow);
            Targets.SelectedIndexChanged += delegate { var selected = Targets.SelectedItem as TargetItem; if (!updating && selected != null && selected.Id != "") target(selected.Id); };
            var actions = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, Margin = new Padding(0, 0, 0, 10), WrapContents = true };
            LockButton = Theme.Button("解锁控制", delegate { action("toggle_lock"); }, true); LockButton.MinimumSize = new Size(145, 42);
            actions.Controls.Add(LockButton); actions.Controls.Add(Theme.Button("开始放映", delegate { action("start"); }));
            PreviewButton = Theme.Button("收起预览", togglePreview); PreviewButton.MinimumSize = new Size(130, 42); actions.Controls.Add(PreviewButton); root.Controls.Add(actions);
            var message = Theme.Stack(); message.BackColor = Theme.Surface; message.Padding = new Padding(13, 10, 13, 10); message.Margin = new Padding(0, 0, 0, 10);
            var caption = Theme.Label("操作反馈", 9); caption.ForeColor = Theme.Muted; message.Controls.Add(caption); feedback.ForeColor = Theme.Text; feedback.MaximumSize = new Size(570, 0); message.Controls.Add(feedback); root.Controls.Add(message);
            var footer = Theme.Label("单人授课 · 离开后回来自动继续 · 可收起到系统托盘", 9); footer.ForeColor = Theme.Muted; root.Controls.Add(footer);
            var version = Theme.Label("v" + Application.ProductVersion, 8); version.ForeColor = Theme.Muted; root.Controls.Add(version);
            Controls.Add(root);
            FormClosing += delegate(object sender, FormClosingEventArgs e)
            {
                if (AllowExit || e.CloseReason == CloseReason.WindowsShutDown || e.CloseReason == CloseReason.TaskManagerClosing) return;
                e.Cancel = true; if (CloseRequested != null) CloseRequested();
            };
        }
        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            // Measure after WinForms has applied this screen's DPI and fonts.
            // Do not replace a window size that the user deliberately saved.
            if (!CompactOnFirstShow || WindowState != FormWindowState.Normal) return;
            int chromeHeight = Height - ClientSize.Height;
            int availableHeight = Screen.FromControl(this).WorkingArea.Height - chromeHeight;
            for (int i = 0; i < 3; i++)
            {
                PerformLayout(); root.PerformLayout();
                int contentHeight = Math.Max(root.PreferredSize.Height, root.GetPreferredSize(new Size(root.ClientSize.Width, 0)).Height);
                int desiredHeight = Math.Max(260, Math.Min(contentHeight + 2, availableHeight));
                MinimumSize = new Size(MinimumSize.Width, Math.Min(MinimumSize.Height, desiredHeight + chromeHeight));
                ClientSize = new Size(ClientSize.Width, desiredHeight);
            }
        }
        public void RefreshStatus(AppStatus model, bool previewVisible, bool observeOnly)
        {
            state.Text = observeOnly ? "诊断观察模式 · 不发送 PPT 指令" : model.Locking ? "正在锁定 · 等待在途命令结束" : model.Locked ? "控制已锁定" : "控制已启用";
            state.ForeColor = model.Locked ? Theme.Amber : Theme.Green;
            LockButton.Text = model.Locked ? "解锁控制" : "锁定控制"; LockButton.Invalidate();
            PreviewButton.Text = previewVisible ? "收起预览" : "显示预览"; PreviewButton.Invalidate();
            camera.UpdateText(model.CameraState == "ready" ? "已连接" : model.CameraState == "loading" ? "正在准备" : model.CameraState == "stopped" ? "后台已停止" : "等待连接 / 重试", model.CameraState == "ready" ? Theme.Green : Theme.Muted);
            person.UpdateText(model.PersonText, model.PresenterVisible ? Theme.Green : Theme.Muted);
            ppt.UpdateText(model.Connected ? "已连接目标" : "尚未连接", model.Connected ? Theme.Green : Theme.Muted);
            feedback.Text = model.LastOperation;
            bool same = Targets.Items.Count == Math.Max(1, model.Targets.Count);
            if (same && model.Targets.Count > 0) for (int i = 0; i < model.Targets.Count; i++)
            { var item = Targets.Items[i] as TargetItem; if (item == null || item.Id != model.Targets[i].Id || item.Title != model.Targets[i].Title) same = false; }
            if (same && model.Targets.Count == 0) same = (Targets.Items[0] as TargetItem) != null && ((TargetItem)Targets.Items[0]).Id == "";
            updating = true;
            try
            {
                if (!same)
                {
                    Targets.Items.Clear();
                    if (model.Targets.Count == 0) Targets.Items.Add(new TargetItem { Id = "", Title = "尚未找到文稿，请先打开 PowerPoint" });
                    else foreach (var item in model.Targets) Targets.Items.Add(item);
                }
                int selected = model.Targets.Count == 0 ? 0 : -1;
                for (int i = 0; i < Targets.Items.Count; i++) if (((TargetItem)Targets.Items[i]).Id == model.TargetId && model.TargetId != "") selected = i;
                if (Targets.SelectedIndex != selected) Targets.SelectedIndex = selected;
                Targets.Enabled = model.Targets.Count > 0;
            }
            finally { updating = false; }
        }
    }
}
