using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace TouchlessPPTControllerLauncher
{
    internal static class Theme
    {
        public static readonly Color Background = Color.FromArgb(13, 22, 36);
        public static readonly Color Surface = Color.FromArgb(22, 35, 53);
        public static readonly Color Input = Color.FromArgb(31, 47, 67);
        public static readonly Color Border = Color.FromArgb(48, 66, 88);
        public static readonly Color Text = Color.FromArgb(235, 241, 250);
        public static readonly Color Muted = Color.FromArgb(163, 181, 203);
        public static readonly Color Accent = Color.FromArgb(119, 183, 255);
        public static readonly Color Green = Color.FromArgb(103, 217, 167);
        public static readonly Color Amber = Color.FromArgb(255, 190, 110);
        public static Font Font(float size, bool bold = false) { return new Font("Microsoft YaHei UI", size, bold ? FontStyle.Bold : FontStyle.Regular); }
        [DllImport("dwmapi.dll")] private static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int size);
        [DllImport("uxtheme.dll", CharSet = CharSet.Unicode)] private static extern int SetWindowTheme(IntPtr window, string subApp, string subId);
        public static void Style(Form form)
        {
            form.AutoScaleDimensions = new SizeF(96, 96);
            form.AutoScaleMode = AutoScaleMode.Dpi;
            form.Font = Font(10);
            form.BackColor = Background; form.ForeColor = Text;
            form.StartPosition = FormStartPosition.CenterScreen;
            form.HandleCreated += delegate { try { int dark = 1; DwmSetWindowAttribute(form.Handle, 20, ref dark, 4); } catch { } };
        }
        public static Label Label(string text, float size = 10, bool bold = false)
        {
            return new Label { Text = text, AutoSize = true, ForeColor = Text, Font = Font(size, bold), Margin = new Padding(0, 0, 0, 5) };
        }
        public static RoundedButton Button(string text, Action action, bool primary = false)
        {
            var button = new RoundedButton { Text = text, Primary = primary, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink,
                MinimumSize = new Size(100, 40), Padding = new Padding(15, 8, 15, 8), Margin = new Padding(0, 0, 10, 0) };
            button.Click += delegate { action(); }; return button;
        }
        public static ComboBox Combo()
        {
            var combo = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, FlatStyle = FlatStyle.Flat,
                BackColor = Input, ForeColor = Text, Font = Font(10), Dock = DockStyle.Fill, Margin = new Padding(0, 4, 0, 4), DrawMode = DrawMode.OwnerDrawFixed, ItemHeight = 26 };
            combo.DrawItem += delegate(object sender, DrawItemEventArgs e)
            {
                using (Brush brush = new SolidBrush((e.State & DrawItemState.Selected) != 0 ? Border : Input)) e.Graphics.FillRectangle(brush, e.Bounds);
                string value = e.Index >= 0 && e.Index < combo.Items.Count ? Convert.ToString(combo.Items[e.Index]) : combo.Text;
                TextRenderer.DrawText(e.Graphics, value, combo.Font, Rectangle.Inflate(e.Bounds, -6, 0), Text,
                    TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis);
            };
            combo.FontChanged += delegate { combo.ItemHeight = Math.Max((int)(26 * combo.DeviceDpi / 96F), combo.Font.Height + 10); };
            combo.HandleCreated += delegate { try { SetWindowTheme(combo.Handle, "DarkMode_CFD", null); } catch { } };
            return combo;
        }
        public static GraphicsPath Rounded(Rectangle rectangle, int radius)
        {
            var path = new GraphicsPath(); int diameter = Math.Min(radius * 2, Math.Min(rectangle.Width, rectangle.Height));
            if (diameter < 2) { path.AddRectangle(rectangle); return path; }
            path.AddArc(rectangle.X, rectangle.Y, diameter, diameter, 180, 90);
            path.AddArc(rectangle.Right - diameter, rectangle.Y, diameter, diameter, 270, 90);
            path.AddArc(rectangle.Right - diameter, rectangle.Bottom - diameter, diameter, diameter, 0, 90);
            path.AddArc(rectangle.X, rectangle.Bottom - diameter, diameter, diameter, 90, 90); path.CloseFigure(); return path;
        }
        public static TableLayoutPanel Stack()
        {
            return new TableLayoutPanel { ColumnCount = 1, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink,
                Dock = DockStyle.Top, BackColor = Color.Transparent, Margin = Padding.Empty, Padding = Padding.Empty };
        }
    }

    internal sealed class RoundedButton : Button
    {
        public bool Primary;
        public RoundedButton() { FlatStyle = FlatStyle.Flat; FlatAppearance.BorderSize = 0; Cursor = Cursors.Hand; SetStyle(ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true); }
        protected override void OnPaint(PaintEventArgs e)
        {
            Control ancestor = Parent;
            while (ancestor != null && ancestor.BackColor.A < 255) ancestor = ancestor.Parent;
            e.Graphics.Clear(ancestor == null ? Theme.Background : ancestor.BackColor);
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            Rectangle rect = new Rectangle(1, 1, Math.Max(1, Width - 3), Math.Max(1, Height - 3));
            using (var path = Theme.Rounded(rect, 9))
            {
                Color fill = Primary ? Theme.Accent : Theme.Input;
                if (!Enabled) fill = Theme.Surface;
                using (var brush = new SolidBrush(fill)) e.Graphics.FillPath(brush, path);
                using (var pen = new Pen(Focused ? Theme.Accent : Theme.Border)) e.Graphics.DrawPath(pen, path);
            }
            TextRenderer.DrawText(e.Graphics, Text, Font, ClientRectangle, !Enabled ? Theme.Muted : Primary ? Theme.Background : Theme.Text,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine);
        }
    }

    internal sealed class StatusTile : Panel
    {
        private readonly Label value;
        public StatusTile(string title)
        {
            BackColor = Theme.Surface; Padding = new Padding(13, 12, 13, 10); Dock = DockStyle.Fill; Margin = new Padding(0, 0, 10, 0); MinimumSize = new Size(100, 84);
            var stack = Theme.Stack(); stack.Dock = DockStyle.Fill;
            var caption = Theme.Label(title, 9); caption.ForeColor = Theme.Muted;
            value = Theme.Label("正在准备", 10, true); value.AutoSize = false; value.Dock = DockStyle.Fill;
            stack.RowStyles.Add(new RowStyle(SizeType.AutoSize)); stack.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            stack.Controls.Add(caption, 0, 0); stack.Controls.Add(value, 0, 1); Controls.Add(stack);
        }
        public void UpdateText(string text, Color color) { value.Text = text; value.ForeColor = color; }
    }
}
