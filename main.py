"""
Magene-link → Strava 同步工具 (CLI)
使用 Strava API (OAuth 2.0) 自动上传，无需浏览器
"""
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fetch_onelap import OnelapClient, load_config
from format_activities import list_activities, normalize_activity
from strava_api import StravaClient, get_strava_client

FIT_DIR = "fit_files"
os.makedirs(FIT_DIR, exist_ok=True)


def update_config(section, key, value):
    config = load_config()
    if section not in config:
        config[section] = {}
    config[section][key] = value
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def ensure_strava_authorized():
    """确保 Strava 已授权，未授权则触发 OAuth 流程"""
    client = get_strava_client()
    if client.is_authorized():
        try:
            client.ensure_token_valid()
            return client
        except Exception:
            pass

    config = load_config().get("strava_api", {})
    cid = config.get("client_id")
    cs = config.get("client_secret")
    if not cid or not cs:
        print("\n❌ 请先在 config.json 中配置 strava_api.client_id 和 client_secret")
        print("   获取地址: https://www.strava.com/settings/api")
        return None

    print("\n🔐 需要 Strava 授权...")
    client = StravaClient(client_id=cid, client_secret=cs)
    try:
        client.authorize()
        athlete = client.get_athlete()
        print(f"✅ 已连接: {athlete.get('firstname')} {athlete.get('lastname')}")
        return client
    except Exception as e:
        print(f"❌ 授权失败: {e}")
        return None


def cmd_fetch():
    """从 Onelap 获取活动"""
    config = load_config()
    user = config.get("onelap", {}).get("username")
    pwd = config.get("onelap", {}).get("password")

    if not user or not pwd:
        print("❌ config.json 中缺少 Onelap 凭据")
        return

    client = OnelapClient(user, pwd)
    if not client.login():
        print("❌ Onelap 登录失败")
        return

    activities = client.get_activities(limit=30)
    if not activities:
        print("⚠️ 未获取到活动")
        return

    normalized = [normalize_activity(a) for a in activities]
    with open("activities.json", "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    print(f"✅ 已保存 {len(normalized)} 条活动")
    list_activities(10)


def cmd_list():
    """列出活动"""
    list_activities(20)


def cmd_upload():
    """上传活动到 Strava"""
    # 确保已认证
    strava = ensure_strava_authorized()
    if not strava:
        return

    activities = list_activities(20, print_table=True)
    if not activities:
        print("未找到活动。请先执行 'fetch'。")
        return

    while True:
        try:
            idx_str = input("\n请选择方式: [编号] 从Onelap上传 / [路径] 本地文件 / [0] 取消: ").strip()
        except EOFError:
            return

        if idx_str == '0':
            return

        # 判断是编号还是文件路径
        if idx_str.isdigit():
            idx = int(idx_str) - 1
            if idx < 0 or idx >= len(activities):
                print("编号超出范围")
                continue

            act = activities[idx]
            durl = act.get("durl")
            if not durl:
                print("❌ 该活动没有 FIT 下载链接，请使用本地文件路径上传")
                continue

            print(f"📥 正在下载: 活动 {act.get('id')} ...")
            config = load_config()
            client = OnelapClient(
                config.get("onelap", {}).get("username"),
                config.get("onelap", {}).get("password")
            )
            client.login()

            filepath = os.path.join(FIT_DIR, f"onelap_{act['id']}.fit")
            if not client.download_fit(durl, filepath):
                print("❌ 下载失败")
                continue
        else:
            # 文件路径
            filepath = idx_str
            if not os.path.exists(filepath):
                print(f"❌ 文件不存在: {filepath}")
                continue
            act = {}

        # 上传
        try:
            result = strava.upload_activity(
                filepath,
                external_id=f"onelap_{act.get('id')}" if act.get('id') else None
            )
            if result.get("status") == "success":
                print(f"🎉 上传成功！活动 ID: {result.get('activity_id')}")
            elif result.get("status") == "processing":
                print("⏳ 文件已提交，Strava 正在处理...")
            else:
                print(f"❌ 上传失败: {result.get('error')}")
        except Exception as e:
            print(f"❌ 上传异常: {e}")
        break


def main():
    print("=" * 45)
    print("  Magene-link → Strava 同步工具 v2.0 (CLI)")
    print("=" * 45)

    while True:
        print("\n菜单:")
        print("  1. 从 Onelap 获取最新活动")
        print("  2. 列出已保存的活动")
        print("  3. 上传活动到 Strava")
        print("  4. 退出")

        try:
            choice = input("\n请选择 (1-4): ").strip()
        except EOFError:
            break

        if choice == '1':
            cmd_fetch()
        elif choice == '2':
            cmd_list()
        elif choice == '3':
            cmd_upload()
        elif choice == '4':
            break
        else:
            print("无效选项")


if __name__ == "__main__":
    main()
