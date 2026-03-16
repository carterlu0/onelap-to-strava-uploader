import json
from datetime import datetime
import os

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
        raw_dist = act.get("totalDistance") if act.get("totalDistance") is not None else act.get("distance")
        raw_dur = act.get("totalTime") if act.get("totalTime") is not None else act.get("time")
        dist = format_distance(raw_dist)
        dur = format_duration(raw_dur)
        title = act.get("name", "") or "无标题"
        print(f"{i:<4} {date:<18} {dist:<12} {dur:<10} {title}")

    print("-" * 60)
    return activities

if __name__ == "__main__":
    list_activities()
