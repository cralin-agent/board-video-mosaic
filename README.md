# Board Video Mosaic — 板书视频批量压缩

Windows 双击 **Start-Windows.cmd**。第一次启动自动创建隔离的 Python 环境并安装依赖（需要联网和 Python 3.11+）；之后可拖入一个含多个视频的文件夹，或浏览选择文件夹。

选择两种算法：
- **Color AVIF (default)**: 彩色、不降分辨率、可选解码后的 SSIM ≥ 0.980 和边缘灰度 MAE ≤ 5.0 自适应质量筛查。这是原单帧 `board_frame_codec.py` 的视频四宫格集成版本。**筛查不等于数学符号识别保证**。
- **DSH binary**: 基于 DSH 的局部亮度对比度、绿色黑板邻域、笔画密度与去孤立点的 1-bit PNG。默认 k=15；无自动去重；无黑板画面回退 RGB。**存在已实测的浅色笔迹被删除风险，只作为导航材料**。

## 输出协议

- 每个视频每秒取一帧（ffmpeg fps=1），按时间连续 4 帧组成 2×2，帧不缩小。
- 输出到拖入文件夹下的 `BoardPackages/<视频名>_<路径hash>/<avif或dsh>/`。
- 每个视频独立 `part_001.zip`、`part_002.zip` 等，ZIP 内含 `mosaics/`、`manifest.json`、`index.html` 和说明。
- **单 ZIP 必须 < 100,000,000 字节**；按 90,000,000 字节预算自动分包，避免将 MiB 误当 MB。每个分包解压后可独立打开 index.html。
- 视频子目录递归处理；同名视频通过相对路径哈希区分。源视频不修改。
- 全批次 `batch_report.json` 记录成功与失败，失败视频不冒充完成。
- 失败不自动删除已完成的其他视频；中途出错的 `.zip.part` 删除。

## 命令行

```powershell
.venv\Scripts\python.exe pipeline.py "D:\Lectures" --mode avif
.venv\Scripts\python.exe pipeline.py "D:\Lectures" --mode dsh
.venv\Scripts\python.exe pipeline.py "D:\Lectures" --mode avif --fast-avif
```

视频格式：MP4/MKV/MOV/AVI/WEBM/M4V/WMV/TS。后端通过 `imageio-ffmpeg` 提供 FFmpeg；GUI 使用 tkinterdnd2 接收文件夹拖入，若不可用仍可用浏览按钮。

## 与既有实验的关系

复用了两条 **算法路线**，并重新实现了统一批处理与打包器。DSH 不是官方库或完整原脚本的逐字镜像，而是来自此前 L07 实验 `fast_chalk.py` 的明确等效实现。彩色 AVIF 对应此前单帧 `board_frame_codec.py` 的解码质量门槛。实际输出必须经复核，不应把二值图作为“没有笔迹”的证据。

## 校验

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```
