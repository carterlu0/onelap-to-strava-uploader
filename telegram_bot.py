"""
Telegram Bot — 手机端 Onelap → Strava 自动上传
==============================================
使用方式:
  1. 在 Telegram 中找 @BotFather 创建 Bot，获取 Token
  2. 将 Token 填入 config.json 的 telegram.bot_token
  3. 运行此脚本 (保持后台运行)
  4. 骑行结束后，在手机 Onelap APP 中「分享 FIT 文件」→ 选择 Telegram → 发送给 Bot
  5. Bot 自动上传到 Strava 并回复结果

依赖: pip install python-telegram-bot
"""
import os
import sys
import json
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strava_api import StravaClient, get_strava_client

# 配置日志
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

FIT_DIR = "fit_files"
os.makedirs(FIT_DIR, exist_ok=True)

# ---------- 检查依赖 ----------
try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
except ImportError:
    print("=" * 60)
    print("  需要安装 python-telegram-bot")
    print("  请运行: pip install python-telegram-bot")
    print("=" * 60)
    sys.exit(1)

# ---------- 配置 ----------

def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


# ---------- Strava 上传 ----------

def upload_to_strava(filepath: str, filename: str) -> dict:
    """使用 Strava API 上传 FIT 文件"""
    config = load_config().get("strava_api", {})
    client = StravaClient(
        client_id=config.get("client_id"),
        client_secret=config.get("client_secret"),
    )

    if not client.is_authorized():
        return {"status": "error", "error": "Strava 未授权，请先在 Web UI 中完成 OAuth 授权"}

    try:
        result = client.upload_activity(filepath)
        return result
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------- Bot 处理器 ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    await update.message.reply_text(
        "🚴 <b>Magene-link → Strava Bot</b>\n\n"
        "直接将 FIT 文件发送给我，我会自动上传到你的 Strava 账号。\n\n"
        "📱 <b>使用方式:</b>\n"
        "1. 在顽鹿运动 APP 中找到活动\n"
        "2. 点击「分享」→ 选择 Telegram → 发送给我\n"
        "3. 等待上传完成 ✅\n\n"
        "/status - 查看 Strava 连接状态\n"
        "/help  - 查看帮助",
        parse_mode="HTML"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /help 命令"""
    await update.message.reply_text(
        "💡 <b>使用帮助</b>\n\n"
        "1️⃣ 骑行结束后，Magene 码表会自动同步数据到手机顽鹿运动 APP\n"
        "2️⃣ 打开顽鹿运动 APP → 找到刚才的骑行记录\n"
        "3️⃣ 点击右上角「分享」图标\n"
        "4️⃣ 选择 Telegram → 找到本 Bot → 发送\n"
        "5️⃣ 等待几秒，Bot 会自动上传到 Strava 并回复链接\n\n"
        "⚠️ 如上传失败请检查:\n"
        "• Strava 授权是否过期 (/status)\n"
        "• 文件是否为 .fit 格式",
        parse_mode="HTML"
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /status 命令"""
    config = load_config().get("strava_api", {})
    client = StravaClient(
        client_id=config.get("client_id"),
        client_secret=config.get("client_secret"),
    )

    if client.is_authorized():
        try:
            athlete = client.get_athlete()
            await update.message.reply_text(
                f"✅ <b>Strava 已连接</b>\n"
                f"👤 {athlete.get('firstname')} {athlete.get('lastname', '')}\n"
                f"📍 {athlete.get('city', '')} {athlete.get('country', '')}\n\n"
                f"✅ 可以正常接收 FIT 文件",
                parse_mode="HTML"
            )
        except Exception as e:
            await update.message.reply_text(
                f"⚠️ <b>Token 可能已过期</b>\n"
                f"请在 Web UI 中重新授权: http://127.0.0.1:5000\n\n"
                f"错误: {e}",
                parse_mode="HTML"
            )
    else:
        await update.message.reply_text(
            "❌ <b>Strava 未连接</b>\n\n"
            "请先在电脑上完成 OAuth 授权:\n"
            "1. 运行 start_app.bat\n"
            "2. 打开 http://127.0.0.1:5000\n"
            "3. 点击「连接 Strava」",
            parse_mode="HTML"
        )


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户发送的文件"""
    message = update.message

    # 检查文件类型
    if message.document:
        file_obj = message.document
        filename = file_obj.file_name or "activity.fit"
    else:
        await message.reply_text("⚠️ 请发送 .fit / .gpx / .tcx 格式的运动文件")
        return

    # 验证扩展名
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".fit", ".gpx", ".tcx"):
        await message.reply_text(
            f"⚠️ 不支持的文件格式: {ext}\n"
            f"请发送 .fit / .gpx / .tcx 格式的文件",
        )
        return

    # 发送处理中提示
    status_msg = await message.reply_text(
        f"📥 收到 <b>{filename}</b>\n"
        f"📏 大小: {file_obj.file_size / 1024:.1f} KB\n\n"
        f"⏳ 正在下载并上传到 Strava...",
        parse_mode="HTML"
    )

    # 下载文件
    filepath = os.path.join(FIT_DIR, filename)
    try:
        tg_file = await context.bot.get_file(file_obj.file_id)
        await tg_file.download_to_drive(filepath)
        logger.info(f"Downloaded: {filename} ({os.path.getsize(filepath)} bytes)")
    except Exception as e:
        logger.error(f"Download failed: {e}")
        await status_msg.edit_text(f"❌ 文件下载失败: {e}", parse_mode="HTML")
        return

    # 上传到 Strava
    try:
        result = upload_to_strava(filepath, filename)

        if result.get("status") == "success":
            activity_id = result.get("activity_id")
            strava_url = f"https://www.strava.com/activities/{activity_id}"
            await status_msg.edit_text(
                f"✅ <b>上传成功！</b>\n\n"
                f"📄 {filename}\n"
                f"🔗 <a href='{strava_url}'>在 Strava 中查看</a>\n"
                f"🆔 活动 ID: {activity_id}",
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            logger.info(f"Upload success: {filename} -> activity {activity_id}")

        elif result.get("status") == "processing":
            await status_msg.edit_text(
                f"⏳ <b>已提交处理</b>\n\n"
                f"📄 {filename}\n"
                f"Strava 正在后台处理中，请稍后查看。",
                parse_mode="HTML",
            )
            logger.info(f"Upload processing: {filename}")

        else:
            error = result.get("error", "未知错误")
            await status_msg.edit_text(
                f"❌ <b>上传失败</b>\n\n"
                f"📄 {filename}\n"
                f"错误: {error}\n\n"
                f"💡 请检查 Strava 授权状态: /status",
                parse_mode="HTML",
            )
            logger.error(f"Upload failed: {filename} - {error}")

    except Exception as e:
        logger.error(f"Upload exception: {e}")
        await status_msg.edit_text(
            f"❌ <b>上传异常</b>\n\n{str(e)}\n\n"
            f"💡 请检查服务状态",
            parse_mode="HTML",
        )


# ---------- 启动 ----------

def main():
    config = load_config()
    bot_token = config.get("telegram", {}).get("bot_token", "")

    if not bot_token:
        print("=" * 60)
        print("  需要配置 Telegram Bot Token")
        print()
        print("  获取方式:")
        print("  1. 在 Telegram 中搜索 @BotFather")
        print("  2. 发送 /newbot 创建 Bot")
        print("  3. 复制 Token 到 config.json:")
        print('     "telegram": { "bot_token": "你的Token" }')
        print("=" * 60)
        sys.exit(1)

    # 检查 Strava 授权
    strava = get_strava_client()
    if not strava.is_authorized():
        logger.warning("Strava 未授权！请先在 Web UI 中完成 OAuth")
        logger.warning("运行 start_app.bat → 打开 http://127.0.0.1:5000 → 连接 Strava")

    # 构建 Application
    app = Application.builder().token(bot_token).build()

    # 注册处理器
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    print("=" * 60)
    print("  🚴 Magene-link → Strava Telegram Bot")
    print("=" * 60)
    print()
    print(f"  Bot 已启动！在 Telegram 中向你的 Bot 发送消息")
    print()
    print("  📱 手机端操作:")
    print("     顽鹿运动 APP → 分享 FIT → Telegram → 你的 Bot")
    print()
    print("  按 Ctrl+C 停止")
    print("=" * 60)

    # 开始轮询
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
