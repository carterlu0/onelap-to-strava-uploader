"""
Strava API 客户端 - OAuth 2.0 认证 + 活动上传
完全替代原来的 Playwright 浏览器自动化方案
"""
import os
import json
import time
import hashlib
import secrets
import webbrowser
import requests
from urllib.parse import urlencode
from http.server import HTTPServer, BaseHTTPRequestHandler

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"
STRAVA_UPLOAD_URL = f"{STRAVA_API_BASE}/uploads"

CONFIG_FILE = "config.json"


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """本地 HTTP 服务器，接收 Strava OAuth 回调"""
    auth_code = None

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        query = parse_qs(urlparse(self.path).query)
        code = query.get("code", [None])[0]
        error = query.get("error", [None])[0]

        if code:
            OAuthCallbackHandler.auth_code = code
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body style='font-family:sans-serif;text-align:center;padding-top:50px;'>"
                "<h2>✅ 授权成功！</h2>"
                "<p>您可以关闭此页面，返回应用继续操作。</p>"
                "<script>window.close();</script>"
                "</body></html>".encode("utf-8")
            )
        elif error:
            self.send_response(400)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body style='font-family:sans-serif;text-align:center;padding-top:50px;'>"
                f"<h2>❌ 授权失败</h2><p>错误: {error}</p>"
                "</body></html>".encode("utf-8")
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # 静默日志


