"""
Magene-link → Strava 配置向导 (Web UI)
======================================
仅用于首次配置。日常上传请运行: start_watcher.bat
"""
import os
import json
import sys
import webbrowser
from flask import Flask, render_template, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strava_api import StravaClient

app = Flask(__name__)
CONFIG_FILE = "config.json"


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def mask_secrets(config):
    masked = json.loads(json.dumps(config))
    for s in ["onelap", "strava"]:
        if s in masked and "password" in masked[s]:
            masked[s]["password"] = "******" if masked[s]["password"] else ""
    if "strava_api" in masked:
        for k in ["client_secret", "access_token", "refresh_token"]:
            if k in masked["strava_api"] and masked["strava_api"][k]:
                masked["strava_api"][k] = "******"
    return masked


# ===================== 页面 =====================

@app.route('/')
def index():
    return render_template('index.html')


# ===================== 配置 API =====================

@app.route('/api/config', methods=['GET', 'POST'])
def config_handler():
    if request.method == 'GET':
        return jsonify(mask_secrets(load_config()))

    new_data = request.json
    config = load_config()

    if "onelap" not in config:
        config["onelap"] = {}
    if new_data.get("onelap_username"):
        config["onelap"]["username"] = new_data["onelap_username"]
    if new_data.get("onelap_password") and new_data["onelap_password"] != "******":
        config["onelap"]["password"] = new_data["onelap_password"]

    if "strava_api" not in config:
        config["strava_api"] = {}
    if new_data.get("strava_client_id"):
        config["strava_api"]["client_id"] = new_data["strava_client_id"]
    if new_data.get("strava_client_secret") and new_data["strava_client_secret"] != "******":
        config["strava_api"]["client_secret"] = new_data["strava_client_secret"]

    if new_data.get("fit_watch_dir"):
        config["fit_watch_dir"] = new_data["fit_watch_dir"]

    save_config(config)
    return jsonify({"status": "success", "message": "配置已保存"})


# ===================== Strava OAuth =====================

@app.route('/api/strava/status', methods=['GET'])
def strava_status():
    config = load_config().get("strava_api", {})
    cid = config.get("client_id")
    cs = config.get("client_secret")

    if not cid or not cs:
        return jsonify({"ready": False, "reason": "no_credentials"})

    client = StravaClient(client_id=cid, client_secret=cs)
    if client.is_authorized():
        try:
            athlete = client.get_athlete()
            return jsonify({
                "ready": True,
                "athlete": {
                    "name": f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip(),
                },
            })
        except Exception:
            pass
    return jsonify({"ready": False, "reason": "not_authorized"})


@app.route('/api/strava/authorize', methods=['POST'])
def strava_authorize():
    config = load_config().get("strava_api", {})
    cid = config.get("client_id")
    cs = config.get("client_secret")
    if not cid or not cs:
        return jsonify({"status": "error", "message": "请先保存 Client ID 和 Secret"}), 400

    client = StravaClient(client_id=cid, client_secret=cs)
    try:
        client.authorize(redirect_port=5001, timeout=120)
        athlete = client.get_athlete()
        return jsonify({
            "status": "success",
            "message": f"授权成功，已连接 {athlete.get('firstname', '')} 的 Strava",
        })
    except TimeoutError:
        return jsonify({"status": "error", "message": "授权超时，请重试"}), 408
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ===================== 启动 =====================

if __name__ == '__main__':
    print("=" * 55)
    print("  Magene-link -> Strava 配置向导")
    print("=" * 55)
    print()
    print("  按页面指引完成配置后，关闭此窗口。")
    print("  日常上传请运行: start_watcher.bat")
    print()

    webbrowser.open("http://127.0.0.1:5000")
    app.run(debug=False, port=5000)
