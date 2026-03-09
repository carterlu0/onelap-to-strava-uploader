import json
import sys
import os
import requests
from playwright.sync_api import sync_playwright
import time
from datetime import datetime

def load_config():
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

config = load_config()
STRAVA_USER = config.get("strava", {}).get("email", "")
STRAVA_PASS = config.get("strava", {}).get("password", "")

def download_fit(url, filename):
    print(f"正在下载 {url} 到 {filename}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.onelap.cn/"
    }
    try:
        r = requests.get(url, stream=True, headers=headers)
        r.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print("下载完成。")
        return True
    except Exception as e:
        print(f"下载失败: {e}")
        return False

def verify_upload(page, activity_info):
    if not activity_info:
        print("未提供活动信息，无法进行高级验证。")
        return False
        
    print("正在通过活动日志验证上传结果...")
    try:
        # Wait a bit before going to training log
        time.sleep(2)
        
        if "athlete/training" not in page.url:
            page.goto("https://www.strava.com/athlete/training")
        else:
            page.reload()
            
        # Wait for rows
        try:
            page.wait_for_selector(".training-activity-row", timeout=15000)
        except:
            print("未找到活动列表。")
            return False
            
        # Get first 10 activity rows
        rows = page.locator(".training-activity-row").all()
        if not rows:
            print("没有找到活动记录。")
            return False
            
        print(f"找到 {len(rows)} 条最近活动，正在匹配...")
        
        # activity_info['date'] is "YYYY-MM-DD HH:MM"
        act_date_str = activity_info.get('date', '')
        if not act_date_str:
            print("活动日期缺失。")
            return False
            
        dt = datetime.strptime(act_date_str, "%Y-%m-%d %H:%M")
        today = datetime.now()
        
        # Prepare match strings
        match_criteria = []
        
        # 1. Today/Yesterday logic
        if dt.date() == today.date():
            match_criteria.append("Today")
            match_criteria.append("今天")
        
        delta = today.date() - dt.date()
        if delta.days == 1:
            match_criteria.append("Yesterday")
            match_criteria.append("昨天")
            
        # 2. Specific date formats
        match_criteria.append(dt.strftime("%b %d, %Y"))
        match_criteria.append(f"{dt.year}/{dt.month}/{dt.day}")
        match_criteria.append(f"{dt.year}/{dt.month:02d}/{dt.day:02d}")
        match_criteria.append(f"{dt.year}年{dt.month}月{dt.day}日")
        
        # 3. Distance
        # Onelap uses 'totalDistance' (meters)
        dist_m = float(activity_info.get('totalDistance', 0) or activity_info.get('distance', 0))
        dist_km = 0.0
        dist_criteria = []
        if dist_m > 0:
            dist_km = dist_m / 1000.0
            
            # Generate candidates to handle rounding/truncation differences
            # Strava might show 0.65 km for 0.66 km source
            candidates = {dist_km, dist_km - 0.01, dist_km + 0.01}
            
            temp_criteria = []
            for val in candidates:
                if val < 0: continue
                # Standard rounding (1 and 2 decimals)
                temp_criteria.append(f"{val:.1f} km")
                temp_criteria.append(f"{val:.2f} km")
                # Truncation to 1 decimal (e.g. 0.66 -> 0.6 km)
                temp_criteria.append(f"{int(val * 10) / 10:.1f} km")
            
            # Deduplicate
            dist_criteria = list(dict.fromkeys(temp_criteria))
            
        print(f"匹配条件: 日期={match_criteria}, 距离={dist_criteria}")
        sys.stdout.flush()
        
        for i, row in enumerate(rows[:10]): # Check top 10
            text = row.inner_text()
            display_text = text.replace("\n", " | ")
            try:
                safe_text = display_text.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
                print(f"[{i+1}] {safe_text}") 
            except:
                print(f"[{i+1}] (无法打印内容)")
            
            # Check date/time match
            date_matched = False
            date_reason = "无日期匹配"
            for crit in match_criteria:
                if crit in text:
                    date_matched = True
                    date_reason = f"匹配: {crit}"
                    break
            
            # Check distance match
            dist_matched = False
            dist_reason = "无距离匹配"
            if dist_criteria:
                for d_crit in dist_criteria:
                    if d_crit in text:
                        dist_matched = True
                        dist_reason = f"匹配: {d_crit}"
                        break
                
                if not dist_matched and dist_km > 0.1:
                    dist_int = int(dist_km)
                    dist_int_str = f"{dist_int} km"
                    
                    if dist_km < 1.0:
                        dist_m_str = f"{int(dist_km * 1000)} m"
                        dist_decimal_1 = f"{dist_km:.1f} km"
                        
                        if dist_m_str in text:
                            dist_matched = True
                            dist_reason = f"匹配(米): {dist_m_str}"
                        elif dist_decimal_1 in text:
                            dist_matched = True
                            dist_reason = f"匹配(0.x): {dist_decimal_1}"
                    else:
                        if f" {dist_int}." in text or f" {dist_int_str}" in text:
                             dist_matched = True
                             dist_reason = f"匹配(整数): {dist_int_str}"
            else:
                dist_matched = True 
                dist_reason = "跳过(无源距离)"
                
            if date_matched and dist_matched:
                 print(f"   >>> 验证成功! ({date_reason}, {dist_reason})")
                 return True
            else:
                 fail_reasons = []
                 if not date_matched: fail_reasons.append(f"日期不符(期望: {match_criteria})")
                 if not dist_matched: fail_reasons.append(f"距离不符(期望: {dist_criteria})")
                 print(f"   >>> 未匹配: {'; '.join(fail_reasons)}")
                 
        print("在前 10 条记录中未找到完全匹配项。")
        return False
        
    except Exception as e:
        print(f"验证过程出错: {e}")
        return False
        
    except Exception as e:
        print(f"验证过程出错: {e}")
        return False

