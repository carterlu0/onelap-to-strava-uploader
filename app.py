import os
import json
import subprocess
import threading
from flask import Flask, render_template, jsonify, request
from fetch_onelap import OnelapClient
from upload_activity import download_fit, upload_to_strava

app = Flask(__name__)

CONFIG_FILE = "config.json"
ACTIVITIES_FILE = "activities.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def config_handler():
    if request.method == 'GET':
        config = load_config()
        # Mask passwords
        if "onelap" in config:
            config["onelap"]["password"] = "******"
        if "strava" in config:
            config["strava"]["password"] = "******"
        return jsonify(config)
    
    if request.method == 'POST':
        new_data = request.json
        config = load_config()
        
        # Update Onelap
        if "onelap" not in config: config["onelap"] = {}
        if new_data.get("onelap_username"):
            config["onelap"]["username"] = new_data["onelap_username"]
        if new_data.get("onelap_password") and new_data["onelap_password"] != "******":
            config["onelap"]["password"] = new_data["onelap_password"]
            
        # Update Strava
        if "strava" not in config: config["strava"] = {}
        if new_data.get("strava_email"):
            config["strava"]["email"] = new_data["strava_email"]
        if new_data.get("strava_password") and new_data["strava_password"] != "******":
            config["strava"]["password"] = new_data["strava_password"]
            
        save_config(config)
        return jsonify({"status": "success", "message": "配置已更新"})

@app.route('/api/activities', methods=['GET'])
def get_activities():
    if os.path.exists(ACTIVITIES_FILE):
        with open(ACTIVITIES_FILE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify([])

@app.route('/api/fetch', methods=['POST'])
def fetch_activities():
    config = load_config()
    user = config.get("onelap", {}).get("username")
    pwd = config.get("onelap", {}).get("password")
    
    if not user or not pwd:
        return jsonify({"status": "error", "message": "请先配置 Onelap 账号密码"}), 400
        
    client = OnelapClient(user, pwd)
    if client.login():
        activities = client.get_activities(limit=30)
        if activities:
            # Filter activities to reduce file size
            filtered_activities = []
            for act in activities:
                total_time = act.get("totalTime")
                if total_time is None:
                    total_time = act.get("time")

                total_dist = act.get("totalDistance")
                if total_dist is None:
                    total_dist = act.get("distance")

                filtered_act = {
                    "id": act.get("id"),
                    "date": act.get("date"),
                    "type": act.get("type"),
                    "time": act.get("time"),
                    "totalTime": total_time,
                    "distance": act.get("distance"),
                    "totalDistance": total_dist,
                    "durl": act.get("durl")
                }
                filtered_activities.append(filtered_act)

            with open(ACTIVITIES_FILE, "w", encoding="utf-8") as f:
                json.dump(filtered_activities, f, ensure_ascii=False, indent=2)
            
            return jsonify({"status": "success", "message": f"成功获取 {len(filtered_activities)} 条活动", "data": filtered_activities})
        else:
            return jsonify({"status": "warning", "message": "登录成功但未获取到活动"}), 200
    else:
        return jsonify({"status": "error", "message": "Onelap 登录失败"}), 400

@app.route('/api/upload', methods=['POST'])
def upload_activity():
    data = request.json
    index = data.get("index") # 0-based index in the file
    
    if index is None:
        return jsonify({"status": "error", "message": "未指定活动索引"}), 400
        
    if not os.path.exists(ACTIVITIES_FILE):
        return jsonify({"status": "error", "message": "活动列表不存在，请先获取活动"}), 400
        
    with open(ACTIVITIES_FILE, "r", encoding="utf-8") as f:
        activities = json.load(f)
        
    if index < 0 or index >= len(activities):
        return jsonify({"status": "error", "message": "索引超出范围"}), 400
        
    act = activities[index]
    durl = act.get("durl")
    if not durl:
        return jsonify({"status": "error", "message": "该活动没有下载链接"}), 400
        
    filename = f"activity_{index+1}.fit"
    filepath = os.path.abspath(filename)
    
    # Download
    if not download_fit(durl, filename):
        return jsonify({"status": "error", "message": "下载 FIT 文件失败"}), 500
        
    # Upload
    # Load strava credentials just in case needed for fallback
    config = load_config()
    s_user = config.get("strava", {}).get("email")
    s_pass = config.get("strava", {}).get("password")
    
    # Run upload in a separate thread to avoid blocking? 
    # Or keep it blocking so we can return result?
    # Upload usually takes time (browser interaction).
    # Since Playwright automation needs to interact with desktop, let's try blocking for now.
    # Note: Flask's dev server is single threaded by default unless threaded=True (default).
    
    try:
        success = upload_to_strava(filepath, s_user, s_pass, activity_info=act)
        if success:
            return jsonify({"status": "success", "message": "上传并验证成功！"})
        else:
            return jsonify({"status": "error", "message": "上传失败或验证未通过，请检查浏览器窗口"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"发生异常: {str(e)}"}), 500

@app.route('/api/launch_edge', methods=['POST'])
def launch_edge():
    try:
        # Use subprocess to launch independent script
        # We use 'start' in shell to detach
        subprocess.Popen(["python", "launch_edge.py"], shell=True)
        return jsonify({"status": "success", "message": "已触发 Edge 启动脚本"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"启动失败: {str(e)}"}), 500

if __name__ == '__main__':
    print("启动 Web 服务...")
    print("请在浏览器中访问: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
