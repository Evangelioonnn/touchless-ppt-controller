using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO.MemoryMappedFiles;
using System.Runtime.InteropServices;
using System.Threading;

namespace TouchlessPPTControllerLauncher
{
    internal sealed class PreviewChannel : IDisposable
    {
        public const int Capacity = 8 * 1024 * 1024;
        public readonly string Name = @"Local\TouchlessPPTPreview." + Guid.NewGuid().ToString("N");
        private readonly MemoryMappedFile mapping;
        internal readonly MemoryMappedViewAccessor View;
        private byte[] bytes;
        private long lastSequence;
        public long FramesRead { get; private set; }
        public PreviewChannel() { mapping = MemoryMappedFile.CreateNew(Name, Capacity); View = mapping.CreateViewAccessor(); }
        public static double Now { get { return Stopwatch.GetTimestamp() / (double)Stopwatch.Frequency; } }
        public Bitmap ReadLatest()
        {
            if (View.ReadInt32(0) != 0x31565054 || View.ReadInt32(4) != 1) return null;
            long sequence = View.ReadInt64(8);
            if (sequence <= 0 || (sequence & 1) != 0 || sequence == lastSequence) return null;
            int width = View.ReadInt32(16), height = View.ReadInt32(20), stride = View.ReadInt32(24), length = View.ReadInt32(28);
            double stamp = View.ReadDouble(32), age = Now - stamp;
            if (width <= 0 || width > 4096 || height <= 0 || height > 2160 || stride != width * 3 || length != stride * height || length > Capacity - 64 || Double.IsNaN(stamp) || age < -.1 || age > 2) return null;
            if (bytes == null || bytes.Length != length) bytes = new byte[length];
            Thread.MemoryBarrier(); View.ReadArray(64, bytes, 0, length); Thread.MemoryBarrier();
            if (View.ReadInt64(8) != sequence) return null;
            Bitmap bitmap = new Bitmap(width, height, PixelFormat.Format24bppRgb);
            BitmapData locked = bitmap.LockBits(new Rectangle(0, 0, width, height), ImageLockMode.WriteOnly, PixelFormat.Format24bppRgb);
            try { for (int row = 0; row < height; row++) Marshal.Copy(bytes, row * stride, IntPtr.Add(locked.Scan0, row * locked.Stride), stride); }
            finally { bitmap.UnlockBits(locked); }
            lastSequence = sequence; FramesRead++; return bitmap;
        }
        public void Dispose() { View.Dispose(); mapping.Dispose(); }
    }
}