def perform_strava_upload(page, filepath, activity_info=None):
    """
    Common upload logic for Strava, used by both connection methods.
    Returns True if successful, False otherwise.
    """
    try:
        print("正在导航到 Strava 上传页面...")
        if "upload/select" not in page.url:
            page.goto("https://www.strava.com/upload/select")
        else:
            page.reload() # Reload if already there to be fresh
        
        # Check login
        if "login" in page.url or "onboarding" in page.url:
            print("当前未登录 Strava，请在弹出的窗口中手动登录...")
            # Wait a long time for manual login
            try:
                page.wait_for_url("**/dashboard**", timeout=300000)
                print("登录成功，继续上传...")
                page.goto("https://www.strava.com/upload/select")
            except:
                print("登录超时。")
                return False

        # Upload file
        print(f"正在上传 {filepath}...")
        
        # Wait for file input to be available
        try:
             page.wait_for_selector("input[type='file']", state="attached", timeout=10000)
        except:
             print("未找到文件输入框，尝试直接设置...")

        try:
             page.locator("input[type='file']").set_input_files(filepath)
        except Exception as e:
             print(f"直接设置文件输入失败: {e}")
             # Fallback to file chooser
             try:
                 with page.expect_file_chooser() as fc_info:
                     # Try different selectors for "Choose files" button
                     if page.get_by_text("Choose files").is_visible():
                        page.get_by_text("Choose files").click()
                     elif page.get_by_text("Select files").is_visible():
                        page.get_by_text("Select files").click()
                     else:
                        # Try generic button
                        page.locator("button", has_text="file").first.click()
                     
                 fc = fc_info.value
                 fc.set_files(filepath)
             except Exception as e2:
                 print(f"文件选择器也失败了: {e2}")
                 return False
        
        print("文件已选择。等待上传处理...")
        
        # Wait for "Save & View" button or similar
        try:
            print("等待 5 秒，让页面加载完成或自动跳转...")
            time.sleep(5)
            
            # Try to click Save just in case it's there and easy
            save_btn = None
            for selector in ["button:has-text('Save & View')", "button:has-text('保存并查看')", "[data-testid='save-activity-button']", ".save-button"]:
                if page.locator(selector).first.is_visible(timeout=2000):
                    print(f"尝试点击按钮: {selector}")
                    page.locator(selector).first.click(timeout=2000)
                    break
        except:
            pass

        # Go directly to verification
        if activity_info:
            print("直接跳转到活动日志进行验证...")
            if verify_upload(page, activity_info):
                return True
        
        print("高级验证未通过，尝试备用验证(检查是否跳转到了活动页面)...")
        try:
            if "/activities/" in page.url:
                print("当前页面是活动详情页，上传成功。")
                return True
        except:
            pass
            
        return False

    except Exception as e:
        print(f"执行上传动作时出错: {e}")
        return False

