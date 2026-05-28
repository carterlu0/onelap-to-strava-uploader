"""
Magene-link → Strava 配置向导 (Web UI)
======================================
仅用于首次配置。日常上传请运行: start_watcher.bat
"""
import os
import json
import sys
import tempfile
import time
import webbrowser
from flask import Flask, render_template, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strava_api import StravaClient
from fit_fixer import fix_fit_file, gcj02_to_wgs84, offset_distance
import magene_device

app = Flask(__name__)
CONFIG_FILE = "config.json"

# 上传文件临时目录
TEMP_DIR = os.path.join(tempfile.gettempdir(), "magene_strava_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)


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
    if "onelap" in masked and "password" in masked["onelap"]:
        masked["onelap"]["password"] = "******" if masked["onelap"]["password"] else ""
    if "strava_api" in masked:
        for k in ["client_secret", "access_token", "refresh_token"]:
            if k in masked["strava_api"] and masked["strava_api"][k]:
                masked["strava_api"][k] = "******"
    return masked


def get_strava_from_config():
    config = load_config().get("strava_api", {})
    return StravaClient(
        client_id=config.get("client_id"),
        client_secret=config.get("client_secret"),
    )


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

    # GCJ-02 自动修正开关
    if "fit_fix_gcj02" in new_data:
        config["fit_fix_gcj02"] = bool(new_data["fit_fix_gcj02"])

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
                "athlete": {"name": f"{athlete.get('firstname','')} {athlete.get('lastname','')}".strip()},
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
        return jsonify({"status": "success",
                        "message": f"授权成功，已连接 {athlete.get('firstname','')} 的 Strava"})
    except TimeoutError:
        return jsonify({"status": "error", "message": "授权超时，请重试"}), 408
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ===================== 手动 FIT 上传 =====================

@app.route('/api/upload/fit', methods=['POST'])
def upload_fit():
    """接收拖放上传的 .fit 文件，自动修正 GCJ-02 坐标后上传 Strava"""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "没有收到文件"}), 400

    uploaded = request.files['file']
    if not uploaded.filename:
        return jsonify({"status": "error", "message": "文件名为空"}), 400

    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in ('.fit', '.gpx', '.tcx'):
        return jsonify({"status": "error", "message": f"不支持的文件格式: {ext}"}), 400

    # 保存临时文件
    filepath = os.path.join(TEMP_DIR, f"{int(time.time())}_{uploaded.filename}")
    uploaded.save(filepath)

    try:
        config = load_config()
        fix_gcj02 = config.get("fit_fix_gcj02", True)

        # GCJ-02 → WGS-84 修正
        if fix_gcj02 and ext == '.fit':
            fix_result = fix_fit_file(filepath)
            if fix_result.get("fixed"):
                pass  # file has been fixed in-place

        # 上传到 Strava
        client = get_strava_from_config()
        if not client.is_authorized():
            return jsonify({"status": "error", "message": "Strava 未授权，请先完成 Strava 连接"}), 400

        result = client.upload_activity(
            filepath,
            name=request.form.get("name"),
            description=request.form.get("description"),
            activity_type=request.form.get("type"),
            external_id=request.form.get("external_id"),
        )

        return jsonify({
            "status": "success",
            "strava": result,
            "fix": {"applied": fix_gcj02} if ext == '.fit' else None,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        # 清理临时文件
        try:
            os.remove(filepath)
        except OSError:
            pass


# ===================== 坐标修正测试 =====================

@app.route('/api/gcj02/test', methods=['POST'])
def gcj02_test():
    """测试 GCJ-02 → WGS-84 转换效果"""
    data = request.json
    lng = float(data.get("lng", 0))
    lat = float(data.get("lat", 0))
    wgs = gcj02_to_wgs84(lng, lat)
    distance = offset_distance(lng, lat)
    return jsonify({
        "input": {"lng": lng, "lat": lat},
        "output": {"lng": round(wgs[0], 6), "lat": round(wgs[1], 6)},
        "offset_meters": round(distance, 1),
    })


# ===================== Magene 设备 =====================

@app.route('/api/device/scan', methods=['POST'])
def device_scan():
    """扫描 Magene 设备"""
    device_path = magene_device.find_magene_device()
    if not device_path:
        return jsonify({"found": False, "message": "未检测到 Magene 设备"})

    fit_files = magene_device.scan_for_fit_files(device_path, since_days=365)
    return jsonify({
        "found": True,
        "device_path": device_path,
        "files": fit_files,
        "count": len(fit_files),
    })


@app.route('/api/device/copy', methods=['POST'])
def device_copy():
    """从 Magene 设备复制 FIT 文件"""
    device_path = magene_device.find_magene_device()
    if not device_path:
        return jsonify({"status": "error", "message": "未检测到 Magene 设备"}), 404

    dest_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fit_files")
    copied = magene_device.copy_fit_from_device(device_path, dest_dir, since_days=365)
    return jsonify({
        "status": "success",
        "copied": copied,
        "count": len(copied),
        "dest_dir": dest_dir,
    })


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

