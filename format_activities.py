"""
活动列表格式化工具
兼容旧版 API 和 OTM API 返回的活动数据格式
"""
import json
from datetime import datetime
import os

# 活动类型映射 (Onelap → 中文)
ACTIVITY_TYPE_MAP = {
    0: "骑行",
    1: "骑行",
    2: "跑步",
    3: "步行",
    27: "骑行",
}


def get_activity_type_label(type_code):
    """将 Onelap 活动类型码转为可读标签"""
    return ACTIVITY_TYPE_MAP.get(type_code, f"类型{type_code}")


def format_duration(seconds):
    if seconds is None:
        seconds = 0
    try:
        seconds = int(float(seconds))
    except (TypeError, ValueError):
        seconds = 0
    if seconds < 0:
        seconds = 0

    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_distance(meters):
    if meters is None:
        meters = 0
    try:
        meters = float(meters)
    except (TypeError, ValueError):
        meters = 0.0
    if meters < 0:
        meters = 0.0
    return f"{meters / 1000:.2f} km"


def normalize_activity(act):
    """
    将不同格式的活动数据统一为标准格式
    支持旧版 API (date, totalDistance, totalTime, durl)
      和 OTM API (start_riding_time, distance_km, time_seconds)
    """
    # 日期: start_riding_time > date > created_at
    date = (
        act.get("start_riding_time")
        or act.get("date")
        or act.get("startTime")
        or act.get("created_at")
        or ""
    )
    # 过滤掉 Unix epoch 默认值
    if date and date.startswith("1970-01-01"):
        date = ""

    # 距离(米): totalDistance > distance > distance_km*1000
    distance = (
        act.get("totalDistance")
        or act.get("distance")
    )
    if distance is None and act.get("distance_km"):
        distance = act["distance_km"] * 1000

    # 时间(秒): totalTime > time > time_seconds
    duration = (
        act.get("totalTime")
        or act.get("time")
        or act.get("time_seconds")
        or 0
    )

    return {
        "id": act.get("id"),
        "rid": act.get("rid"),
        "date": date,
        "type": act.get("type", 0),
        "type_label": get_activity_type_label(act.get("type", 0)),
        "time": duration,
        "time_formatted": format_duration(duration),
        "distance": distance,
        "distance_km": act.get("distance_km"),
        "name": act.get("name") or act.get("title") or "",
        "durl": act.get("durl") or act.get("fit_url") or "",
        # OTM 独有字段
        "avg_speed_kmh": act.get("avg_speed_kmh"),
        "avg_power_w": act.get("avg_power_w"),
        "avg_heart_bpm": act.get("avg_heart_bpm"),
    }


def list_activities(limit=20, print_table=True):
    if not os.path.exists("activities.json"):
        if print_table:
            print("activities.json not found.")
        return []

    with open("activities.json", "r", encoding="utf-8") as f:
        activities = json.load(f)

    # 归一化
    activities = [normalize_activity(a) for a in activities]

    # 按日期降序排列
    activities.sort(key=lambda x: x.get("date", ""), reverse=True)

    top_n = activities[:limit]

    if print_table:
        print("最近的活动:")
        print("-" * 70)
        print(f"{'编号':<4} {'日期':<18} {'类型':<6} {'距离':<12} {'时长':<10} {'标题'}")
        print("-" * 70)

        for i, act in enumerate(top_n, 1):
            date = act.get("date", "N/A")
            dist = format_distance(act.get("distance"))
            dur = format_duration(act.get("time"))
            atype = act.get("type_label", "")
            title = act.get("name") or "无标题"
            print(f"{i:<4} {date:<18} {atype:<6} {dist:<12} {dur:<10} {title}")

        print("-" * 70)

    return activities


if __name__ == "__main__":
    list_activities()

