from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from telegram import Bot

from camera import CameraError, camera_available, capture_photo, record_video, restart_camera
from storage import get_last_command, init_db, log_command


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0") or "0")
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0") or "0")
DB_PATH = os.getenv("DB_PATH", "camera_controller.sqlite3")
TEMP_DIR = os.getenv("TEMP_DIR", "temp")
START_TIME = datetime.now(timezone.utc)

init_db(DB_PATH)

app = FastAPI(title="Telegram Laptop Camera Controller")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEBAPP_DIR = Path(__file__).parent / "webapp"
if WEBAPP_DIR.exists():
    app.mount("/webapp", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")


class CommandRequest(BaseModel):
    user_id: int = Field(..., description="Telegram user id from Mini App")
    command: Literal["photo", "video", "status", "restart"]
    duration: int | None = Field(default=None, ge=1, le=60)


def _ensure_owner(user_id: int) -> None:
    if OWNER_TELEGRAM_ID <= 0:
        raise HTTPException(status_code=500, detail="OWNER_TELEGRAM_ID is not configured.")
    if user_id != OWNER_TELEGRAM_ID:
        raise HTTPException(status_code=403, detail="Forbidden.")


def _format_uptime() -> str:
    seconds = int((datetime.now(timezone.utc) - START_TIME).total_seconds())
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def build_status() -> dict[str, str | bool | None]:
    last = get_last_command(DB_PATH)
    camera_ok = camera_available(CAMERA_INDEX)
    return {
        "laptop_online": True,
        "camera_available": camera_ok,
        "last_command": last["command"] if last else None,
        "last_command_status": last["status"] if last else None,
        "last_command_at": last["created_at"] if last else None,
        "uptime": _format_uptime(),
    }


def _status_text() -> str:
    status = build_status()
    camera_text = "available" if status["camera_available"] else "unavailable"
    last = status["last_command"] or "none"
    last_status = status["last_command_status"] or "n/a"
    return (
        "📡 Camera laptop status\n"
        f"Online: yes\n"
        f"Camera: {camera_text}\n"
        f"Last command: {last} ({last_status})\n"
        f"Uptime: {status['uptime']}"
    )


async def _send_photo(bot: Bot) -> None:
    path: Path | None = None
    try:
        path = await asyncio.to_thread(capture_photo, CAMERA_INDEX, TEMP_DIR)
        with path.open("rb") as photo:
            await bot.send_photo(chat_id=OWNER_TELEGRAM_ID, photo=photo, caption="📸 Photo captured")
    finally:
        if path and path.exists():
            path.unlink(missing_ok=True)


async def _send_video(bot: Bot, duration: int) -> None:
    path: Path | None = None
    try:
        path = await asyncio.to_thread(record_video, duration, CAMERA_INDEX, TEMP_DIR)
        with path.open("rb") as video:
            await bot.send_video(
                chat_id=OWNER_TELEGRAM_ID,
                video=video,
                caption=f"🎥 Video recorded: {duration}s",
                supports_streaming=True,
            )
    finally:
        if path and path.exists():
            path.unlink(missing_ok=True)


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/webapp/")


@app.get("/api/status")
async def api_status(user_id: int = Query(...)) -> dict[str, str | bool | None]:
    _ensure_owner(user_id)
    return build_status()


@app.post("/api/command")
async def api_command(payload: CommandRequest) -> dict[str, str]:
    _ensure_owner(payload.user_id)
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN is not configured.")

    bot = Bot(BOT_TOKEN)
    command_label = payload.command if payload.command != "video" else f"video {payload.duration or 5}"
    log_command(payload.user_id, command_label, "started", "local api", DB_PATH)
    started = time.monotonic()

    try:
        if payload.command == "photo":
            await _send_photo(bot)
            message = "Photo sent to Telegram."
        elif payload.command == "video":
            duration = payload.duration or 5
            await _send_video(bot, duration)
            message = f"Video {duration}s sent to Telegram."
        elif payload.command == "status":
            await bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=_status_text())
            message = "Status sent to Telegram."
        elif payload.command == "restart":
            ok = await asyncio.to_thread(restart_camera, CAMERA_INDEX)
            await bot.send_message(
                chat_id=OWNER_TELEGRAM_ID,
                text="Camera restart check completed." if ok else "Camera restart check failed.",
            )
            message = "Restart check completed."
        else:
            raise HTTPException(status_code=400, detail="Unknown command.")

        elapsed = time.monotonic() - started
        log_command(payload.user_id, command_label, "success", f"{elapsed:.2f}s", DB_PATH)
        return {"status": "ok", "message": message}
    except CameraError as exc:
        log_command(payload.user_id, command_label, "error", str(exc), DB_PATH)
        await bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=f"Camera error: {exc}")
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        log_command(payload.user_id, command_label, "error", str(exc), DB_PATH)
        raise HTTPException(status_code=500, detail=f"Command failed: {exc}") from exc
