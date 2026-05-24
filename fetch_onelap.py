"""
Onelap (顽鹿) API 客户端
支持:
  1. 旧版 API: /api/login + /analysis/list (兼容)
  2. 新版 OTM API: 带 MD5 签名的 /api/otm/ride_record/list
  3. FIT 文件下载 (含重试 + 会话认证)
"""
import requests
import hashlib
import json
import os
import time
import random
import string
from urllib.parse import urljoin

# ---- OTM API 签名常量 ----
OTM_SIGN_KEY = "fe9f8382418fcdeb136461cac6acae7b"


def load_config():
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def generate_nonce(length=16):
    """生成随机 nonce 字符串"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def sign_otm_request(params: dict) -> dict:
    """
    为 OTM API 请求签名
    返回需要添加的 headers: {nonce, timestamp, sign}
    """
    nonce = generate_nonce()
    timestamp = str(int(time.time() * 1000))

    # 扁平化参数: 列表/字典 → JSON 字符串
    flat_params = {}
    for k, v in params.items():
        if isinstance(v, (list, dict)):
            flat_params[k] = json.dumps(v, separators=(',', ':'))
        else:
            flat_params[k] = str(v)

    # 添加签名元数据
    flat_params["nonce"] = nonce
    flat_params["timestamp"] = timestamp

    # 按 key 排序
    sorted_keys = sorted(flat_params.keys())
    # 构建签名字符串
    sign_str = "&".join(f"{k}={flat_params[k]}" for k in sorted_keys)
    sign_str += f"&key={OTM_SIGN_KEY}"

    sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()

    return {
        "nonce": nonce,
        "timestamp": timestamp,
        "sign": sign,
    }


class OnelapClient:
    def __init__(self, username=None, password=None):
        self.session = requests.Session()
        self.base_url = "https://www.onelap.cn"
        self.otm_url = "https://otm.onelap.cn"
        self.u_base_url = "https://u.onelap.cn"
        self.token = None
        self.uid = None

        # 设置通用请求头
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        })

        # Load from config if not provided
        if not username or not password:
            conf = load_config()
            self.username = username or conf.get("onelap", {}).get("username", "")
            self.password = password or conf.get("onelap", {}).get("password", "")
        else:
            self.username = username
            self.password = password

    # ===================== 认证 =====================

    def login(self):
        """
        登录 Onelap with request signing

        OTM API 要求登录请求也包含签名头 (nonce, timestamp, sign)。
        """
        if not self.username or not self.password:
            print("Username or password missing.")
            return False

        url = f"{self.base_url}/api/login"
        password_md5 = get_md5(self.password)

        # 构建签名参数 (按字母序)
        timestamp = str(int(time.time()))
        nonce = generate_nonce(16)
        sign_str = (
            f"account={self.username}&"
            f"nonce={nonce}&"
            f"password={password_md5}&"
            f"timestamp={timestamp}&"
            f"key={OTM_SIGN_KEY}"
        )
        sign = get_md5(sign_str)

        payload = {
            "account": self.username,
            "password": password_md5,
            "client_type": "pc",
            "app_version": "1.0.0",
            "language": "en"
        }
        headers = {
            "Content-Type": "application/json",
            "nonce": nonce,
            "timestamp": timestamp,
            "sign": sign,
        }

        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    result_list = data.get("data", [])
                    if result_list:
                        self.token = result_list[0].get("token")
                        # 提取 UID (OTM API 需要)
                        userinfo = result_list[0].get("userinfo", {})
                        self.uid = str(userinfo.get("uid", ""))
                        print(f"✅ Onelap 登录成功 (uid={self.uid})")
                        return True
                    else:
                        print("Login response has no data")
                else:
                    print(f"Login API error: code={data.get('code')}, msg={data.get('msg', '')}")
            else:
                print(f"Login HTTP error: {response.status_code}")
        except Exception as e:
            print(f"Login error: {e}")
        return False

    # ===================== 活动列表 =====================

    def get_activities(self, limit=30):
        """
        获取活动列表 - 使用 OTM API
        (旧版 /analysis/list 已于 2026 年下线，返回 404)
        """
        # 先尝试 OTM API
        try:
            activities = self._get_activities_otm(limit)
            if activities:
                return activities
        except Exception as e:
            print(f"OTM API 获取失败: {e}")

        # 旧 API 已下线 (404)，直接返回空
        print("⚠️ Onelap 旧版 API 已下线，无法获取活动列表。")
        print("   建议使用「本地上传」功能直接上传 FIT 文件。")
        return []

    def _get_activities_otm(self, limit=30):
        """
        OTM API: POST https://otm.onelap.cn/api/otm/ride_record/list
        认证方式: Authorization header + ouid Cookie
        """
        if not self.token or not self.uid:
            if not self.login():
                raise Exception("OTM API 需要登录")

        url = f"{self.otm_url}/api/otm/ride_record/list"
        all_activities = []
        page = 1

        while len(all_activities) < limit:
            payload = {"page": page, "limit": min(20, limit - len(all_activities))}

            headers = {
                "Content-Type": "application/json",
                "Authorization": self.token,
            }

            # OTM API 需要 ouid cookie
            cookies = {"ouid": self.uid}

            try:
                response = self.session.post(
                    url, json=payload, headers=headers,
                    cookies=cookies, timeout=15
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == 200:
                        page_items = data.get("data", {}).get("list", [])
                        if not isinstance(page_items, list):
                            page_items = data.get("data", [])
                            if isinstance(page_items, dict):
                                page_items = page_items.get("list", [])
                        if not page_items:
                            break
                        all_activities.extend(page_items)
                        page += 1
                    else:
                        print(f"OTM API error: code={data.get('code')}, msg={data.get('msg', data.get('message', ''))}")
                        break
                elif response.status_code == 403:
                    print(f"OTM API 403 Forbidden - token/uid 无效，尝试重新登录...")
                    # 重新登录并重试一次
                    if self.login():
                        headers["Authorization"] = self.token
                        cookies["ouid"] = self.uid
                        response = self.session.post(url, json=payload, headers=headers, cookies=cookies, timeout=15)
                        if response.status_code == 200:
                            data = response.json()
                            if data.get("code") == 200:
                                page_items = data.get("data", {}).get("list", [])
                                if not page_items:
                                    break
                                all_activities.extend(page_items)
                                continue
                    break
                else:
                    print(f"OTM API HTTP {response.status_code}: {response.text[:200]}")
                    break
            except Exception as e:
                print(f"OTM API fetch error: {e}")
                break

        return all_activities[:limit]

    # ===================== FIT 下载 =====================

    def download_fit(self, url, filepath, max_retries=2):
        """
        下载 FIT 文件（带重试和会话认证）

        参数:
            url: 下载链接 (durl 字段)
            filepath: 保存路径
            max_retries: 最大重试次数

        返回:
            bool: 是否下载成功
        """
        if not url:
            print("下载链接为空")
            return False

        # 确保是完整 URL
        if not url.startswith(("http://", "https://")):
            url = urljoin(self.u_base_url, url)

        # 确保已登录
        if not self.token:
            self.login()

        headers = {
            "Referer": f"{self.u_base_url}/",
        }

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    wait = 2 ** attempt
                    print(f"  重试 {attempt}/{max_retries}，等待 {wait}s...")
                    time.sleep(wait)
                    # 重试前重新登录
                    self.login()

                print(f"  正在下载: {os.path.basename(filepath)}")
                resp = self.session.get(url, headers=headers,
                                        stream=True, timeout=60)

                if resp.status_code == 200:
                    content_type = resp.headers.get("Content-Type", "")
                    content = resp.content

                    # 验证是否为有效的 FIT 文件
                    if len(content) < 100:
                        print(f"  文件太小 ({len(content)} bytes)，可能无效")
                        continue

                    # FIT 文件头检查: 前2字节通常是 .FIT header
                    if not content.startswith(b'\x0e\x10'):
                        # 检查是否被重定向到了 HTML 页面
                        if content.startswith(b'<!') or content.startswith(b'<html'):
                            print(f"  响应为 HTML 页面，非 FIT 文件 (可能 token 过期)")
                            continue

                    with open(filepath, 'wb') as f:
                        f.write(content)
                    print(f"  ✅ 下载成功 ({len(content)} bytes)")
                    return True
                else:
                    print(f"  HTTP {resp.status_code}")

            except requests.exceptions.Timeout:
                print(f"  下载超时")
            except Exception as e:
                print(f"  下载异常: {e}")

        print(f"  ❌ 下载失败 (已重试 {max_retries} 次)")
        return False

    def download_activity_fit(self, activity, save_dir="."):
        """
        下载单条活动的 FIT 文件

        参数:
            activity: 活动数据 dict
            save_dir: 保存目录

        返回:
            str: 保存的文件路径，失败返回 None
        """
        activity_id = activity.get("id", "unknown")
        durl = activity.get("durl", "")

        if not durl:
            print(f"活动 {activity_id} 没有下载链接")
            return None

        filename = f"activity_{activity_id}.fit"
        filepath = os.path.join(save_dir, filename)

        if self.download_fit(durl, filepath):
            return filepath
        return None

    # ===================== 活动详情 =====================

    def get_activity_detail(self, activity_id):
        """获取活动详情（可能包含更多数据）"""
        url = f"{self.u_base_url}/analysis/detail"
        try:
            resp = self.session.get(url, params={"id": activity_id}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 200:
                    return data.get("data")
        except Exception as e:
            print(f"获取活动详情失败: {e}")
        return None


if __name__ == "__main__":
    client = OnelapClient()
    if client.login():
        activities = client.get_activities()
        with open("activities.json", "w", encoding="utf-8") as f:
            json.dump(activities, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(activities)} activities to activities.json")
    else:
        print("Login failed")
