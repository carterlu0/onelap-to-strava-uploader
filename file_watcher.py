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
from to_tcx import fit_to_tcx  # FIT → TCX 转换（含 GCJ-02 修正 + 功率/心率）

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

        # GCJ-02 修正开关（默认开启）
        full_config = load_config()
        self.fix_gcj02 = full_config.get("fit_fix_gcj02", True)

        # 只扫描 .fit 文件 (Magene 码表导出格式)
        self.extensions = {".fit"}

    # ---------- 已上传记录 ----------

    def _load_uploaded(self) -> dict[str, str]:
        """
        加载已上传记录: { external_id -> md5_hash }
        明文格式，可手动编辑删除某条记录以实现重传
        """
        if os.path.exists(UPLOADED_LOG):
            try:
                with open(UPLOADED_LOG, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                    # 兼容旧格式 (list → dict)
                    if isinstance(data, list):
                        legacy = {}
                        for i, h in enumerate(data):
                            legacy[f"legacy_{i}"] = h
                        return legacy
            except Exception:
                pass
        return {}

    def _save_uploaded(self):
        """保存已上传记录，限制 500 条。仅用文件名作为 key，值存 'ok'。"""
        if len(self.uploaded) > 500:
            keys = list(self.uploaded.keys())[-500:]
            self.uploaded = {k: self.uploaded[k] for k in keys}
        with open(UPLOADED_LOG, "w", encoding="utf-8") as f:
            json.dump(self.uploaded, f, indent=2, ensure_ascii=False)

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
        """上传 .fit 文件到 Strava。先转 TCX 修正 GCJ-02 + 保留功率/心率。"""
        filename = os.path.basename(filepath)
        ext = os.path.splitext(filename)[1].lower()
        ext_id = os.path.splitext(filename)[0]

        # 本地记录检查
        if ext_id in self.uploaded:
            logger.info(f"本地记录已存在，跳过: {filename}")
            logger.info(f"  💡 如需重传，请从 uploaded_files.json 中删除 '{ext_id}' 条目")
            return True

        # 等待文件写入完成
        logger.info(f"等待文件写入完成: {filename}")
        if not self._wait_file_stable(filepath):
            logger.error(f"文件未稳定: {filepath}")
            return False

        # 如果是 .fit 文件且开启 GCJ-02 修正 → 转为 TCX 上传
        upload_path = filepath
        temp_tcx = None
        if ext == '.fit' and self.fix_gcj02:
            import tempfile as tf
            temp_tcx = os.path.join(tf.gettempdir(), f"_tcx_{ext_id}.tcx")
            tcx = fit_to_tcx(filepath, fix_gcj02=True)
            if tcx:
                with open(temp_tcx, 'w', encoding='utf-8') as f:
                    f.write(tcx)
                upload_path = temp_tcx
                logger.info(f"  📍 FIT → TCX: GCJ-02 已修正 + 功率/心率已保留")
            else:
                logger.info(f"  ⚠️ TCX 转换失败，尝试直接上传 FIT")

        file_size = os.path.getsize(upload_path)
        logger.info(f"开始上传: {os.path.basename(upload_path)} ({file_size / 1024:.1f} KB)")

        try:
            result = self.strava.upload_activity(upload_path, external_id=ext_id)

            if result.get("status") == "success":
                activity_id = result.get("activity_id")
                self.uploaded[ext_id] = result.get("upload_id", "ok")  # 只记录已上传
                self._save_uploaded()
                logger.info(f"✅ 上传成功! Strava 活动 ID: {activity_id}")
                logger.info(f"   https://www.strava.com/activities/{activity_id}")
                return True

            elif result.get("status") in ("duplicate", "processing"):
                self.uploaded[ext_id] = "ok"
                self._save_uploaded()
                logger.info(f"✅ 已提交/已存在，记录完成: {filename}")
                return True

            else:
                logger.error(f"❌ 上传失败: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"❌ 上传异常: {e}")
            return False
        finally:
            # 清理临时 TCX 文件
            if temp_tcx and os.path.exists(temp_tcx):
                try:
                    os.remove(temp_tcx)
                except OSError:
                    pass

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
