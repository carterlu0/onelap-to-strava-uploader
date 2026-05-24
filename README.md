# Magene-link → Strava

> 🚴 骑行结束 → 手机分享 FIT 到 QQ「我的电脑」→ 电脑自动上传 Strava  
> **到此一游式操作，无需守在电脑前。一行代码都不用写。**

---

## 🎯 一句话原理

```
顽鹿 APP → 分享 FIT → QQ「我的电脑」→ D:\QQfiles → 自动检测 → Strava ✅
```

---

## 📦 安装（三步，3 分钟）

### ① 下载代码

```bash
git clone https://github.com/carterlu0/onelap-to-strava-uploader.git
cd onelap-to-strava-uploader
pip install -r requirements.txt
```

### ② 获取 Strava API 凭据

打开 https://www.strava.com/settings/api ，创建一个应用：

| 字段 | 填写 |
|:---|:---|
| 应用名称 | `Magene-link`（或任意英文） |
| 网站 URL | `http://localhost:5000` |
| 授权回调域名 | `localhost` |

点创建后，记下页面上显示的 **Client ID**（一串数字）和 **Client Secret**（一长串字符）。

### ③ 运行配置向导

```bash
双击 start_app.bat
```

浏览器打开后按页面提示：
1. 输入顽鹿账号密码 → 保存
2. 输入 Client ID / Client Secret → 保存
3. 点击「连接 Strava」→ 自动跳转授权 → 看到绿色 ✅ 即完成

> 🔐 所有凭据仅保存在本地 `config.json`，不会上传任何服务器。

---

## 🚀 日常使用

### 启动后台（每次开机一次）

```bash
双击 start_watcher.bat
```

看到 `🔍 开始监听文件夹: D:\QQfiles` 表示运行中。**最小化窗口即可，不要关闭。**

### 骑行后上传（仅 2 步）

1. 打开顽鹿 APP → 找到刚骑完的活动 → 点击 **分享** → 选择 **QQ「我的电脑」**
2. 🎉 **30 秒内自动出现在 Strava 上**。`start_watcher.bat` 窗口会打印日志。

---

## 🏠 保持运行

| 需要保持 | 说明 |
|:---|:---|
| 💻 电脑开机 | 待机/锁屏/休眠都行 |
| 🟢 QQ PC 端登录 | 接收手机发来的文件 |
| ▶️ `start_watcher.bat` | 最小化即可，不要关 |

> 💡 建议把 `start_watcher.bat` 放入 `shell:startup` 文件夹实现开机自启。

---

## 🔧 配置参考

`config.json`（由向导自动填写，一般不需手动改）：

```json
{
    "onelap": { "username": "手机号", "password": "密码" },
    "strava_api": { "client_id": "数字", "client_secret": "密钥" },
    "fit_watch_dir": "D:\\QQfiles"
}
```

| 字段 | 说明 |
|:---|:---|
| `fit_watch_dir` | QQ 接收文件的目录。如果 QQ 设置保存在其他位置，改这里。 |
| `strava_api.*` | Token 由 OAuth 自动管理，不用手动填。 |

---

## ❓ FAQ

**Q: 怎么知道上传成功了？**  
看 `start_watcher.bat` 窗口，会打印 `✅ 上传成功! Strava 活动 ID: xxxxxxxx`。也可以直接打开 Strava 确认。

**Q: 提示 "Rate Limit Exceeded"？**  
程序会自动等待恢复，每个文件仅消耗 2 次 API 调用，正常使用不会触发。

**Q: Strava 断了怎么办？**  
重新运行 `start_app.bat` → 点击「连接 Strava」即可。

**Q: 能上传旧的历史活动吗？**  
可以。把旧 .fit 文件拖到 `D:\QQfiles`（或你配置的目录），监听器会自动上传。重复的活动 Strava 会自动去重。

**Q: 不用 QQ 可以吗？**  
只要是能把 .fit 文件传到电脑上指定文件夹的方式都可以。比如微信文件传输助手、AirDrop、甚至 U 盘拷贝。

---

## 📁 项目文件

| 文件 | 角色 |
|:---|:---|
| `start_app.bat` | 🧭 **首次使用**：配置向导 |
| `start_watcher.bat` | 🚀 **日常使用**：后台监听 + 自动上传 |
| `config.json` | 所有配置集中管理 |
| `file_watcher.py` | 文件夹监听引擎 |
| `strava_api.py` | Strava OAuth + 上传 API |
| `fetch_onelap.py` | Onelap 活动列表（参考用） |
| `app.py` | 配置向导 Web 后端 |

## License

MIT
