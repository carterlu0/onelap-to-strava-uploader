import json
from datetime import datetime
import os

def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def format_distance(meters):
    return f"{meters/1000:.2f} km"

def list_activities(limit=20):
    if not os.path.exists("activities.json"):
        print("activities.json not found.")
        return []

    with open("activities.json", "r", encoding="utf-8") as f:
        activities = json.load(f)

    # Sort by date descending
    activities.sort(key=lambda x: x.get("date", ""), reverse=True)

    top_n = activities[:limit]

    print("最近的活动:")
    print("-" * 60)
    print(f"{'编号':<4} {'日期':<18} {'距离':<12} {'时长':<10} {'标题'}")
    print("-" * 60)

    for i, act in enumerate(top_n, 1):
        date = act.get("date", "N/A")
        dist = format_distance(act.get("totalDistance", 0))
        dur = format_duration(act.get("totalTime", 0))
        title = act.get("name", "") or "无标题"
        print(f"{i:<4} {date:<18} {dist:<12} {dur:<10} {title}")

    print("-" * 60)
    return activities

if __name__ == "__main__":
    list_activities()
