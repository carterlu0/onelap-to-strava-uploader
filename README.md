# Onelap to Strava Uploader

这是一个用于将 Onelap (顽鹿) 的骑行/跑步活动自动同步上传到 Strava 的工具。

## 功能特点

*   **自动获取**：从 Onelap 获取最新的活动记录。
*   **自动上传**：自动下载 FIT 文件并上传到 Strava。
*   **智能验证**：上传后自动跳转到 Strava 活动日志，验证日期和距离是否匹配，确保上传成功。
*   **Web 界面**：提供直观的网页操作界面，无需敲命令行。
*   **Edge 浏览器集成**：支持直接调用本机已登录 Strava 的 Edge 浏览器，无需在脚本中输入 Strava 账号密码（避免验证码问题）。

## 依赖

*   Python 3.8+
*   Microsoft Edge 浏览器 (用于自动化上传)

## 安装

1.  克隆本项目：
    ```bash
    git clone https://github.com/YOUR_USERNAME/onelap-to-strava-uploader.git
    cd onelap-to-strava-uploader
    ```

2.  安装 Python 依赖：
    ```bash
    pip install -r requirements.txt
    playwright install chromium
    ```

## 使用方法

### 方式一：Web 界面 (推荐)

1.  双击运行 `start_app.bat` (Windows)。
2.  浏览器会自动打开 `http://127.0.0.1:5000`。
3.  **配置**：在网页左侧输入您的 Onelap 账号和密码并保存。
4.  **启动浏览器**：点击“启动调试版 Edge 浏览器”，这会打开一个专用的 Edge 窗口。**请在此窗口中登录 Strava 并保持开启**。
5.  **获取活动**：点击“从 Onelap 获取最新活动”。
6.  **上传**：在列表中点击“上传到 Strava”。

### 方式二：命令行

1.  启动 Edge 调试模式（只需运行一次）：
    ```bash
    python launch_edge.py
    ```
2.  运行主程序：
    ```bash
    python main.py
    ```
    按提示操作即可。

## 注意事项

*   **账号安全**：您的账号密码仅保存在本地的 `config.json` 文件中，不会上传到任何服务器。
*   **浏览器窗口**：上传过程中脚本会控制 Edge 浏览器，请勿手动关闭正在工作的标签页。

## License

MIT
