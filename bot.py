from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from camera import CameraError, camera_available, capture_photo, record_video, restart_camera
from storage import get_last_command, init_db, log_command


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0") or "0")
MINI_APP_URL = os.getenv("MINI_APP_URL", "").strip()
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0") or "0")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000") or "8000")
DB_PATH = os.getenv("DB_PATH", "camera_controller.sqlite3")
TEMP_DIR = os.getenv("TEMP_DIR", "temp")
START_API = os.getenv("START_API", "true").lower() in {"1", "true", "yes", "on"}
START_TIME = datetime.now(timezone.utc)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("camera-controller")


def is_owner(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id == OWNER_TELEGRAM_ID)


def owner_keyboard() -> InlineKeyboardMarkup:
    panel_url = MINI_APP_URL or f"http://127.0.0.1:{API_PORT}/webapp/"
    open_panel_button = (
        InlineKeyboardButton("🌐 Open Panel", web_app=WebAppInfo(panel_url))
        if panel_url.startswith("https://")
        else InlineKeyboardButton("🌐 Open Panel", url=panel_url)
    )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📸 Photo", callback_data="photo")],
            [
                InlineKeyboardButton("🎥 Video 5s", callback_data="video:5"),
                InlineKeyboardButton("🎥 Video 10s", callback_data="video:10"),
            ],
            [InlineKeyboardButton("🎥 Video 30s", callback_data="video:30")],
            [InlineKeyboardButton("📡 Status", callback_data="status")],
            [open_panel_button],
        ]
    )


def format_uptime() -> str:
    seconds = int((datetime.now(timezone.utc) - START_TIME).total_seconds())
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def status_text() -> str:
    last = get_last_command(DB_PATH)
    camera_ok = camera_available(CAMERA_INDEX)
    last_command = "none"
    if last:
        last_command = f"{last['command']} ({last['status']}, {last['created_at']})"

    return (
        "📡 Camera laptop status\n"
        "Online: yes\n"
        f"Camera: {'available' if camera_ok else 'unavailable'}\n"
        f"Last command: {last_command}\n"
        f"Uptime: {format_uptime()}"
    )


async def reject_unauthorized(update: Update) -> None:
    if update.callback_query:
        await update.callback_query.answer("Forbidden", show_alert=False)
    logger.warning("Ignored unauthorized user: %s", update.effective_user.id if update.effective_user else None)


