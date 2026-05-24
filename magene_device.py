"""
Magene 设备 FIT 文件自动发现模块
检测 USB 连接的 Magene 码表，自动提取 FIT 文件
"""
import os
import sys
import glob
import shutil
import time
from datetime import datetime


# Magene 设备常见的卷标和路径
# Magene C706/C506 等码表 USB 连接后通常显示为 U 盘，FIT 文件在特定目录
MAGENE_PATTERNS = [
    # Garmin 风格目录结构 (Magene 兼容)
    "?:/GARMIN/Garmin/Activities/*.fit",
    "?:/Garmin/Activities/*.fit",
    "?:/Activities/*.fit",
    # 直接的 FIT 文件夹
    "?:/FIT/*.fit",
    # 根目录 (最低优先级，可能导致误报)
    "?:/*.fit",
]


def get_all_drives():
    """获取 Windows 下所有可用盘符"""
    drives = []
    for letter in "DEFGHIJK":
        path = f"{letter}:/"
        if os.path.exists(path):
            drives.append(path)
    return drives


def find_magene_device():
    """
    检测 Magene 设备挂载点
    通过扫描已知路径模式来发现设备，排除明显的非设备目录
    """
    # 需要排除的目录 (Windows 系统目录、下载目录等)
    EXCLUDE_DIRS = {
        "downloads", "documents", "desktop", "music", "pictures",
        "videos", "windows", "program files", "program files (x86)",
        "programdata", "users", "temp", "tmp",
    }

    # 方法1: 扫描已知模式
    for pattern in MAGENE_PATTERNS:
        for drive in "DEFGHIJK":
            full_pattern = pattern.replace("?:", f"{drive}:")
            matches = glob.glob(full_pattern)
            if matches:
                dir_path = os.path.dirname(matches[0])

                # 排除非设备目录
                dir_lower = dir_path.lower()
                is_excluded = False
                for ex in EXCLUDE_DIRS:
                    if ex in dir_lower:
                        is_excluded = True
                        break

                if not is_excluded:
                    return dir_path

    # 方法2: 扫描所有盘符，查找特定的 Magene/Garmin 目录结构
    for drive in get_all_drives():
        # 只检查根目录下的特定文件夹
        for check_dir in ["GARMIN", "Garmin", "Activities", "FIT"]:
            check_path = os.path.join(drive, check_dir)
            if not os.path.isdir(check_path):
                continue

            # 查找 FIT 文件
            for root, dirs, files in os.walk(check_path):
                depth = root.replace(drive, "").count(os.sep)
                if depth > 3:
                    dirs.clear()
                    continue
                fit_files = [f for f in files if f.lower().endswith(".fit")]
                if fit_files:
                    return root

    return None


def scan_for_fit_files(directory, since_days=30):
    """
    扫描目录中的 FIT 文件

    返回: [(filepath, filename, size, mtime), ...]
    """
    if not directory or not os.path.isdir(directory):
        return []

    cutoff = time.time() - (since_days * 86400)
    results = []

    for f in os.listdir(directory):
        if not f.lower().endswith(".fit"):
            continue
        filepath = os.path.join(directory, f)
        try:
            stat = os.stat(filepath)
            if stat.st_mtime > cutoff:
                results.append({
                    "path": filepath,
                    "name": f,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
        except OSError:
            pass

    # 按修改时间排序（最新的在前）
    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results


def copy_fit_from_device(device_path, dest_dir="fit_files", since_days=30):
    """
    从设备复制 FIT 文件到本地

    返回: [copied_filepaths, ...]
    """
    os.makedirs(dest_dir, exist_ok=True)
    fit_files = scan_for_fit_files(device_path, since_days)
    copied = []

    for f in fit_files:
        dest = os.path.join(dest_dir, f["name"])
        # 如果目标已存在且大小相同，跳过
        if os.path.exists(dest) and os.path.getsize(dest) == f["size"]:
            continue

        try:
            shutil.copy2(f["path"], dest)
            copied.append(dest)
            print(f"  📋 复制: {f['name']} ({f['size'] / 1024:.1f} KB)")
        except Exception as e:
            print(f"  ⚠️ 复制失败 {f['name']}: {e}")

    return copied


def auto_discover_and_copy(dest_dir="fit_files"):
    """
    自动发现 Magene 设备并复制 FIT 文件

    返回: (device_path, copied_files)
    """
    print("🔍 正在搜索 Magene 设备...")

    device = find_magene_device()
    if not device:
        print("  ❌ 未检测到 Magene 设备")
        print("  💡 请确保码表已通过 USB 连接电脑并开机")
        return None, []

    print(f"  ✅ 发现设备: {device}")
    copied = copy_fit_from_device(device, dest_dir)
    print(f"  📦 共复制 {len(copied)} 个文件")
    return device, copied


if __name__ == "__main__":
    auto_discover_and_copy()