class StravaClient:
    """Strava API 客户端"""

    def __init__(self, client_id=None, client_secret=None, access_token=None,
                 refresh_token=None, expires_at=None):
        config = load_config().get("strava_api", {})

        self.client_id = client_id or config.get("client_id", "")
        self.client_secret = client_secret or config.get("client_secret", "")
        self.access_token = access_token or config.get("access_token")
        self.refresh_token = refresh_token or config.get("refresh_token")
        self.expires_at = expires_at or config.get("expires_at", 0)

        self.session = requests.Session()

    # ---------- OAuth 2.0 授权流程 ----------

    def get_authorization_url(self, redirect_uri="http://localhost:5001/callback",
                               scope="read,activity:read_all,activity:write"):
        """生成 Strava 授权页面 URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": scope,
        }
        return f"{STRAVA_AUTH_URL}?{urlencode(params)}"

    def authorize(self, redirect_port=5001, timeout=120):
        """
        交互式 OAuth 授权：
        1. 启动本地 HTTP 服务器监听回调
        2. 打开浏览器让用户授权
        3. 获取 authorization code
        4. 用 code 换取 token
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("请先在 config.json 中配置 strava_api.client_id 和 client_secret")

        redirect_uri = f"http://localhost:{redirect_port}/callback"

        # 启动本地回调服务器
        server = HTTPServer(("127.0.0.1", redirect_port), OAuthCallbackHandler)
        server.timeout = 1
        OAuthCallbackHandler.auth_code = None

        # 打开浏览器授权
        auth_url = self.get_authorization_url(redirect_uri=redirect_uri)
        print(f"\n正在打开浏览器进行 Strava 授权...")
        print(f"如果浏览器未自动打开，请手动访问:\n{auth_url}\n")
        webbrowser.open(auth_url)

        # 等待回调
        start = time.time()
        while OAuthCallbackHandler.auth_code is None:
            server.handle_request()
            if time.time() - start > timeout:
                server.server_close()
                raise TimeoutError("OAuth 授权超时，请重试")

        server.server_close()
        auth_code = OAuthCallbackHandler.auth_code

        # 用 code 换 token
        return self._exchange_code(auth_code)

    def _exchange_code(self, code):
        """用 authorization code 换取 access token"""
        resp = requests.post(STRAVA_TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
        }, timeout=15)

        if resp.status_code != 200:
            raise Exception(f"Token 交换失败: {resp.status_code} {resp.text}")

        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.expires_at = data["expires_at"]

        self._save_tokens()
        print("✅ Strava 授权成功！")
        return True

    # ---------- Token 管理 ----------

    def _save_tokens(self):
        """保存 token 到 config.json"""
        config = load_config()
        if "strava_api" not in config:
            config["strava_api"] = {}
        config["strava_api"]["access_token"] = self.access_token
        config["strava_api"]["refresh_token"] = self.refresh_token
        config["strava_api"]["expires_at"] = self.expires_at
        save_config(config)

    def refresh_access_token(self):
        """刷新过期的 access token"""
        if not self.refresh_token:
            return False

        resp = requests.post(STRAVA_TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }, timeout=15)

        if resp.status_code != 200:
            print(f"Token 刷新失败: {resp.text}")
            return False

        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        self.expires_at = data["expires_at"]
        self._save_tokens()
        return True

    def ensure_token_valid(self):
        """确保 access token 有效，过期则自动刷新"""
        if not self.access_token:
            raise Exception("未授权，请先完成 Strava OAuth 授权")

        # Strava token 有效期 6 小时，提前 5 分钟刷新
        if time.time() > (self.expires_at - 300):
            if not self.refresh_access_token():
                raise Exception("Token 已过期且刷新失败，请重新授权")
        return True

    # ---------- API 请求辅助 ----------

    def _request(self, method, url, **kwargs):
        """带认证的 API 请求，自动处理限流"""
        self.ensure_token_valid()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"

        for attempt in range(3):
            resp = self.session.request(method, url, headers=headers, **kwargs)
            if resp.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f"  Strava 限流，等待 {wait}s...", end="\r")
                time.sleep(wait)
                continue
            return resp
        return resp

    # ---------- 活动上传 ----------

    def upload_activity(self, filepath, name=None, description=None,
                        activity_type=None, trainer=False, commute=False,
                        data_type=None, external_id=None):
        """
        上传 FIT/GPX/TCX 文件到 Strava

        策略：提交 → 等 10s → 查一次状态。
              如果仍在 processing → 返回 "processing"（Strava 后台会完成）。
              只用 2 次 API 调用，彻底避免 Rate Limit Exceeded。

        参数:
            external_id: 外部 ID 用于去重

        返回:
            dict: {"status": "success"/"duplicate"/"processing"/"error", "activity_id": ..., "error": ...}
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")

        ext = os.path.splitext(filepath)[1].lower()
        data_type = data_type or {".fit": "fit", ".gpx": "gpx", ".tcx": "tcx"}.get(ext, "fit")

        params = {
            "data_type": data_type,
            "trainer": str(trainer).lower(),
            "commute": str(commute).lower(),
        }
        if name:
            params["name"] = name
        if description:
            params["description"] = description
        if activity_type:
            params["activity_type"] = activity_type
        if external_id:
            params["external_id"] = external_id

        # Step 1: 提交上传
        with open(filepath, "rb") as f:
            files = {"file": (os.path.basename(filepath), f)}
            print(f"正在提交 {os.path.basename(filepath)} 到 Strava...")
            resp = self._request("POST", STRAVA_UPLOAD_URL, data=params, files=files)

        if resp.status_code not in (200, 201):
            raise Exception(f"上传请求失败: {resp.status_code} {resp.text}")

        result = resp.json()
        upload_id = result.get("id")
        if not upload_id:
            return {"status": "error", "error": "未获取到 upload_id"}

        # Step 2: 等 10 秒后查一次
        print(f"  等待 Strava 处理...", end="\r")
        time.sleep(10)

        resp = self._request("GET", f"{STRAVA_UPLOAD_URL}/{upload_id}")
        if resp.status_code != 200:
            return {"status": "error", "error": f"查询状态失败 (HTTP {resp.status_code})"}

        data = resp.json()
        status = data.get("status", "")
        activity_id = data.get("activity_id")
        error = data.get("error", "")

        if status == "ready" and activity_id:
            print(f"✅ 上传成功！活动 ID: {activity_id}                           ")
            return {"status": "success", "activity_id": activity_id, "upload_id": upload_id}

        if status == "error":
            if self._is_duplicate_error(error):
                existing_id = self._extract_activity_id(error)
                print(f"ℹ️ 已存在重复活动 (activity/{existing_id})              ")
                return {"status": "duplicate", "activity_id": existing_id, "error": error}
            else:
                print(f"⚠️ Strava 处理异常: {error[:80]}")
                return {"status": "error", "error": error}

        # status in ("processing", "created") or unknown
        print(f"⏳ 已提交 (upload/{upload_id})，Strava 后台处理中            ")
        return {"status": "processing", "upload_id": upload_id, "message": "已提交，后台处理中"}

    @staticmethod
    def _is_duplicate_error(error: str) -> bool:
        """检测 Strava 返回的错误是否为重复活动"""
        if not error:
            return False
        error_lower = error.lower()
        duplicate_keywords = [
            "duplicate", "already exists", "already uploaded",
            "error processing",  # Strava 对重复活动的通用提示
            "重复", "已存在",
        ]
        return any(kw in error_lower for kw in duplicate_keywords)

    @staticmethod
    def _extract_activity_id(error: str) -> str:
        """从错误信息中提取已存在的活动 ID"""
        import re
        # 匹配 "duplicate of activity 123456" 等模式
        match = re.search(r'activity[_\s]*(\d{5,})', error, re.IGNORECASE)
        if match:
            return match.group(1)
        return ""


    # ---------- 查询 ----------

    def get_athlete(self):
        """获取当前授权用户信息"""
        resp = self._request("GET", f"{STRAVA_API_BASE}/athlete")
        if resp.status_code == 200:
            return resp.json()
        raise Exception(f"获取用户信息失败: {resp.text}")

    def get_activities(self, page=1, per_page=30):
        """获取已授权用户的活动列表"""
        resp = self._request("GET", f"{STRAVA_API_BASE}/athlete/activities",
                             params={"page": page, "per_page": per_page})
        if resp.status_code == 200:
            return resp.json()
        raise Exception(f"获取活动列表失败: {resp.text}")

    def is_authorized(self):
        """检查是否已授权"""
        return bool(self.access_token and self.refresh_token)


# ========== 便捷函数 ==========

def get_strava_client():
    """获取已配置的 Strava 客户端实例"""
    config = load_config().get("strava_api", {})
    return StravaClient(
        client_id=config.get("client_id"),
        client_secret=config.get("client_secret"),
    )


def needs_authorization():
    """检查是否需要 Strava OAuth 授权"""
    client = get_strava_client()
    return not client.is_authorized()


if __name__ == "__main__":
    # 测试：执行 OAuth 授权
    client = get_strava_client()
    if not client.client_id or not client.client_secret:
        print("请先在 config.json 中设置 strava_api.client_id 和 client_secret")
    else:
        client.authorize()
        user = client.get_athlete()
        print(f"已授权用户: {user.get('firstname')} {user.get('lastname')}")