def upload_to_strava(filepath, user=None, password=None, activity_info=None):
    # 1. Try connecting to existing Edge (localhost:9222)
    print("尝试连接到已打开的 Edge 浏览器 (调试模式 9222 端口)...")
    try:
        with sync_playwright() as p:
            try:
                # Add timeout to connect, fail fast if not running
                browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=5000)
                context = browser.contexts[0]
                print("成功连接到现有 Edge 浏览器!")
                
                # Find existing Strava tab or create new
                page = None
                for p_page in context.pages:
                    if "strava.com" in p_page.url:
                        page = p_page
                        page.bring_to_front()
                        print("找到已存在的 Strava 标签页。")
                        break
                
                if not page:
                    print("未找到 Strava 标签页，创建新标签页...")
                    page = context.new_page()
                
                success = perform_strava_upload(page, filepath, activity_info)
                if success:
                    print("任务完成。")
                    # Do not close browser
                    # Just disconnect
                    browser.close() # For connect_over_cdp, close() just disconnects, doesn't kill browser
                    return True
                else:
                    print("通过现有 Edge 上传失败。")
                    return False
                    
            except Exception as e:
                print(f"连接现有 Edge 失败: {e}")
                print("原因可能是: 1. Edge 未启动; 2. 未使用调试端口 9222 启动。")
                print("正在尝试启动新的实例...")
                # Fall through to next method
    except Exception as e:
        print(f"Playwright 初始化失败: {e}")

    # 2. Try launching persistent context (requires closing Edge)
    # Modified: Ask user instead of force close
    print("\n无法连接到调试端口 (9222)。")
    print("这可能是因为 Edge 未以调试模式启动。")
    print("建议: 运行 'launch_edge.py' 来启动支持自动化的 Edge 窗口。")
    
    # Do not auto-close unless explicitly requested
    print("尝试启动一次性 Edge 实例 (如果不希望这样，请按 Ctrl+C 终止)...")
    time.sleep(3) # Give user time to abort

    use_edge_persistent = True
    
    if use_edge_persistent:
        user_data_dir = os.path.expanduser("~\\AppData\\Local\\Microsoft\\Edge\\User Data")
        try:
            # We must NOT use 'with sync_playwright() as p:' because exiting the context manager 
            # might clean up resources. We need to keep it alive if we want browser to stay open?
            # Actually, playwright context manager just stops the playwright server.
            # browser.close() is what closes the browser.
            
            p = sync_playwright().start()
            browser = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel="msedge",
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.pages[0]
            
            success = perform_strava_upload(page, filepath, activity_info)
            
            print("\n上传完成。")
            print("注意: 这是一个临时启动的 Edge 实例。")
            print("按回车键退出脚本并关闭浏览器...")
            try:
                input()
            except:
                time.sleep(60)

            browser.close()
            p.stop()
            return success

        except Exception as e:
            print(f"启动 Edge 实例失败: {e}")
            print("请确保已关闭所有 Edge 窗口。")

    # 3. Fallback to original logic (Standard Login)
    print("\n所有 Edge 自动化尝试均失败，尝试使用账号密码登录...")
    if not user or not password:
        conf = load_config()
        user = user or conf.get("strava", {}).get("email", "")
        password = password or conf.get("strava", {}).get("password", "")
    
    if not user or not password:
        print("缺少 Strava 凭据。")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            print("正在导航到 Strava 登录页面...")
            page.goto("https://www.strava.com/login")
            
            # Fill credentials
            print("正在填写凭据...")
            page.get_by_placeholder("Your Email").fill(user)
            page.get_by_placeholder("Password").fill(password)
            
            # Click Log In
            print("点击登录...")
            page.get_by_role("button", name="Log In").click()
            
            # Wait for login
            print("等待登录完成...")
            page.wait_for_url("**/dashboard**", timeout=60000)
            
            success = perform_strava_upload(page, filepath, activity_info)
            
            print("5 秒后关闭浏览器...")
            time.sleep(5)
            browser.close()
            return success
            
        except Exception as e:
            print(f"标准登录流程失败: {e}")
            browser.close()
            return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python upload_activity.py <index>")
        sys.exit(1)
    
    try:
        index = int(sys.argv[1]) - 1
    except:
        print("Invalid index")
        sys.exit(1)
        
    if not os.path.exists("activities.json"):
        print("activities.json not found")
        sys.exit(1)
        
    with open("activities.json", "r", encoding="utf-8") as f:
        activities = json.load(f)
    
    # Sort same way
    activities.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    if index < 0 or index >= len(activities):
        print("Index out of range")
        sys.exit(1)
        
    act = activities[index]
    durl = act.get("durl")
    if not durl:
        print("No download URL for this activity")
        sys.exit(1)
        
    filename = f"activity_{index+1}.fit"
    if download_fit(durl, filename):
        upload_to_strava(os.path.abspath(filename), activity_info=act)
