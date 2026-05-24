r"""
文件夹监听器 — 自动检测新 FIT 文件并上传 Strava
================================================
监听指定文件夹 (如 D:\QQfiles)，当有新的 .fit/.gpx/.tcx 文件出现时，
自动通过 Strava API 上传，无需任何手动操作。

典型用法:
  手机顽鹿 APP → 分享 FIT → QQ「我的电脑」
  → PC 端 QQ 自动保存到 D:\QQfiles
  → 本脚本自动检测 → 上传 Strava ✅

运行: python file_watcher.py
  (将 config.json 中 fit_watch_dir 设为要监听的文件夹)
"""
import os
import sys
import json
import time
import hashlib
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strava_api import StravaClient, get_strava_client

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_FILE = "config.json"
UPLOADED_LOG = "uploaded_files.json"


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


class FileWatcher:
    """
    文件夹监听器
    轮询检测新文件 → 等待写入完成 → 上传 Strava
    """

    def __init__(self, watch_dir, poll_interval=3):
        """
        watch_dir: 要监听的文件夹路径
        poll_interval: 轮询间隔 (秒)
        """
        self.watch_dir = Path(watch_dir)
        self.poll_interval = poll_interval
        self.known_files: dict[str, float] = {}  # filepath -> mtime
        self.uploaded: set[str] = self._load_uploaded()

        # Strava 客户端
        config = load_config().get("strava_api", {})
        self.strava = StravaClient(
            client_id=config.get("client_id"),
            client_secret=config.get("client_secret"),
        )

        # 支持的扩展名 — 只扫描 .fit 文件
        self.extensions = {".fit"}

    # ---------- 已上传记录 ----------

    def _load_uploaded(self) -> set[str]:
        """加载已上传文件记录 (用文件哈希去重)"""
        if os.path.exists(UPLOADED_LOG):
            try:
                with open(UPLOADED_LOG, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception:
                pass
        return set()

    def _save_uploaded(self):
        # 只保留最近 500 条记录，防止文件无限增长
        items = sorted(self.uploaded)
        if len(items) > 500:
            items = items[-500:]
            self.uploaded = set(items)
        with open(UPLOADED_LOG, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)

    def _file_hash(self, filepath: str) -> str:
        """用文件名+大小+前64KB内容生成可靠哈希，防止同名不同内容文件误判"""
        name = os.path.basename(filepath)
        try:
            size = os.path.getsize(filepath)
        except OSError:
            return ""
        hasher = hashlib.md5()
        hasher.update(name.encode())
        hasher.update(str(size).encode())
        try:
            with open(filepath, "rb") as f:
                hasher.update(f.read(65536))
        except Exception:
            pass
        return hasher.hexdigest()

    # ---------- 文件稳定性检测 ----------

    def _wait_file_stable(self, filepath: str, max_wait=30) -> bool:
        """
        等待文件写入完成 (大小不再变化)
        返回 True 表示文件已稳定，False 表示超时
        """
        start = time.time()
        last_size = -1
        stable_count = 0

        while time.time() - start < max_wait:
            try:
                current_size = os.path.getsize(filepath)
            except OSError:
                return False

            if current_size == last_size:
                stable_count += 1
                if stable_count >= 3:  # 连续 3 次大小不变
                    return True
            else:
                stable_count = 0
                last_size = current_size

            time.sleep(1)

        logger.warning(f"文件稳定性检测超时: {filepath}")
        return False

    # ---------- 文件扫描 ----------

    def _scan_new_files(self) -> list[str]:
        """扫描目录中新的 .fit 文件，返回新增/变更的文件路径列表"""
        new_files = []
        current_files = set()

        if not self.watch_dir.is_dir():
            return new_files

        for f in self.watch_dir.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() not in self.extensions:
                continue

            filepath = str(f.resolve())
            current_files.add(filepath)

            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue

            # 检测新文件或修改过的文件
            if filepath in self.known_files:
                if mtime > self.known_files[filepath]:
                    new_files.append(filepath)  # 文件被修改（可能正在写入）
            else:
                new_files.append(filepath)  # 全新文件

            self.known_files[filepath] = mtime

        # 清理：移除已不在目录中的文件记录（用户删除了旧文件）
        removed = set(self.known_files.keys()) - current_files
        for r in removed:
            del self.known_files[r]

        return new_files

    # ---------- 上传 ----------

    def _upload_file(self, filepath: str) -> bool:
        """上传单个文件到 Strava"""
        filename = os.path.basename(filepath)
        fh = self._file_hash(filepath)
        if fh in self.uploaded:
            logger.info(f"已上传过，跳过: {filename}")
            return True

        # 等待文件写入完成
        logger.info(f"等待文件写入完成: {filename}")
        if not self._wait_file_stable(filepath):
            logger.error(f"文件未稳定: {filepath}")
            return False

        file_size = os.path.getsize(filepath)
        logger.info(f"开始上传: {filename} ({file_size / 1024:.1f} KB)")

        # 使用文件名的 stem 作为 external_id，帮助 Strava 去重
        ext_id = os.path.splitext(filename)[0]

        try:
            result = self.strava.upload_activity(filepath, external_id=ext_id)

            if result.get("status") == "success":
                activity_id = result.get("activity_id")
                self.uploaded.add(fh)
                self._save_uploaded()
                logger.info(f"✅ 上传成功! Strava 活动 ID: {activity_id}")
                logger.info(f"   https://www.strava.com/activities/{activity_id}")
                return True

            elif result.get("status") == "duplicate":
                existing_id = result.get("activity_id", "")
                self.uploaded.add(fh)
                self._save_uploaded()
                logger.info(f"⏭️ 已在 Strava 存在，跳过: {filename}"
                           + (f" (activity/{existing_id})" if existing_id else ""))
                return True

            elif result.get("status") == "processing":
                # 文件已提交 Strava，后台会完成处理
                self.uploaded.add(fh)
                self._save_uploaded()
                logger.info(f"✅ 已提交 (upload/{result.get('upload_id')})，Strava 后台处理中")
                return True

            else:
                logger.error(f"❌ 上传失败: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"❌ 上传异常: {e}")
            return False

    # ---------- 主循环 ----------

    def run(self):
        """启动监听循环"""
        if not self.strava.is_authorized():
            logger.error("❌ Strava 未授权！请先在 Web UI 中完成 OAuth 授权")
            logger.error("   运行 start_app.bat → http://127.0.0.1:5000 → 连接 Strava")
            return

        # 验证授权有效
        try:
            athlete = self.strava.get_athlete()
            logger.info(f"✅ Strava 已连接: {athlete.get('firstname')} {athlete.get('lastname', '')}")
        except Exception as e:
            logger.error(f"❌ Strava 认证失败: {e}")
            return

        logger.info(f"🔍 开始监听文件夹: {self.watch_dir}")
        logger.info(f"   支持格式: {', '.join(self.extensions)}")
        logger.info(f"   已上传文件数: {len(self.uploaded)}")
        logger.info(f"   按 Ctrl+C 停止")
        logger.info("-" * 50)

        # 首次扫描：处理已有但未上传的文件
        logger.info("执行首次扫描...")
        existing = self._scan_new_files()
        if existing:
            logger.info(f"发现 {len(existing)} 个未上传文件，开始处理...")
            for fp in existing:
                self._upload_file(fp)

        # 持续监听
        try:
            while True:
                time.sleep(self.poll_interval)
                new_files = self._scan_new_files()
                for fp in new_files:
                    self._upload_file(fp)
                    # 文件间短暂休息，避免请求过于密集
                    time.sleep(2)

        except KeyboardInterrupt:
            logger.info("\n监听已停止。")


def main():
    config = load_config()

    # 从配置读取监听目录，默认 D:\QQfiles
    watch_dir = config.get("fit_watch_dir", "")
    if not watch_dir:
        # 检测常见 QQ 接收目录
        candidates = [
            r"D:\QQfiles",
            r"D:\QQ Files",
            os.path.expanduser(r"~\Documents\Tencent Files"),
            r"C:\QQfiles",
        ]
        for c in candidates:
            if os.path.isdir(c):
                watch_dir = c
                break

        if not watch_dir:
            print("=" * 60)
            print("  未找到 QQ 文件接收目录")
            print()
            print("  请在 config.json 中指定:")
            print('  "fit_watch_dir": "D:\\QQfiles"')
            print()
            print("  常见路径:")
            for c in candidates:
                print(f"    {c}")
            print("=" * 60)
            sys.exit(1)

    # 确保目录存在
    os.makedirs(watch_dir, exist_ok=True)

    print("=" * 60)
    print("  Magene-link 文件夹监听器")
    print("=" * 60)
    print(f"  监听目录: {watch_dir}")
    print(f"  手机操作: 顽鹿 APP → 分享 → QQ「我的电脑」")
    print(f"  自动上传 Strava，无需任何手动操作")
    print("=" * 60)
    print()

    watcher = FileWatcher(watch_dir)
    watcher.run()


if __name__ == "__main__":
    main()
