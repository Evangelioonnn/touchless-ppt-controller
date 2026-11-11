using System;
using System.Collections;
using System.Collections.Generic;

namespace TouchlessPPTControllerLauncher
{
    internal sealed class TargetItem
    {
        public string Id, Title;
        public override string ToString() { return Title; }
    }
    internal sealed class AppStatus
    {
        public bool Locked = true, Locking, PresenterVisible, Ready, Connected, SettingsLoaded;
        public string CameraState = "loading", CameraMessage = "正在准备摄像头", Device = "正在加载本地模型", LastOperation = "交叉手臂锁定 / 解锁，举手切换幻灯片。";
        public string Stage = "启动中", TargetId = "", RawMessage = "", InferenceMessage = "";
        public double Fps, Latency;
        public long PublishedFrames;
        public int ModelLoads;
        public readonly List<TargetItem> Targets = new List<TargetItem>();
        public Dictionary<string, object> Settings = new Dictionary<string, object>();
        public static string Value(Dictionary<string, object> data, string key, string fallback = "") { return BackendHost.Value(data, key, fallback); }
        private static bool Bool(Dictionary<string, object> data, string key) { return data.ContainsKey(key) && data[key] is bool && (bool)data[key]; }
        public void Update(Dictionary<string, object> data)
        {
            string type = Value(data, "type");
            if (type == "status")
            {
                Locked = !data.ContainsKey("locked") || Bool(data, "locked"); Locking = Bool(data, "locking");
                PresenterVisible = Bool(data, "presenter_visible"); Ready = Bool(data, "ready");
                CameraState = Value(data, "camera_state"); CameraMessage = Value(data, "camera_message");
                Device = Value(data, "device"); InferenceMessage = Value(data, "inference_message");
                double.TryParse(Value(data, "fps", "0"), out Fps); double.TryParse(Value(data, "latency_ms", "0"), out Latency);
                long.TryParse(Value(data, "preview_published_frames", "0"), out PublishedFrames);
                if (data.ContainsKey("settings") && data["settings"] is Dictionary<string, object>) { Settings = (Dictionary<string, object>)data["settings"]; SettingsLoaded = true; }
                var ppt = data.ContainsKey("ppt") ? data["ppt"] as Dictionary<string, object> : null;
                if (ppt != null)
                {
                    Connected = Bool(ppt, "connected"); TargetId = Value(ppt, "target_id"); Targets.Clear();
                    var list = ppt.ContainsKey("targets") ? ppt["targets"] as IEnumerable : null;
                    if (list != null) foreach (object item in list)
                    {
                        var target = item as Dictionary<string, object>;
                        if (target != null) Targets.Add(new TargetItem { Id = Value(target, "id"), Title = Value(target, "title", "PowerPoint") });
                    }
                }
            }
            else if (type == "stage")
            {
                string stage = Value(data, "stage");
                if (stage == "loading_torch" || stage == "loading_ultralytics" || stage == "loading_onnxruntime") Stage = "正在加载本地模型";
                else if (stage == "model_loaded") { Stage = "模型已加载，等待摄像头"; ModelLoads++; }
                else if (stage == "ready") Stage = "识别已就绪";
                else if (stage == "stopped") Stage = "后台已停止";
            }
            else if (type == "error" || type == "warning")
            { RawMessage = Value(data, "message"); LastOperation = type == "error" ? "后台遇到问题，请在设置中重试或查看诊断。" : "有一条运行提示，详见高级设置。"; }
            else if (type == "operation")
            {
                var result = data["result"] as Dictionary<string, object>;
                if (result == null) return;
                string action = Value(result, "action"), state = Value(result, "state");
                string title = action == "next" ? "下一步" : action == "previous" ? "上一步" : "PPT 操作";
                string verdict = state == "observed" ? "已观测到变化" : state == "accepted" ? "已调用 PPT" : state == "sent" ? "消息已发送，未确认执行" : state == "unknown" ? "结果未知，不自动重发" : "未完成";
                LastOperation = title + " · " + verdict; RawMessage = Value(result, "message");
            }
        }
        public string PersonText { get { return !Ready ? "等待识别就绪" : PresenterVisible ? "已找到讲课者" : "等待入镜 · 自动恢复"; } }
        public string TechnicalText
        {
            get { return CameraMessage + Environment.NewLine + Device + " · " + Fps.ToString("0.0") + " FPS · " + Latency.ToString("0.0") + " ms" + Environment.NewLine + InferenceMessage + Environment.NewLine + RawMessage + Environment.NewLine + "预览帧：" + PublishedFrames; }
        }
    }
}
