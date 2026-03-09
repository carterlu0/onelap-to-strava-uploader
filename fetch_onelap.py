import requests
import hashlib
import json
import os

# Load config
def load_config():
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

config = load_config()
USERNAME = config.get("onelap", {}).get("username", "")
PASSWORD = config.get("onelap", {}).get("password", "")

def get_md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

class OnelapClient:
    def __init__(self, username=None, password=None):
        self.session = requests.Session()
        self.base_url = "https://www.onelap.cn"
        self.token = None
        
        # Load from config if not provided
        if not username or not password:
            conf = load_config()
            self.username = username or conf.get("onelap", {}).get("username", "")
            self.password = password or conf.get("onelap", {}).get("password", "")
        else:
            self.username = username
            self.password = password

    def login(self):
        if not self.username or not self.password:
            print("Username or password missing.")
            return False

        url = f"{self.base_url}/api/login"
        payload = {
            "account": self.username,
            "password": get_md5(self.password),
            "client_type": "pc",
            "app_version": "1.0.0",
            "language": "en"
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    result_list = data.get("data", [])
                    if result_list:
                        self.token = result_list[0].get("token")
                        return True
        except Exception as e:
            print(f"Login error: {e}")
        return False

    def get_activities(self, limit=30):
        url = "https://u.onelap.cn/analysis/list"
        all_activities = []
        page = 1
        page_size = 20 # Onelap usually returns 20 items per page
        
        # Calculate how many pages we need to fetch to get 'limit' items
        # e.g. limit=30, page_size=20 -> need 2 pages
        
        while len(all_activities) < limit:
            try:
                # Session cookies are automatically handled
                response = self.session.get(url, params={"page": page})
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == 200:
                        page_items = data.get("data", [])
                        if not page_items:
                            break # No more data
                        all_activities.extend(page_items)
                        page += 1
                    else:
                        break # Error
                else:
                    break # Http error
            except Exception as e:
                print(f"Fetch error: {e}")
                break
                
        return all_activities[:limit]

if __name__ == "__main__":
    client = OnelapClient()
    if client.login():
        activities = client.get_activities()
        # Save to file for next step
        with open("activities.json", "w", encoding="utf-8") as f:
            json.dump(activities, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(activities)} activities to activities.json")
    else:
        print("Login failed")
