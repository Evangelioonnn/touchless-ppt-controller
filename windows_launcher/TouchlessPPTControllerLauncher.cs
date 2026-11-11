using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

namespace TouchlessPPTControllerLauncher
{
    internal static class Program
    {
        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        private static extern int SetCurrentProcessExplicitAppUserModelID(string appId);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr FindWindow(string className, string windowName);
        [DllImport("user32.dll")]
        private static extern bool SetForegroundWindow(IntPtr window);
        [DllImport("user32.dll")]
        private static extern bool ShowWindow(IntPtr window, int command);
        [DllImport("user32.dll")] private static extern bool SetProcessDpiAwarenessContext(IntPtr awareness);

        [STAThread]
        private static void Main(string[] args)
        {
            try { SetProcessDpiAwarenessContext(new IntPtr(-4)); } catch { }
            bool created;
            using (var mutex = new Mutex(true, @"Local\TouchlessPPTController.UI.v2", out created))
            {
                if (!created)
                {
                    try { using (var signal = EventWaitHandle.OpenExisting(ControllerAppContext.ActivationEventName)) signal.Set(); }
                    catch
                    {
                        IntPtr window = FindWindow(null, "Touchless PPT Controller");
                        if (window != IntPtr.Zero) { ShowWindow(window, 9); SetForegroundWindow(window); }
                    }
                    return;
                }
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                SetCurrentProcessExplicitAppUserModelID("TouchlessPPTController.YOLO26");
                try { using (var context = new ControllerAppContext(args)) Application.Run(context); }
                catch (Exception error) { MessageBox.Show(error.Message, "Touchless PPT Controller", MessageBoxButtons.OK, MessageBoxIcon.Error); }
            }
        }
    }
}

