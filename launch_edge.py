import os
import subprocess
import sys
import winreg
import time

def find_edge_path():
    # 尝试从注册表查找
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
        path, _ = winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)
        if os.path.exists(path):
            return path
    except:
        pass

    # 常见路径
    paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\Application\msedge.exe")
    ]
    
    for p in paths:
        if os.path.exists(p):
            return p
            
    return None

def kill_edge():
    print("正在尝试强制关闭 msedge.exe (可能需要管理员权限)...")
    try:
        subprocess.run(["taskkill", "/F", "/IM", "msedge.exe"], capture_output=True)
        time.sleep(1) # 等待释放
    except Exception as e:
        print(f"关闭 Edge 失败 (非致命): {e}")

def launch_edge_debug():
    edge_path = find_edge_path()
    if not edge_path:
        raise Exception("未找到 Microsoft Edge 安装路径")
        
    user_data_dir = os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\User Data")
    
    # 构建命令
    cmd = [
        edge_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir}"
    ]
    
    # Popen 不会阻塞，让浏览器独立运行
    subprocess.Popen(cmd)
    print("Edge 已启动 (调试模式)")

def main():
    print("=== 启动 Microsoft Edge 调试模式 ===")
    
    edge_path = find_edge_path()
    if not edge_path:
        print("错误: 未找到 Microsoft Edge 安装路径。")
        input("按回车键退出...")
        return

    print(f"找到 Edge: {edge_path}")
    
    print("\n正在启动 Edge...")
    print("注意: 如果 Edge 已经运行但没有开启调试端口，本脚本可能无法生效。")
    print("建议: 先手动关闭所有 Edge 窗口，然后再运行此脚本。")
    
    kill_edge()

    try:
        launch_edge_debug()
        print("\nEdge 已启动！")
        print("请保留此窗口或 Edge 窗口开启。")
        print("现在您可以运行上传脚本了。")
    except Exception as e:
        print(f"\n启动失败: {e}")

    print("\n(脚本将在 10 秒后自动退出，浏览器将保持运行)")
    time.sleep(10)

if __name__ == "__main__":
    main()
