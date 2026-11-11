using System;
using System.Drawing;
using System.Windows.Forms;

namespace TouchlessPPTControllerLauncher
{
    internal sealed class FrameCanvas : Control
    {
        private Bitmap frame;
        public string Notice = "正在等待摄像头画面…";
        public FrameCanvas() { DoubleBuffered = true; Dock = DockStyle.Fill; BackColor = Theme.Background; ImeMode = ImeMode.Disable; }
        public void SetFrame(Bitmap bitmap) { Bitmap previous = frame; frame = bitmap; if (previous != null) previous.Dispose(); Notice = ""; Invalidate(); }
        public void Clear(string text) { if (frame != null) { frame.Dispose(); frame = null; } Notice = text; Invalidate(); }
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.Clear(Theme.Background);
            if (frame != null)
            {
                float scale = Math.Min(Width / (float)frame.Width, Height / (float)frame.Height);
                int width = (int)(frame.Width * scale), height = (int)(frame.Height * scale);
                e.Graphics.DrawImage(frame, new Rectangle((Width - width) / 2, (Height - height) / 2, width, height));
            }
            if (Notice != "") TextRenderer.DrawText(e.Graphics, Notice, Font, ClientRectangle, Theme.Muted,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.WordBreak);
        }
        protected override void Dispose(bool disposing) { if (disposing && frame != null) { frame.Dispose(); frame = null; } base.Dispose(disposing); }
    }

    internal sealed class PreviewForm : Form
    {
        internal readonly FrameCanvas Canvas = new FrameCanvas();
        private readonly RoundedButton restore;
        private Rectangle normalBounds;
        private FormWindowState normalState;
        private FormWindowState lastNonMinimizedState = FormWindowState.Normal;
        private string mode = "normal";
        private readonly Action<string> action;
        public bool AllowExit;
        public event Action HiddenRequested;
        public event Action VisibilityStateChanged;
        public event Action<string> ModeChanged;
        public string Mode { get { return mode; } }
        public bool IsDrawable { get { return Visible && WindowState != FormWindowState.Minimized; } }
        public double LastFrameAt;
        public PreviewForm(Action<string> command, Icon icon)
        {
            action = command; Theme.Style(this); Icon = icon; Text = "实时预览 · Touchless PPT Controller";
            ClientSize = new Size(960, 590); MinimumSize = new Size(480, 320); KeyPreview = true;
            ImeMode = ImeMode.Disable;
            var bar = new FlowLayoutPanel { Dock = DockStyle.Top, Height = 48, Padding = new Padding(10, 5, 10, 5), BackColor = Theme.Surface, WrapContents = false };
            restore = Theme.Button("全屏", delegate { SetMode(mode == "fullscreen" ? "normal" : "fullscreen"); });
            bar.Controls.Add(restore); bar.Controls.Add(Theme.Button("置顶小窗", delegate { SetMode(mode == "overlay" ? "normal" : "overlay"); }));
            bar.Controls.Add(Theme.Button("收起预览", RequestHide));
            Controls.Add(Canvas); Controls.Add(bar);
            KeyDown += OnKey;
            VisibleChanged += delegate { if (VisibilityStateChanged != null) VisibilityStateChanged(); };
            Resize += delegate
            {
                if (VisibilityStateChanged != null) VisibilityStateChanged();
            };
            FormClosing += delegate(object sender, FormClosingEventArgs e)
            {
                if (AllowExit || e.CloseReason == CloseReason.WindowsShutDown || e.CloseReason == CloseReason.TaskManagerClosing) return;
                e.Cancel = true; RequestHide();
            };
        }
        public void RequestHide() { Canvas.Clear("预览已收起"); if (HiddenRequested != null) HiddenRequested(); else Hide(); }
        public void ReceiveFrame(Bitmap bitmap) { Canvas.SetFrame(bitmap); LastFrameAt = PreviewChannel.Now; }
        public void RestoreFromMinimized()
        {
            if (WindowState != FormWindowState.Minimized) return;
            WindowState = lastNonMinimizedState;
            if (mode == "fullscreen") Bounds = Screen.FromControl(this).Bounds;
        }
        protected override void WndProc(ref Message message)
        {
            if (message.Msg == 0x0005 && mode != "fullscreen")
            {
                int sizeState = message.WParam.ToInt32();
                if (sizeState == 0) lastNonMinimizedState = FormWindowState.Normal;
                else if (sizeState == 2) lastNonMinimizedState = FormWindowState.Maximized;
            }
            base.WndProc(ref message);
        }
        protected override bool ProcessCmdKey(ref Message message, Keys keyData)
        {
            Keys key = keyData & Keys.KeyCode;
            if ((keyData & (Keys.Control | Keys.Alt)) == 0 && (key == Keys.Escape || key == Keys.F || key == Keys.O || key == Keys.Q || key == Keys.L || key == Keys.S || key == Keys.R || key == Keys.M || key == Keys.C))
            { OnKey(this, new KeyEventArgs(keyData)); return true; }
            return base.ProcessCmdKey(ref message, keyData);
        }
        public void SetMode(string value)
        {
            if (value != "normal" && value != "overlay" && value != "fullscreen") return;
            if (mode == value) return;
            if (mode == "normal") { normalBounds = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds; normalState = WindowState == FormWindowState.Maximized ? FormWindowState.Maximized : FormWindowState.Normal; }
            if (mode == "fullscreen") { WindowState = FormWindowState.Normal; FormBorderStyle = FormBorderStyle.Sizable; }
            mode = value; TopMost = value == "overlay";
            if (value == "fullscreen") { WindowState = FormWindowState.Normal; FormBorderStyle = FormBorderStyle.None; Bounds = Screen.FromControl(this).Bounds; }
            else if (value == "overlay") { WindowState = FormWindowState.Normal; Size = new Size(560, 370); }
            else if (normalBounds.Width > 0) { Bounds = normalBounds; WindowState = normalState; }
            restore.Text = value == "fullscreen" ? "退出全屏" : "全屏"; restore.Invalidate();
            if (ModeChanged != null) ModeChanged(mode);
        }
        public void CapturePlacement(WindowPlacement placement)
        {
            if (mode == "normal") placement.Capture(this);
            else if (normalBounds.Width > 0)
            {
                float scale = DeviceDpi / 96F;
                placement.Left = (int)(normalBounds.Left / scale); placement.Top = (int)(normalBounds.Top / scale);
                placement.Width = (int)(normalBounds.Width / scale); placement.Height = (int)(normalBounds.Height / scale); placement.Maximized = normalState == FormWindowState.Maximized;
            }
        }
        private void OnKey(object sender, KeyEventArgs e)
        {
            if (e.Control || e.Alt) return;
            if (e.KeyCode == Keys.Escape) { if (mode == "fullscreen") SetMode("normal"); else RequestHide(); }
            else if (e.KeyCode == Keys.F) SetMode(mode == "fullscreen" ? "normal" : "fullscreen");
            else if (e.KeyCode == Keys.O) SetMode(mode == "overlay" ? "normal" : "overlay");
            else
            {
                string command = e.KeyCode == Keys.Q ? "quit" : e.KeyCode == Keys.L ? "toggle_lock" : e.KeyCode == Keys.S ? "start" : e.KeyCode == Keys.R ? "refresh" : e.KeyCode == Keys.M ? "swap" : e.KeyCode == Keys.C ? "reselect" : "";
                if (command == "") return;
                action(command);
            }
            e.Handled = true; e.SuppressKeyPress = true;
        }
    }
}
