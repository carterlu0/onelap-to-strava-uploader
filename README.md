# Magene-link -> Strava

> 迈金码表骑行数据自动同步到 Strava
> 自动修正 GCJ-02 坐标偏移，保留功率/心率/踏频数据

---

## 原理

```
迈金码表 -> 顽鹿APP -> 分享FIT -> QQ我的电脑 -> D:\QQfiles -> 自动检测 -> 修正 -> Strava
```

---

## 安装

### 1. 获取代码

```bash
git clone https://github.com/carterlu0/onelap-to-strava-uploader.git
cd onelap-to-strava-uploader
pip install -r requirements.txt
```

### 2. 获取 Strava API 凭据

打开 https://www.strava.com/settings/api ，创建应用：

| 字段 | 填写内容 |
|:---|:---|
| 应用名称 | `Magene-link`（任意英文） |
| 网站 URL | `http://localhost:5000` |
| 授权回调域名 | `localhost` |

创建后复制 **Client ID**（数字）和 **Client Secret**（字符串）。

### 3. 运行配置向导

双击 `start_app.bat`

浏览器打开后：
1. 输入 Client ID / Client Secret -> 保存
2. 点击连接 Strava -> 完成 OAuth 授权
3. 确认 QQ 文件接收目录（默认 `D:\QQfiles`）

> 所有凭据仅保存在本地 `config.json`，不会上传任何服务器。

---

## 日常使用

### 启动（每次开机一次）

双击 `start_watcher.bat`，最小化窗口即可，不要关闭。

### 骑行后上传

1. 打开顽鹿 APP -> 活动 -> 分享 -> QQ我的电脑
2. 30秒内自动出现在 Strava 上

---

## GCJ-02 自动修正

迈金码表使用 GCJ-02（火星坐标系），Strava 使用 WGS-84，直接上传会偏移 100-700 米。

本工具自动：
1. 解析 FIT 提取坐标、心率、功率、踏频
2. GCJ-02 -> WGS-84 坐标转换
3. 生成标准 TCX -> 上传 Strava

> 可通过 `config.json` 中的 `fit_fix_gcj02` 开关控制（默认 `true`）。

---

## 配置参考

```json
{
    "strava_api": {
        "client_id":     "数字",
        "client_secret": "密钥"
    },
    "fit_watch_dir": "D:\\QQfiles",
    "fit_fix_gcj02": true
}
```

| 字段 | 说明 |
|:---|:---|
| `strava_api` | Client ID/Secret，Token 由 OAuth 自动管理 |
| `fit_watch_dir` | QQ 文件接收目录 |
| `fit_fix_gcj02` | 是否自动修正 GCJ-02（默认 true） |

---

## 项目文件

| 文件 | 用途 |
|:---|:---|
| `app.py` | Web 配置向导 |
| `file_watcher.py` | 文件夹监听 + 自动上传 |
| `fit_fixer.py` | GCJ-02 坐标检测 + WGS-84 修正 |
| `to_tcx.py` | FIT->TCX 转换（修正 + 功率/心率保留） |
| `strava_api.py` | Strava API 客户端 (OAuth 2.0) |
| `magene_device.py` | Magene 码表 USB 设备发现 |
| `start_app.bat` | 启动配置向导 |
| `start_watcher.bat` | 启动后台监听 |
| `config.example.json` | 配置模板 |
