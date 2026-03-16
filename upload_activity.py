import json
import sys
import os
import requests
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
import time
from datetime import datetime
try:
    from launch_edge import kill_edge, launch_edge_debug
except ImportError:
    # Fallback if launch_edge.py is not found or has errors
    def kill_edge(): pass
    def launch_edge_debug(): pass

def load_config():
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

config = load_config()
STRAVA_USER = config.get("strava", {}).get("email", "")
STRAVA_PASS = config.get("strava", {}).get("password", "")

def download_fit(url, filename):
    if isinstance(url, str):
        url = url.strip()
    base = "https://u.onelap.cn/"
    full_url = url
    if isinstance(url, str) and url and not url.lower().startswith(("http://", "https://")):
        full_url = urljoin(base, url)

    print(f"正在下载 {full_url} 到 {filename}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": base
    }
    try:
        onelap_user = config.get("onelap", {}).get("username")
        onelap_pass = config.get("onelap", {}).get("password")
        if onelap_user and onelap_pass:
            from fetch_onelap import OnelapClient
            client = OnelapClient(onelap_user, onelap_pass)
            if client.login():
                r = client.session.get(full_url, stream=True, headers=headers, timeout=30)
            else:
                r = requests.get(full_url, stream=True, headers=headers, timeout=30)
        else:
            r = requests.get(full_url, stream=True, headers=headers, timeout=30)
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
            print("正在等待保存按钮或自动跳转...")
            # 缩短初始等待，改用轮询检测
            # Check for success indicators aggressively
            start_time = time.time()
            while time.time() - start_time < 15: # 最多等待15秒
                # 1. Check for Save button
                for selector in ["button:has-text('Save & View')", "button:has-text('保存并查看')", "[data-testid='save-activity-button']", ".save-button"]:
                    if page.locator(selector).first.is_visible(timeout=100):
                        print(f"发现按钮: {selector}，点击保存...")
                        page.locator(selector).first.click()
                        time.sleep(1) # Give it a moment to react
                        break
                
                # 2. Check for redirect to activity page (success)
                if "/activities/" in page.url and "upload" not in page.url:
                    print("检测到已跳转至活动详情页，上传成功。")
                    return True
                    
                # 3. Check for "duplicate" message (common fast failure/success case)
                if page.get_by_text("duplicate of").is_visible(timeout=100) or page.get_by_text("重复").is_visible(timeout=100):
                    print("检测到重复活动提示，视为成功。")
                    return True

                time.sleep(0.5) # Poll interval
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
    # 1. Try connecting to Edge (localhost:9222)
    # If fails, kill all Edge and relaunch in debug mode, then connect
    print("尝试连接到已打开的 Edge 浏览器 (调试模式 9222 端口)...")
    
    with sync_playwright() as p:
        browser = None
        try:
            # First attempt: Connect to existing
            browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=3000)
            print("成功连接到现有 Edge 浏览器!")
        except Exception as e:
            print(f"连接现有 Edge 失败: {e}")
            print("正在尝试关闭所有 Edge 窗口并重新启动 (调试模式)...")
            
            try:
                kill_edge()
                launch_edge_debug()
                print("等待 Edge 启动 (5秒)...")
                time.sleep(5)
                browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=10000)
                print("成功连接到重启后的 Edge 浏览器!")
            except Exception as e2:
                print(f"重启 Edge 并连接失败: {e2}")
        
        if browser:
            try:
                context = browser.contexts[0]
                
                # 1. 尝试找到并聚焦同步工具页面 (Web UI)
                web_ui_page = None
                for p_page in context.pages:
                    if "127.0.0.1:5000" in p_page.url or "localhost:5000" in p_page.url:
                        web_ui_page = p_page
                        break
                
                if web_ui_page:
                    print("找到同步工具页面，将其置于前台...")
                    try:
                        web_ui_page.bring_to_front()
                    except:
                        pass # 忽略聚焦失败

                # Find existing Strava tab or create new
                page = None
                for p_page in context.pages:
                    if "strava.com" in p_page.url:
                        page = p_page
                        # page.bring_to_front() # 不要主动前置 Strava
                        print("找到已存在的 Strava 标签页 (后台)。")
                        break
                
                if not page:
                    print("未找到 Strava 标签页，创建新标签页...")
                    page = context.new_page()
                    # 新建标签页会自动前置，如果存在 Web UI，需要重新切回去
                    if web_ui_page:
                        try:
                            web_ui_page.bring_to_front()
                            print("  (已重新切回同步工具页面)")
                        except:
                            pass
                
                success = perform_strava_upload(page, filepath, activity_info)
                browser.close() # Just disconnects for connect_over_cdp
                if success:
                    print("任务完成。")
                    return True
                else:
                    print("通过 Edge 自动化上传失败。")
            except Exception as e:
                print(f"操作 Edge 浏览器时出错: {e}")
                if browser:
                    try: browser.close()
                    except: pass

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
