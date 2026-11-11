# 从 GitHub 恢复 v0.2.0-beta.3

本仓库和同版本 Release 足以恢复本版软件工程、模型和可运行程序。**不是原电脑磁盘的完整备份**：不包含私人配置/日志、文稿、Conda/venv、其他项目或旧版本。删除本地工程不会影响已上传的 GitHub 内容，但请等发布完成并确认下述验证结果后再自行清理；发布流程不会替你删除原工程。

## A. 恢复使用（不开发）

1. 打开 [v0.2.0-beta.3 Release](https://github.com/Evangelioonnn/touchless-ppt-controller/releases/tag/v0.2.0-beta.3)。
2. 下载安装 EXE，或下载名称含 `portable.zip` 的完整便携包。
3. 便携包完整解压后运行 `TouchlessPPTController.exe`，不要只复制小 EXE。
4. 安装本机 Microsoft PowerPoint、连接摄像头；程序已经自带 Python 运行时和 ONNX 模型。

安装包/便携包不依赖原工程路径、不依赖原来的自动拍照项目或 Conda 环境。Windows/.NET/Office 等外部运行前提仍需要满足。原用户相机选择、窗口位置等恢复为新电脑的默认设置，可重新调整。

## B. 恢复源码与模型

安装 Git 和 Windows x64 Python 3.12（构建参考 3.12.13），然后在新目录运行：

```powershell
git clone --branch v0.2.0-beta.3 --depth 1 https://github.com/Evangelioonnn/touchless-ppt-controller.git
cd touchless-ppt-controller
py -3.12 -m venv .venv-release
.venv-release\Scripts\python.exe -m pip install -r requirements/build-lock.txt
.venv-release\Scripts\python.exe tools/restore_models.py
.venv-release\Scripts\python.exe tools/run_checks.py
.venv-release\Scripts\python.exe ppt_controller.py --self-check --backend onnx
.venv-release\Scripts\python.exe tools/build_launcher.py --backend onnx
.\build\development\TouchlessPPTController.exe
```

标签定位这次发布对应的代码；Git 提示 detached HEAD 是按标签恢复的正常结果。需要继续开发可再创建分支。没有 Git 时下载 Release 的 `source-candidate.zip` 并解压，后续步骤相同。

模型不放进 Git 历史，避免大文件克隆；同版本 `models.zip` 保存：

- `models/yolo26s-pose.pt`：官方原始 checkpoint，恢复 Torch 开发/重新导出的首选源。
- `models/yolo26s-pose.onnx`：本次验证的 FP32 ONNX，直接恢复它，不要求重新导出得到逐字节相同文件。
- `models/manifest.json`：来源、许可、转换参数与模型哈希。

`tools/restore_models.py` 从固定版本 Release 下载，逐个校验模型哈希；已存在且正确的模型不会重下，已存在但不匹配时拒绝覆盖。正常软件启动不调用它。手动恢复时把 models.zip 的 `models/` 合并到工程根目录，保留本版的清单。

若 Release 模型暂时不可访问，原始 PT 仍有官方来源，可运行 `tools/fetch_model.py` 获取并校验；重新导出步骤见 [BUILD.md](BUILD.md)。重新导出可能改变 ONNX 的文件级哈希，必须重新验证并记录，不能冒充当前附件。

## C. 重新打包

完成 B 后：

```powershell
.venv-release\Scripts\python.exe tools/build_release.py
.venv-release\Scripts\python.exe tools/build_model_backup.py
.venv-release\Scripts\python.exe tools/prepare_public_source.py
```

这会生成便携候选与源码候选。生成安装包另需 Inno Setup，详见 [BUILD.md](BUILD.md)。正常使用不需要 Inno Setup、Node.js 或训练环境。不同工具链的重建产物不保证与这次 Release 逐字节一致，不能沿用旧校验文件。

## D. 校验附件

Release 的 `SHA256SUMS.txt` 覆盖安装器、便携包、源码包和模型包。PowerShell 可核对：

```powershell
Get-FileHash -Algorithm SHA256 .\TouchlessPPTController-v0.2.0-beta.3-windows-x64-setup.exe
Get-FileHash -Algorithm SHA256 .\TouchlessPPTController-v0.2.0-beta.3-models.zip
```

将结果与同版本 `SHA256SUMS.txt` 对照。来源/哈希不对时停止运行，重新获取；不要通过关闭安全软件来解决。GitHub 自动生成的源码 ZIP 没有模型和运行环境，不能代替 portable.zip。

## 发布后的恢复核验口径

维护者会从远程版本标签克隆到独立目录，从 Release 下载模型，核对源码/模型清单并运行回归与 ONNX 自检。这个过程不读取原项目里的模型文件，验证的是工程与附件可恢复；不等于新电脑的摄像头/Office/驱动组合都已通过。最终远程核验结果写入 Release 说明，不凭本地打包成功宣称已上传成功。