async def run_camera_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    command: str,
    duration: int | None = None,
    source: str = "telegram",
) -> None:
    if not is_owner(update):
        await reject_unauthorized(update)
        return

    chat_id = update.effective_chat.id if update.effective_chat else OWNER_TELEGRAM_ID
    user_id = update.effective_user.id if update.effective_user else OWNER_TELEGRAM_ID
    command_label = command if command != "video" else f"video {duration or 5}"
    log_command(user_id, command_label, "started", source, DB_PATH)
    started = time.monotonic()

    try:
        if command == "photo":
            await context.bot.send_message(chat_id=chat_id, text="Taking photo...")
            path: Path | None = None
            try:
                path = await asyncio.to_thread(capture_photo, CAMERA_INDEX, TEMP_DIR)
                with path.open("rb") as photo:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo, caption="📸 Photo captured")
            finally:
                if path and path.exists():
                    path.unlink(missing_ok=True)

        elif command == "video":
            seconds = duration or 5
            await context.bot.send_message(chat_id=chat_id, text=f"Recording video: {seconds}s...")
            path = None
            try:
                path = await asyncio.to_thread(record_video, seconds, CAMERA_INDEX, TEMP_DIR)
                with path.open("rb") as video:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=video,
                        caption=f"🎥 Video recorded: {seconds}s",
                        supports_streaming=True,
                    )
            finally:
                if path and path.exists():
                    path.unlink(missing_ok=True)

        elif command == "status":
            await context.bot.send_message(chat_id=chat_id, text=status_text(), reply_markup=owner_keyboard())

        elif command == "restart":
            ok = await asyncio.to_thread(restart_camera, CAMERA_INDEX)
            message = "Camera restart check completed." if ok else "Camera restart check failed."
            await context.bot.send_message(chat_id=chat_id, text=message)

        else:
            await context.bot.send_message(chat_id=chat_id, text="Unknown command.")
            log_command(user_id, command_label, "error", "unknown command", DB_PATH)
            return

        elapsed = time.monotonic() - started
        log_command(user_id, command_label, "success", f"{elapsed:.2f}s", DB_PATH)
    except CameraError as exc:
        log_command(user_id, command_label, "error", str(exc), DB_PATH)
        await context.bot.send_message(chat_id=chat_id, text=f"Camera error: {exc}")
    except Exception as exc:
        logger.exception("Command failed")
        log_command(user_id, command_label, "error", str(exc), DB_PATH)
        await context.bot.send_message(chat_id=chat_id, text=f"Command failed: {exc}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        await reject_unauthorized(update)
        return

    text = (
        "Telegram Laptop Camera Controller is online.\n\n"
        "Use the buttons below or commands:\n"
        "/photo\n"
        "/video 5\n"
        "/video 10\n"
        "/video 30\n"
        "/status\n"
        "/restart\n"
        "/help"
    )
    await update.effective_message.reply_text(text, reply_markup=owner_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        await reject_unauthorized(update)
        return

    await update.effective_message.reply_text(
        "Commands:\n"
        "/start - show menu\n"
        "/photo - take webcam photo\n"
        "/video 5 - record 5 seconds\n"
        "/video 10 - record 10 seconds\n"
        "/video 30 - record 30 seconds\n"
        "/status - show laptop and camera status\n"
        "/restart - reopen and check the camera\n"
        "/help - show this help",
        reply_markup=owner_keyboard(),
    )


async def photo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_camera_command(update, context, "photo")


async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        try:
            duration = int(context.args[0])
        except ValueError:
            await update.effective_message.reply_text("Usage: /video 5")
            return
    else:
        duration = 5

    if duration not in {5, 10, 15, 30, 60}:
        await update.effective_message.reply_text("Choose duration: 5, 10, 15, 30, or 60 seconds.")
        return

    await run_camera_command(update, context, "video", duration=duration)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_camera_command(update, context, "status")


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_camera_command(update, context, "restart")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    if not is_owner(update):
        await reject_unauthorized(update)
        return

    await query.answer()
    data = query.data or ""
    if data == "photo":
        await run_camera_command(update, context, "photo", source="callback")
    elif data.startswith("video:"):
        duration = int(data.split(":", 1)[1])
        await run_camera_command(update, context, "video", duration=duration, source="callback")
    elif data == "status":
        await run_camera_command(update, context, "status", source="callback")
    elif data == "restart":
        await run_camera_command(update, context, "restart", source="callback")


async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        await reject_unauthorized(update)
        return

    data = update.effective_message.web_app_data.data if update.effective_message.web_app_data else "{}"
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        await update.effective_message.reply_text("Mini App sent invalid JSON.")
        return

    command = payload.get("command")
    duration = payload.get("duration")
    if command == "photo":
        await run_camera_command(update, context, "photo", source="mini_app")
    elif command == "video":
        await run_camera_command(update, context, "video", duration=int(duration or 5), source="mini_app")
    elif command == "status":
        await run_camera_command(update, context, "status", source="mini_app")
    elif command == "restart":
        await run_camera_command(update, context, "restart", source="mini_app")
    else:
        await update.effective_message.reply_text("Mini App sent unknown command.")


def start_api_server() -> None:
    import uvicorn

    def run() -> None:
        config = uvicorn.Config("api:app", host=API_HOST, port=API_PORT, log_level="info")
        server = uvicorn.Server(config)
        server.run()

    thread = threading.Thread(target=run, name="fastapi-server", daemon=True)
    thread.start()
    logger.info("FastAPI started on http://%s:%s", API_HOST, API_PORT)


def build_application() -> Application:
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("photo", photo_command))
    application.add_handler(CommandHandler("video", video_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("restart", restart_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    return application


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Create .env from .env.example.")
    if OWNER_TELEGRAM_ID <= 0:
        raise RuntimeError("OWNER_TELEGRAM_ID is missing or invalid.")

    init_db(DB_PATH)
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)

    if START_API:
        start_api_server()

    application = build_application()
    logger.info("Bot polling started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
