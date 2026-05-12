from __future__ import annotations

import math
import time
import uuid
from pathlib import Path

import cv2


class CameraError(RuntimeError):
    pass


def _open_camera(camera_index: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        raise CameraError(
            f"Camera index {camera_index} is not available. "
            "Close apps using the webcam or try another CAMERA_INDEX."
        )

    return cap


def _ensure_temp_dir(temp_dir: str | Path) -> Path:
    path = Path(temp_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def camera_available(camera_index: int = 0) -> bool:
    cap = None
    try:
        cap = _open_camera(camera_index)
        ok, _ = cap.read()
        return bool(ok)
    except Exception:
        return False
    finally:
        if cap is not None:
            cap.release()


def capture_photo(camera_index: int = 0, temp_dir: str | Path = "temp") -> Path:
    cap = None
    try:
        cap = _open_camera(camera_index)

        frame = None
        for _ in range(8):
            ok, candidate = cap.read()
            if ok:
                frame = candidate
            time.sleep(0.04)

        if frame is None:
            raise CameraError("Camera opened, but no frame was returned.")

        output_dir = _ensure_temp_dir(temp_dir)
        output_path = output_dir / f"photo_{uuid.uuid4().hex}.jpg"
        if not cv2.imwrite(str(output_path), frame):
            raise CameraError("Could not write captured photo to disk.")

        return output_path
    except CameraError:
        raise
    except Exception as exc:
        raise CameraError(f"Could not capture photo: {exc}") from exc
    finally:
        if cap is not None:
            cap.release()


def record_video(
    duration_seconds: int,
    camera_index: int = 0,
    temp_dir: str | Path = "temp",
) -> Path:
    if duration_seconds < 1 or duration_seconds > 60:
        raise CameraError("Video duration must be between 1 and 60 seconds.")

    cap = None
    writer = None
    try:
        cap = _open_camera(camera_index)

        ok, first_frame = cap.read()
        if not ok or first_frame is None:
            raise CameraError("Camera opened, but no video frame was returned.")

        height, width = first_frame.shape[:2]
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or math.isnan(fps) or fps < 1 or fps > 60:
            fps = 20.0

        output_dir = _ensure_temp_dir(temp_dir)
        output_path = output_dir / f"video_{duration_seconds}s_{uuid.uuid4().hex}.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
        if not writer.isOpened():
            raise CameraError(
                "Could not start MP4 video writer. Install ffmpeg or try another camera driver."
            )

        start = time.monotonic()
        writer.write(first_frame)

        while time.monotonic() - start < duration_seconds:
            ok, frame = cap.read()
            if not ok or frame is None:
                raise CameraError("Camera stopped returning frames during recording.")
            writer.write(frame)

        return output_path
    except CameraError:
        raise
    except Exception as exc:
        raise CameraError(f"Could not record video: {exc}") from exc
    finally:
        if writer is not None:
            writer.release()
        if cap is not None:
            cap.release()


def restart_camera(camera_index: int = 0) -> bool:
    cap = None
    try:
        cap = _open_camera(camera_index)
        time.sleep(0.2)
        return True
    finally:
        if cap is not None:
            cap.release()
