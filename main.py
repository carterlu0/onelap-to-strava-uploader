import sys
import os
import json
import time

# Ensure we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fetch_onelap import OnelapClient, load_config
from format_activities import list_activities
from upload_activity import download_fit, upload_to_strava

def update_config(section, key, value):
    config = {}
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
            except:
                pass
    
    if section not in config:
        config[section] = {}
    
    config[section][key] = value
    
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def main():
    print("=== 迈金 Onelap 到 Strava 同步工具 ===")
    
    # Check Onelap Config
    config = load_config()
    onelap_user = config.get("onelap", {}).get("username")
    onelap_pass = config.get("onelap", {}).get("password")
    
    if not onelap_user or not onelap_pass:
        print("\nconfig.json 中缺少 Onelap 凭据。")
        # In a real interactive session, we would ask here.
        # But for non-interactive demo, we skip or rely on config.
    
    # Check Strava Config
    strava_user = config.get("strava", {}).get("email")
    strava_pass = config.get("strava", {}).get("password")
    
    if not strava_user or not strava_pass:
        print("\n[警告] config.json 中缺少 Strava 凭据。")
        print("请在菜单选项 4 中进行配置。")
    
    while True:
        print("\n菜单:")
        print("1. 从 Onelap 获取最新活动")
        print("2. 列出已保存的活动")
        print("3. 上传活动到 Strava")
        print("4. 配置 Strava 凭据")
        print("5. 退出")
        
        try:
            choice = input("\n请输入选项 (1-5): ").strip()
        except EOFError:
            print("\n由于 EOF 退出。")
            break
        
        if choice == '1':
            client = OnelapClient(onelap_user, onelap_pass)
            if client.login():
                activities = client.get_activities(limit=30)
                if activities:
                    # Filter activities to reduce file size
                    filtered_activities = []
                    for act in activities:
                        filtered_act = {
                            "id": act.get("id"),
                            "date": act.get("date"),
                            "type": act.get("type"),
                            "time": act.get("time"),
                            "totalTime": act.get("totalTime"),
                            "distance": act.get("distance"),
                            "totalDistance": act.get("totalDistance"),
                            "durl": act.get("durl")
                        }
                        filtered_activities.append(filtered_act)

                    with open("activities.json", "w", encoding="utf-8") as f:
                        json.dump(filtered_activities, f, ensure_ascii=False, indent=2)
                    print(f"成功获取 {len(filtered_activities)} 条活动")
                    list_activities(10)
            else:
                print("登录失败。")
                
        elif choice == '2':
            list_activities(20)
            
        elif choice == '3':
            activities = list_activities(20)
            if not activities:
                print("未找到活动。请先获取活动。")
                continue
                
            idx_str = input("请输入要上传的活动编号 (输入 0 取消): ").strip()
            if not idx_str.isdigit():
                print("无效的编号。")
                continue
                
            idx = int(idx_str)
            if idx == 0:
                continue
            if idx < 1 or idx > len(activities):
                print("编号超出范围。")
                continue
            
            # Check credentials again
            config = load_config()
            s_user = config.get("strava", {}).get("email")
            s_pass = config.get("strava", {}).get("password")
            
            if not s_user or not s_pass:
                print("需要 Strava 凭据。")
                u = input("请输入 Strava 邮箱: ").strip()
                p = input("请输入 Strava 密码: ").strip()
                if u and p:
                    update_config("strava", "email", u)
                    update_config("strava", "password", p)
                    s_user = u
                    s_pass = p
                else:
                    print("凭据缺失。取消上传。")
                    continue

            act = activities[idx-1]
            durl = act.get("durl")
            if not durl:
                print("此活动没有下载链接。")
                continue
                
            filename = f"activity_{idx}.fit"
            if download_fit(durl, filename):
                upload_to_strava(os.path.abspath(filename), s_user, s_pass, activity_info=act)
                
        elif choice == '4':
            u = input("请输入 Strava 邮箱: ").strip()
            p = input("请输入 Strava 密码: ").strip()
            if u and p:
                update_config("strava", "email", u)
                update_config("strava", "password", p)
                print("已保存。")
                
        elif choice == '5':
            break

if __name__ == "__main__":
    main()
