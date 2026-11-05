# %% HTTPS Flask + notebook GUI + MJPEG + WebRTC signaling + MediaPipe pinch click (v4.4.1)

import os
import re
import ssl
import cv2
import mss
import time
import math
import json
import queue
import html
import socket
import logging
import threading
import subprocess
import urllib.request
import urllib.error
import signal
import sys
from collections import deque
import numpy as np
from flask import Flask, Response, request, jsonify
from werkzeug.serving import make_server
from security import configure_pairing

# ---------- Optional accelerators / optional deps ----------
try:
    from turbojpeg import TurboJPEG, TJPF_BGR
    _jpeg = TurboJPEG()
    _use_turbo = True
except Exception:
    _jpeg = None
    _use_turbo = False

try:
    import mediapipe as mp
    _has_mediapipe = hasattr(mp, "solutions")
    if not _has_mediapipe:
        raise ImportError("Install requirements-gestures.txt: this project uses MediaPipe Solutions.")
    _mediapipe_err = ""
except Exception as e:
    _has_mediapipe = False
    _mediapipe_err = str(e)

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    try:
        pyautogui.PAUSE = 0.0
    except Exception:
        pass
    try:
        pyautogui.DARWIN_CATCH_UP_TIME = 0
    except Exception:
        pass
    try:
        pyautogui.MINIMUM_DURATION = 0
    except Exception:
        pass
    _has_pyautogui = True
except Exception:
    _has_pyautogui = False

try:
    import ipywidgets as widgets
    from IPython.display import display
    _has_widgets = True
except Exception:
    _has_widgets = False

# ---------- Root / static resolution ----------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------- Tunables ----------
VR_HOST_RENDER_WIDTH  = 5600
VR_HOST_RENDER_HEIGHT = 3150
MJPEG_TARGET_WIDTH = 12000
MJPEG_FPS = 30
HOST_TEXTURE_WIDTH = 4096
PHONE_CAM_MAX_WIDTH  = 480
PHONE_CAM_MAX_HEIGHT = 270
PHONE_CAM_MAX_FPS    = 24

DEFAULT_CURVE_RADIUS = 6.0
DEFAULT_GESTURE_FRAME_WIDTH = 424
DEFAULT_GESTURE_FRAME_HEIGHT = 240
DEFAULT_GESTURE_FRAME_FPS = 12
DEFAULT_GESTURE_PINCH_ON = 0.30
DEFAULT_GESTURE_PINCH_OFF = 0.42
DEFAULT_GESTURE_DOUBLE_MS = 1750
DEFAULT_GESTURE_INACTIVE_MS = 700
DEFAULT_GESTURE_OVERLAY_FPS = 18
DEFAULT_GESTURE_OVERLAY_JPEG_QUALITY = 75
PHONE_LINK_TIMEOUT_S = 3.5

CAM_FEED_PRESETS = {
    "low": {"camMaxWidth": 480.0, "camMaxHeight": 270.0, "camMaxFps": 24.0},
    "balanced": {"camMaxWidth": 640.0, "camMaxHeight": 360.0, "camMaxFps": 24.0},
    "clear": {"camMaxWidth": 960.0, "camMaxHeight": 540.0, "camMaxFps": 24.0},
    "ultra_clear": {"camMaxWidth": 1280.0, "camMaxHeight": 720.0, "camMaxFps": 24.0},
}

RESOLUTION_PRESETS = {
    "ultra_clear": {
        "hostRenderWidth": 5600.0,
        "hostRenderHeight": 3150.0,
        "mjpegWidth": 12000.0,
        "mjpegFps": 30.0,
        "hostTextureWidth": 4096.0,
    },
    "clear_default": {
        "hostRenderWidth": 4800.0,
        "hostRenderHeight": 2700.0,
        "mjpegWidth": 10000.0,
        "mjpegFps": 30.0,
        "hostTextureWidth": 3072.0,
    },
    "balanced": {
        "hostRenderWidth": 3840.0,
        "hostRenderHeight": 2160.0,
        "mjpegWidth": 7200.0,
        "mjpegFps": 30.0,
        "hostTextureWidth": 2560.0,
    },
    "low_latency": {
        "hostRenderWidth": 2880.0,
        "hostRenderHeight": 1620.0,
        "mjpegWidth": 5200.0,
        "mjpegFps": 28.0,
        "hostTextureWidth": 2048.0,
    },
    "ultra_latency": {
        "hostRenderWidth": 1920.0,
        "hostRenderHeight": 1080.0,
        "mjpegWidth": 3200.0,
        "mjpegFps": 24.0,
        "hostTextureWidth": 1536.0,
    },
}

MONITOR_INDEX = int(os.environ.get("VR_MONITOR_INDEX", "1"))

app = Flask(
    __name__,
    static_folder=os.path.join(ROOT_DIR, "static"),
    static_url_path="/static"
)

PAIRING_CODE = configure_pairing(app)

# ---------- Access log filter ----------
class SuppressNonErrorHTTP(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        try:
            parts = msg.split()
            code = int(parts[-2])
            if 200 <= code < 400:
                return False
        except Exception:
            pass
        return True

logging.getLogger("werkzeug").addFilter(SuppressNonErrorHTTP())

@app.after_request
def _log_settings_errors(resp):
    try:
        if (request.path in ("/settings", "/cursor", "/phone_cam_frame")) and resp.status_code >= 400:
            app.logger.error(f"{request.path} error -> {resp.status_code}")
    except Exception:
        pass
    return resp

# ---------- Shared settings ----------
SETTINGS = {
    "screenScale": 2.60,
    "screenDist": 1.50,
    "screenCurveRadius": DEFAULT_CURVE_RADIUS,
    "eyePx": 16.0,
    "converge": False,

    "recenterNonce": 0,

    "camEnabled": False,
    "camOpacity": 70.0,
    "camLens": "normal",
    "camFeedProfile": "low",
    "camBlend": "screen",

    "cursorEnabled": False,
    "cursorSafePx": 1.0,
    "cursorHz": 60.0,
    "cursorGainX": 1.0,
    "cursorGainY": 1.0,
    "cursorSmoothing": 0.25,
    "cursorJumpPx": 24.0,

    "hostRenderWidth": VR_HOST_RENDER_WIDTH,
    "hostRenderHeight": VR_HOST_RENDER_HEIGHT,
    "mjpegWidth": MJPEG_TARGET_WIDTH,
    "mjpegFps": MJPEG_FPS,
    "hostTextureWidth": HOST_TEXTURE_WIDTH,
    "camMaxWidth": PHONE_CAM_MAX_WIDTH,
    "camMaxHeight": PHONE_CAM_MAX_HEIGHT,
    "camMaxFps": PHONE_CAM_MAX_FPS,

    "filterMode": "simple",

    # Gesture pipeline
    "gestureEnabled": False,
    "gestureInactiveMs": float(DEFAULT_GESTURE_INACTIVE_MS),
    # Hold duration threshold:
    # pinch release <= threshold -> single click
    # pinch release  > threshold -> two-finger click
    "gestureDoublePinchMs": float(DEFAULT_GESTURE_DOUBLE_MS),
    "gesturePinchOn": float(DEFAULT_GESTURE_PINCH_ON),
    "gesturePinchOff": float(DEFAULT_GESTURE_PINCH_OFF),
    "gestureFrameWidth": float(DEFAULT_GESTURE_FRAME_WIDTH),
    "gestureFrameHeight": float(DEFAULT_GESTURE_FRAME_HEIGHT),
    "gestureFrameFps": float(DEFAULT_GESTURE_FRAME_FPS),
    "gestureMirrorX": False,
    "gestureDragDetectEnabled": True,
    "gestureDragAdjMinRatio": 0.24,
    "gestureDragThumbIndexMinRatio": 0.32,
    "gestureDragExtendRatio": 1.08,
    "gestureDragScaleGain": 1.00,
    "gestureKeypointStreamEnabled": True,
    # Drag hand selection:
    # False -> detect MediaPipe Left hand (usually user's right hand)
    # True  -> detect MediaPipe Right hand
    "gestureSwapHands": False,
    "gestureOverlayFps": float(DEFAULT_GESTURE_OVERLAY_FPS),
    "gestureOverlayJpegQuality": float(DEFAULT_GESTURE_OVERLAY_JPEG_QUALITY),

    "version": 1,
    "origin": "server",
}
SET_LOCK = threading.Lock()

BOOL_KEYS = {
    "converge", "camEnabled", "cursorEnabled", "gestureEnabled", "gestureMirrorX",
    "gestureDragDetectEnabled", "gestureSwapHands", "gestureKeypointStreamEnabled"
}
ENUM_KEYS = {
    "camLens": {"normal", "wide"},
    "camFeedProfile": {"low", "balanced", "clear", "ultra_clear"},
    "camBlend": {"screen", "normal"},
    "filterMode": {"simple", "one_euro"},
}
PROTECTED_KEYS = {"version", "origin", "recenterNonce"}


def _to_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def _set_setting(key, val, origin="server"):
    with SET_LOCK:
        SETTINGS[key] = val
        SETTINGS["version"] += 1
        SETTINGS["origin"] = origin


def _touch_settings(origin="server"):
    with SET_LOCK:
        SETTINGS["version"] += 1
        SETTINGS["origin"] = origin


def _apply_cam_feed_profile_locked(profile):
    p = CAM_FEED_PRESETS.get(str(profile))
    if not p:
        return False
    SETTINGS["camFeedProfile"] = str(profile)
    SETTINGS["camMaxWidth"] = float(p["camMaxWidth"])
    SETTINGS["camMaxHeight"] = float(p["camMaxHeight"])
    SETTINGS["camMaxFps"] = float(p["camMaxFps"])
    return True


@app.route("/settings", methods=["GET", "POST"])
def settings_route():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        origin = str(data.get("origin", "server"))
        cursor_set_explicitly = ("cursorEnabled" in data)
        cursor_new_value = _to_bool(data.get("cursorEnabled", False)) if cursor_set_explicitly else None
        cam_profile_to_apply = None
        with SET_LOCK:
            for k, raw in data.items():
                if k not in SETTINGS or k in PROTECTED_KEYS:
                    continue
                if k in BOOL_KEYS:
                    SETTINGS[k] = _to_bool(raw)
                elif k in ENUM_KEYS:
                    v = str(raw).strip().lower()
                    if v in ENUM_KEYS[k]:
                        if k == "camFeedProfile":
                            cam_profile_to_apply = v
                        else:
                            SETTINGS[k] = v
                else:
                    try:
                        SETTINGS[k] = float(raw)
                    except Exception:
                        pass
            if cam_profile_to_apply:
                _apply_cam_feed_profile_locked(cam_profile_to_apply)
            SETTINGS["version"] += 1
            SETTINGS["origin"] = origin
            out = dict(SETTINGS)
        if cursor_set_explicitly and cursor_new_value is False:
            with PHONE_LINK_LOCK:
                PHONE_LINK_STATE["cursorAutoSuppressed"] = False
                PHONE_LINK_STATE["cursorResumeWanted"] = False
        return jsonify(ok=True, **out)

    with SET_LOCK:
        return jsonify(**SETTINGS)


@app.route("/recenter", methods=["POST"])
def recenter():
    with SET_LOCK:
        SETTINGS["recenterNonce"] += 1
        SETTINGS["version"] += 1
        SETTINGS["origin"] = "server"
        rec = SETTINGS["recenterNonce"]
        ver = SETTINGS["version"]
    return jsonify(ok=True, recentered=rec, version=ver, origin="server")


# ---------- JPEG / screen stream ----------
def _encode_jpeg_from_bgr(bgr, quality=80):
    if _use_turbo:
        return _jpeg.encode(bgr, quality=quality, pixel_format=TJPF_BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


def get_monitor_geometry():
    with mss.mss() as sct:
        mon = sct.monitors[MONITOR_INDEX]
        return {
            "left": int(mon["left"]),
            "top": int(mon["top"]),
            "width": int(mon["width"]),
            "height": int(mon["height"]),
        }


_MON_GEO_CACHE = {"ts": 0.0, "geo": None}
_MON_GEO_LOCK = threading.Lock()


def get_monitor_geometry_cached(ttl=0.5):
    now = time.time()
    with _MON_GEO_LOCK:
        if _MON_GEO_CACHE["geo"] and (now - _MON_GEO_CACHE["ts"]) <= ttl:
            return dict(_MON_GEO_CACHE["geo"])
    geo = get_monitor_geometry()
    with _MON_GEO_LOCK:
        _MON_GEO_CACHE["geo"] = dict(geo)
        _MON_GEO_CACHE["ts"] = now
    return geo


@app.route("/screen_geom")
def screen_geom():
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }
    try:
        return jsonify(get_monitor_geometry()), 200, headers
    except Exception as e:
        return jsonify(error=str(e)), 500, headers


def gen_mjpeg():
    with mss.mss() as sct:
        mon = sct.monitors[MONITOR_INDEX]
        while True:
            with SET_LOCK:
                target_width = int(SETTINGS.get("mjpegWidth", MJPEG_TARGET_WIDTH))
                fps = max(1, int(SETTINGS.get("mjpegFps", MJPEG_FPS)))
            interval = 1.0 / fps

            t0 = time.time()
            sct_img = sct.grab(mon)
            bgr = cv2.cvtColor(np.asarray(sct_img), cv2.COLOR_BGRA2BGR)
            h, w = bgr.shape[:2]
            if w > target_width:
                tw = target_width
                th = int(h * (tw / w))
                bgr = cv2.resize(bgr, (tw, th), interpolation=cv2.INTER_AREA)

            jpg = _encode_jpeg_from_bgr(bgr, quality=80)
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
            )

            dt = time.time() - t0
            if dt < interval:
                time.sleep(interval - dt)


@app.route("/screen.mjpeg")
def screen_mjpeg():
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }
    return Response(
        gen_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers=headers,
    )


# ---------- Cursor endpoint (existing gaze control) ----------
@app.route("/cursor", methods=["POST"])
def cursor():
    if not _has_pyautogui:
        return jsonify(ok=False, error="pyautogui not available"), 501
    data = request.get_json(silent=True) or {}
    x = data.get("x")
    y = data.get("y")
    if x is None or y is None:
        return jsonify(ok=False, error="x,y required"), 400
    try:
        pyautogui.moveTo(int(math.floor(x)), int(math.floor(y)), duration=0, _pause=False)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


# ---------- Phone camera upload + MediaPipe gesture ----------
GESTURE_LOCK = threading.Lock()
GESTURE_FRAME = None
GESTURE_FRAME_SEQ = 0
GESTURE_OVERLAY_FRAME = None
GESTURE_KEYPOINT_LOCK = threading.Lock()
GESTURE_KEYPOINT_PACKET = {
    "seq": 0,
    "ts": 0.0,
    "frameSeq": 0,
    "frameWidth": 0,
    "frameHeight": 0,
    "mirrorX": False,
    "hands": [],
    "trackingEnabled": False,
    "trackingCenterNormX": 0.5,
    "trackingCenterNormY": 0.5,
}
GESTURE_STATUS = {
    "mediapipeAvailable": _has_mediapipe,
    "mediapipeError": _mediapipe_err,
    "enabled": False,
    "framesReceived": 0,
    "framesProcessed": 0,
    "handsDetected": 0,
    "lastFrameAt": 0.0,
    "phoneConnected": False,
    "lastHeartbeatAt": 0.0,
    "cursorAutoSuppressed": False,
    "lastProcessAt": 0.0,
    "keypointsSeq": 0,
    "keypointsAt": 0.0,
    "pinchActive": False,
    "lastPinchAt": 0.0,
    "lastPinchRatio": -1.0,
    "pinchHoldMs": 0.0,
    "pinchHoldThresholdMs": float(DEFAULT_GESTURE_DOUBLE_MS),
    "pendingSingle": False,
    "pendingDeadline": 0.0,
    "cooldownUntil": 0.0,
    "lastAction": "none",
    "lastActionAt": 0.0,
    "lastActionX": 0,
    "lastActionY": 0,
    "lastTwoFingerAt": 0.0,
    "lastError": "",
    "lastPinchDistance": -1.0,
    "dragHandDetected": False,
    "dragHandSpread": False,
    "dragHandSpanPx": 0.0,
    "dragHandBoxWpx": 0.0,
    "dragHandBoxHpx": 0.0,
    "dragHandCenterNormX": 0.5,
    "dragHandCenterNormY": 0.5,
    "dragScaleGain": 1.0,
    "leftHandDetected": False,
    "leftHandSpread": False,
    "trackingEnabled": False,
    "trackingReason": "disabled",
    "trackingDisableReason": "not_started",
    "trackingCenterNormX": 0.5,
    "trackingCenterNormY": 0.5,
    "trackingX": 0,
    "trackingY": 0,
    "trackingUpdatedAt": 0.0,
}
GESTURE_LOGS = deque(maxlen=250)
GESTURE_LOG_LOCK = threading.Lock()
GESTURE_LAST_LOG_TS = {}
PHONE_LINK_LOCK = threading.Lock()
PHONE_LINK_STATE = {
    "connected": False,
    "lastHeartbeatAt": 0.0,
    "lastFrameAt": 0.0,
    "lastChangeAt": 0.0,
    "cursorAutoSuppressed": False,
    "cursorResumeWanted": False,
}
_PHONE_LINK_MONITOR_STARTED = False


def gesture_log(message, key=None, min_interval_s=0.0):
    now = time.time()
    if key:
        with GESTURE_LOG_LOCK:
            last = GESTURE_LAST_LOG_TS.get(key, 0.0)
            if (now - last) < float(min_interval_s):
                return
            GESTURE_LAST_LOG_TS[key] = now

    line = f"[gesture {time.strftime('%H:%M:%S')}] {message}"
    print(line)
    with GESTURE_LOG_LOCK:
        GESTURE_LOGS.append(line)


def _phone_link_snapshot(now=None):
    now = time.time() if now is None else float(now)
    with PHONE_LINK_LOCK:
        snap = dict(PHONE_LINK_STATE)
    hb = float(snap.get("lastHeartbeatAt", 0.0))
    age_ms = max(0, int((now - hb) * 1000)) if hb > 0 else 9999999
    snap["heartbeatAgeMs"] = age_ms
    return snap


def _phone_link_mark_connected(source="heartbeat"):
    now = time.time()
    became_connected = False
    should_restore_cursor = False

    with PHONE_LINK_LOCK:
        if source == "frame":
            PHONE_LINK_STATE["lastFrameAt"] = now
        PHONE_LINK_STATE["lastHeartbeatAt"] = now
        if not PHONE_LINK_STATE["connected"]:
            PHONE_LINK_STATE["connected"] = True
            PHONE_LINK_STATE["lastChangeAt"] = now
            became_connected = True
            should_restore_cursor = bool(
                PHONE_LINK_STATE.get("cursorAutoSuppressed") and PHONE_LINK_STATE.get("cursorResumeWanted")
            )
            if should_restore_cursor:
                PHONE_LINK_STATE["cursorAutoSuppressed"] = False
                PHONE_LINK_STATE["cursorResumeWanted"] = False
        cursor_auto_suppressed = bool(PHONE_LINK_STATE.get("cursorAutoSuppressed", False))

    if became_connected:
        gesture_log("phone link connected")

    if should_restore_cursor:
        with SET_LOCK:
            if not bool(SETTINGS.get("cursorEnabled", False)):
                SETTINGS["cursorEnabled"] = True
                SETTINGS["version"] += 1
                SETTINGS["origin"] = "server"
        gesture_log("phone reconnected: gaze cursor restored")
        cursor_auto_suppressed = False

    with GESTURE_LOCK:
        GESTURE_STATUS["phoneConnected"] = True
        GESTURE_STATUS["lastHeartbeatAt"] = float(now)
        GESTURE_STATUS["cursorAutoSuppressed"] = bool(cursor_auto_suppressed)


def _phone_link_mark_disconnected(reason="timeout"):
    now = time.time()
    changed = False
    cursor_was_disabled = False

    with PHONE_LINK_LOCK:
        if PHONE_LINK_STATE["connected"]:
            PHONE_LINK_STATE["connected"] = False
            PHONE_LINK_STATE["lastChangeAt"] = now
            changed = True

    if not changed:
        return False

    with SET_LOCK:
        if bool(SETTINGS.get("cursorEnabled", False)):
            SETTINGS["cursorEnabled"] = False
            SETTINGS["version"] += 1
            SETTINGS["origin"] = "server"
            cursor_was_disabled = True

    with PHONE_LINK_LOCK:
        if cursor_was_disabled:
            PHONE_LINK_STATE["cursorAutoSuppressed"] = True
            PHONE_LINK_STATE["cursorResumeWanted"] = True
        else:
            PHONE_LINK_STATE["cursorAutoSuppressed"] = False
            PHONE_LINK_STATE["cursorResumeWanted"] = False
        hb = float(PHONE_LINK_STATE.get("lastHeartbeatAt", 0.0))
        cursor_auto_suppressed = bool(PHONE_LINK_STATE.get("cursorAutoSuppressed", False))

    with GESTURE_LOCK:
        GESTURE_STATUS["phoneConnected"] = False
        GESTURE_STATUS["lastHeartbeatAt"] = hb
        GESTURE_STATUS["cursorAutoSuppressed"] = bool(cursor_auto_suppressed)

    if cursor_was_disabled:
        gesture_log(f"phone link disconnected ({reason}); gaze cursor auto-disabled")
    else:
        gesture_log(f"phone link disconnected ({reason})")
    return True


def phone_link_monitor_worker():
    while True:
        snap = _phone_link_snapshot()
        if bool(snap.get("connected")):
            age_ms = int(snap.get("heartbeatAgeMs", 0))
            if age_ms > int(PHONE_LINK_TIMEOUT_S * 1000):
                _phone_link_mark_disconnected("heartbeat timeout")
        time.sleep(0.35)


def start_phone_link_monitor_once():
    global _PHONE_LINK_MONITOR_STARTED
    if _PHONE_LINK_MONITOR_STARTED:
        return
    t = threading.Thread(target=phone_link_monitor_worker, daemon=True)
    t.start()
    _PHONE_LINK_MONITOR_STARTED = True


def _make_overlay_placeholder(message="waiting for phone camera..."):
    img = np.zeros((480, 848, 3), dtype=np.uint8)
    cv2.putText(
        img,
        message,
        (30, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.86,
        (90, 220, 255),
        2,
        cv2.LINE_AA,
    )
    return img


def _put_overlay_info(img, text, line, color=(200, 255, 200)):
    cv2.putText(
        img,
        text,
        (12, 24 + line * 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.64,
        color,
        2,
        cv2.LINE_AA,
    )


def _norm_to_screen(u, v, mirror_x=False):
    u = max(0.0, min(1.0, float(u)))
    v = max(0.0, min(1.0, float(v)))
    if mirror_x:
        u = 1.0 - u
    geo = get_monitor_geometry_cached()
    x = int(round(geo["left"] + u * (geo["width"] - 1)))
    y = int(round(geo["top"] + v * (geo["height"] - 1)))
    return x, y


def _gesture_click(kind, x, y):
    if not _has_pyautogui:
        return False, "pyautogui not available"
    try:
        pyautogui.moveTo(int(x), int(y), duration=0, _pause=False)
        if kind == "right":
            pyautogui.click(button="right", _pause=False)
        else:
            pyautogui.click(button="left", _pause=False)
        return True, ""
    except Exception as e:
        return False, str(e)


def _lm_dist_points(a, b):
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def _eval_drag_hand_spread(lm, adj_min_ratio, thumb_min_ratio, extend_ratio):
    tip_ids = (8, 12, 16, 20)
    pip_ids = (6, 10, 14, 18)
    wrist = lm[0]

    palm_span = max(
        1e-6,
        _lm_dist_points(lm[5], lm[17]),
        _lm_dist_points(lm[0], lm[9]),
    )
    adj = (
        _lm_dist_points(lm[8], lm[12]) / palm_span,
        _lm_dist_points(lm[12], lm[16]) / palm_span,
        _lm_dist_points(lm[16], lm[20]) / palm_span,
    )
    thumb_index = _lm_dist_points(lm[4], lm[8]) / palm_span
    extended = []
    for tid, pid in zip(tip_ids, pip_ids):
        tip_d = _lm_dist_points(lm[tid], wrist)
        pip_d = _lm_dist_points(lm[pid], wrist)
        extended.append(tip_d >= pip_d * max(1.0, extend_ratio))

    spread_ok = (min(adj) >= adj_min_ratio) and (thumb_index >= thumb_min_ratio) and all(extended)
    cx = sum(lm[i].x for i in (0, 4, 8, 12, 16, 20)) / 6.0
    cy = sum(lm[i].y for i in (0, 4, 8, 12, 16, 20)) / 6.0
    return spread_ok, (cx, cy), min(adj), thumb_index, all(extended)


def _is_drag_hand(handed_label, swap_hands=False):
    label = str(handed_label or "").strip().lower()
    mp_is_left = label == "left"
    return (not mp_is_left) if swap_hands else mp_is_left


def _update_overlay_frame(frame):
    global GESTURE_OVERLAY_FRAME
    with GESTURE_LOCK:
        GESTURE_OVERLAY_FRAME = frame


def _publish_gesture_keypoints(
    hands,
    frame_w,
    frame_h,
    mirror_x,
    frame_seq,
    tracking_enabled=False,
    tracking_center_norm=(0.5, 0.5),
):
    global GESTURE_KEYPOINT_PACKET
    now = time.time()
    with GESTURE_KEYPOINT_LOCK:
        next_seq = int(GESTURE_KEYPOINT_PACKET.get("seq", 0)) + 1
        GESTURE_KEYPOINT_PACKET = {
            "seq": next_seq,
            "ts": float(now),
            "frameSeq": int(frame_seq),
            "frameWidth": int(frame_w),
            "frameHeight": int(frame_h),
            "mirrorX": bool(mirror_x),
            "hands": hands,
            "trackingEnabled": bool(tracking_enabled),
            "trackingCenterNormX": float(tracking_center_norm[0]),
            "trackingCenterNormY": float(tracking_center_norm[1]),
        }

    with GESTURE_LOCK:
        GESTURE_STATUS["keypointsSeq"] = int(next_seq)
        GESTURE_STATUS["keypointsAt"] = float(now)


@app.route("/phone_cam_frame", methods=["POST"])
def phone_cam_frame():
    global GESTURE_FRAME, GESTURE_FRAME_SEQ
    raw = request.get_data(cache=False)
    if not raw:
        return jsonify(ok=False, error="empty frame"), 400

    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify(ok=False, error="decode failed"), 400

    with SET_LOCK:
        max_w = max(224, int(SETTINGS.get("gestureFrameWidth", DEFAULT_GESTURE_FRAME_WIDTH)))
        max_h = max(160, int(SETTINGS.get("gestureFrameHeight", DEFAULT_GESTURE_FRAME_HEIGHT)))
    h0, w0 = frame.shape[:2]
    if w0 > max_w or h0 > max_h:
        scale = min(max_w / max(1, w0), max_h / max(1, h0))
        tw = max(1, int(round(w0 * scale)))
        th = max(1, int(round(h0 * scale)))
        frame = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_AREA)

    now = time.time()
    _phone_link_mark_connected(source="frame")
    with GESTURE_LOCK:
        GESTURE_FRAME = frame
        GESTURE_FRAME_SEQ += 1
        GESTURE_STATUS["framesReceived"] = int(GESTURE_STATUS.get("framesReceived", 0)) + 1
        GESTURE_STATUS["lastFrameAt"] = now
        GESTURE_STATUS["phoneConnected"] = True
        GESTURE_STATUS["lastHeartbeatAt"] = float(now)
        seq_now = GESTURE_FRAME_SEQ

    if seq_now <= 3:
        gesture_log(f"phone camera uplink active ({frame.shape[1]}x{frame.shape[0]}), seq={seq_now}")
    else:
        gesture_log(f"phone camera frames arriving, latest seq={seq_now}", key="phone_frame_alive", min_interval_s=5.0)

    return jsonify(ok=True, seq=GESTURE_FRAME_SEQ)


@app.route("/phone_heartbeat", methods=["GET", "POST"])
def phone_heartbeat():
    _phone_link_mark_connected(source="heartbeat")
    now = time.time()
    return jsonify(ok=True, ts=now)


@app.route("/gesture_status")
def gesture_status():
    with GESTURE_LOCK:
        out = dict(GESTURE_STATUS)
    now = time.time()
    with SET_LOCK:
        out["pinchOnRatio"] = float(SETTINGS.get("gesturePinchOn", DEFAULT_GESTURE_PINCH_ON))
        out["pinchOffRatio"] = float(SETTINGS.get("gesturePinchOff", DEFAULT_GESTURE_PINCH_OFF))
        out["dragAdjMinRatio"] = float(SETTINGS.get("gestureDragAdjMinRatio", 0.24))
        out["dragThumbIndexMinRatio"] = float(SETTINGS.get("gestureDragThumbIndexMinRatio", 0.32))
        out["dragExtendRatio"] = float(SETTINGS.get("gestureDragExtendRatio", 1.08))
        out["dragScaleGain"] = float(SETTINGS.get("gestureDragScaleGain", 1.0))
        out["dragDetectEnabled"] = bool(SETTINGS.get("gestureDragDetectEnabled", True))
        out["gestureKeypointStreamEnabled"] = bool(SETTINGS.get("gestureKeypointStreamEnabled", True))
        out["gestureSwapHands"] = bool(SETTINGS.get("gestureSwapHands", False))
    phone_snap = _phone_link_snapshot(now=now)
    out["cooldownRemainingMs"] = max(0, int((out.get("cooldownUntil", 0.0) - now) * 1000))
    out["pendingRemainingMs"] = max(0, int((out.get("pendingDeadline", 0.0) - now) * 1000))
    out["lastFrameAgeMs"] = max(0, int((now - float(out.get("lastFrameAt", 0.0))) * 1000))
    out["keypointsAgeMs"] = max(0, int((now - float(out.get("keypointsAt", 0.0))) * 1000))
    out["phoneConnected"] = bool(phone_snap.get("connected", False))
    out["lastHeartbeatAt"] = float(phone_snap.get("lastHeartbeatAt", 0.0))
    out["heartbeatAgeMs"] = int(phone_snap.get("heartbeatAgeMs", 0))
    out["phoneLinkTimeoutMs"] = int(PHONE_LINK_TIMEOUT_S * 1000)
    out["cursorAutoSuppressed"] = bool(phone_snap.get("cursorAutoSuppressed", False))
    out["gestureLibrary"] = ["pinch_to_click", "pinch_hold_two_finger_click", "drag_mode_right_hand_spread"]
    return jsonify(**out)


@app.route("/gesture_logs")
def gesture_logs():
    try:
        n = max(1, min(200, int(request.args.get("n", "60"))))
    except Exception:
        n = 60
    with GESTURE_LOG_LOCK:
        lines = list(GESTURE_LOGS)[-n:]
    return jsonify(lines=lines, count=len(lines))


@app.route("/gesture_keypoints")
def gesture_keypoints():
    try:
        since = int(request.args.get("since", "0"))
    except Exception:
        since = 0

    with GESTURE_KEYPOINT_LOCK:
        payload = dict(GESTURE_KEYPOINT_PACKET)
        payload["hands"] = list(GESTURE_KEYPOINT_PACKET.get("hands", []))

    seq_now = int(payload.get("seq", 0))
    if seq_now <= since:
        payload = {
            "stale": True,
            "seq": seq_now,
            "ts": float(payload.get("ts", 0.0)),
            "hands": [],
            "frameSeq": int(payload.get("frameSeq", 0)),
            "frameWidth": int(payload.get("frameWidth", 0)),
            "frameHeight": int(payload.get("frameHeight", 0)),
            "mirrorX": bool(payload.get("mirrorX", False)),
            "trackingEnabled": bool(payload.get("trackingEnabled", False)),
            "trackingCenterNormX": float(payload.get("trackingCenterNormX", 0.5)),
            "trackingCenterNormY": float(payload.get("trackingCenterNormY", 0.5)),
        }
    else:
        payload["stale"] = False

    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }
    return jsonify(payload), 200, headers


@app.route("/overlay.jpg")
def overlay_jpg():
    with GESTURE_LOCK:
        frame = GESTURE_OVERLAY_FRAME.copy() if GESTURE_OVERLAY_FRAME is not None else None
    if frame is None:
        frame = _make_overlay_placeholder()

    with SET_LOCK:
        q = int(SETTINGS.get("gestureOverlayJpegQuality", DEFAULT_GESTURE_OVERLAY_JPEG_QUALITY))
    jpg = _encode_jpeg_from_bgr(frame, quality=max(40, min(95, q)))
    return Response(
        jpg,
        mimetype="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


def gen_overlay_mjpeg():
    while True:
        with GESTURE_LOCK:
            frame = GESTURE_OVERLAY_FRAME.copy() if GESTURE_OVERLAY_FRAME is not None else None
        if frame is None:
            frame = _make_overlay_placeholder()

        with SET_LOCK:
            fps = max(4, min(30, int(SETTINGS.get("gestureOverlayFps", DEFAULT_GESTURE_OVERLAY_FPS))))
            q = int(SETTINGS.get("gestureOverlayJpegQuality", DEFAULT_GESTURE_OVERLAY_JPEG_QUALITY))

        jpg = _encode_jpeg_from_bgr(frame, quality=max(40, min(95, q)))
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
        )
        time.sleep(1.0 / fps)


@app.route("/overlay.mjpeg")
def overlay_mjpeg():
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }
    return Response(
        gen_overlay_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers=headers,
    )


_GESTURE_THREAD_STARTED = False

def gesture_worker():
    if not _has_mediapipe:
        with GESTURE_LOCK:
            GESTURE_STATUS["lastError"] = "mediapipe unavailable"
        gesture_log(f"mediapipe unavailable: {_mediapipe_err or 'import failed'}")
        return

    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    mp_style = mp.solutions.drawing_styles

    local_seq = -1
    pinch_down = False
    pinch_started_at = 0.0
    pinch_point = None  # screen coordinates
    pinch_ignored = False
    cooldown_until = 0.0
    smooth_ratio = None

    tracking_enabled = False
    tracking_center_norm = (0.5, 0.5)
    tracking_disable_reason = "not_started"
    tracking_x = 0
    tracking_y = 0
    last_empty_keypoint_publish = 0.0
    gesture_log("mediapipe gesture worker started (ratio-based pinch detection)")

    with mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        model_complexity=1,
        min_detection_confidence=0.60,
        min_tracking_confidence=0.55,
    ) as hands:
        while True:
            now = time.time()

            with SET_LOCK:
                enabled = bool(SETTINGS.get("gestureEnabled", False))
                inactive_ms = float(SETTINGS.get("gestureInactiveMs", DEFAULT_GESTURE_INACTIVE_MS))
                hold_ms_threshold = float(SETTINGS.get("gestureDoublePinchMs", DEFAULT_GESTURE_DOUBLE_MS))
                pinch_on = float(SETTINGS.get("gesturePinchOn", DEFAULT_GESTURE_PINCH_ON))
                pinch_off = float(SETTINGS.get("gesturePinchOff", DEFAULT_GESTURE_PINCH_OFF))
                mirror_x = bool(SETTINGS.get("gestureMirrorX", False))
                drag_detect_enabled = bool(SETTINGS.get("gestureDragDetectEnabled", True))
                keypoint_stream_enabled = bool(SETTINGS.get("gestureKeypointStreamEnabled", True))
                drag_adj_min_ratio = float(SETTINGS.get("gestureDragAdjMinRatio", 0.24))
                drag_thumb_index_min_ratio = float(SETTINGS.get("gestureDragThumbIndexMinRatio", 0.32))
                drag_extend_ratio = float(SETTINGS.get("gestureDragExtendRatio", 1.08))
                drag_scale_gain = float(SETTINGS.get("gestureDragScaleGain", 1.0))
                swap_hands = bool(SETTINGS.get("gestureSwapHands", False))

            if not enabled:
                pinch_down = False
                pinch_started_at = 0.0
                pinch_point = None
                pinch_ignored = False
                smooth_ratio = None
                cooldown_until = 0.0
                tracking_enabled = False
                tracking_disable_reason = "disabled"
                with GESTURE_LOCK:
                    GESTURE_STATUS["enabled"] = False
                    GESTURE_STATUS["handsDetected"] = 0
                    GESTURE_STATUS["pinchActive"] = False
                    GESTURE_STATUS["lastPinchRatio"] = -1.0
                    GESTURE_STATUS["pinchHoldMs"] = 0.0
                    GESTURE_STATUS["pinchHoldThresholdMs"] = float(hold_ms_threshold)
                    GESTURE_STATUS["pendingSingle"] = False
                    GESTURE_STATUS["pendingDeadline"] = 0.0
                    GESTURE_STATUS["cooldownUntil"] = 0.0
                    GESTURE_STATUS["lastProcessAt"] = now
                    GESTURE_STATUS["lastPinchDistance"] = -1.0
                    GESTURE_STATUS["dragHandDetected"] = False
                    GESTURE_STATUS["dragHandSpread"] = False
                    GESTURE_STATUS["dragHandSpanPx"] = 0.0
                    GESTURE_STATUS["dragHandBoxWpx"] = 0.0
                    GESTURE_STATUS["dragHandBoxHpx"] = 0.0
                    GESTURE_STATUS["dragHandCenterNormX"] = float(tracking_center_norm[0])
                    GESTURE_STATUS["dragHandCenterNormY"] = float(tracking_center_norm[1])
                    GESTURE_STATUS["leftHandDetected"] = False  # compatibility
                    GESTURE_STATUS["leftHandSpread"] = False   # compatibility
                    GESTURE_STATUS["trackingEnabled"] = False
                    GESTURE_STATUS["trackingReason"] = "disabled"
                    GESTURE_STATUS["trackingDisableReason"] = "disabled"
                    GESTURE_STATUS["trackingCenterNormX"] = float(tracking_center_norm[0])
                    GESTURE_STATUS["trackingCenterNormY"] = float(tracking_center_norm[1])
                    GESTURE_STATUS["trackingX"] = int(tracking_x)
                    GESTURE_STATUS["trackingY"] = int(tracking_y)
                    GESTURE_STATUS["trackingUpdatedAt"] = now
                    GESTURE_STATUS["dragScaleGain"] = float(drag_scale_gain)
                if keypoint_stream_enabled and (now - last_empty_keypoint_publish) >= 0.25:
                    _publish_gesture_keypoints(
                        [],
                        frame_w=0,
                        frame_h=0,
                        mirror_x=mirror_x,
                        frame_seq=local_seq,
                        tracking_enabled=False,
                        tracking_center_norm=tracking_center_norm,
                    )
                    last_empty_keypoint_publish = now
                time.sleep(0.03)
                continue

            frame = None
            last_frame_at = 0.0
            with GESTURE_LOCK:
                if GESTURE_FRAME is not None and GESTURE_FRAME_SEQ != local_seq:
                    frame = GESTURE_FRAME.copy()
                    local_seq = GESTURE_FRAME_SEQ
                last_frame_at = float(GESTURE_STATUS.get("lastFrameAt", 0.0))

            if frame is None and (now - last_frame_at) > 1.2:
                if pinch_down:
                    gesture_log("pinch canceled due missing frames", key="pinch_drop_no_frame", min_interval_s=0.8)
                pinch_down = False
                pinch_started_at = 0.0
                pinch_point = None
                pinch_ignored = False
                smooth_ratio = None
                if tracking_enabled:
                    tracking_enabled = False
                    tracking_disable_reason = "drag_hand_lost"
                    gesture_log(
                        f"drag tracking disabled (drag hand lost); locked at ({tracking_x}, {tracking_y})",
                        key="drag_lost_frame",
                        min_interval_s=0.6,
                    )
                gesture_log("gesture enabled but no phone camera frames arriving", key="no_frame", min_interval_s=2.0)
                with GESTURE_LOCK:
                    GESTURE_STATUS["enabled"] = True
                    GESTURE_STATUS["handsDetected"] = 0
                    GESTURE_STATUS["pinchActive"] = False
                    GESTURE_STATUS["lastPinchRatio"] = -1.0
                    GESTURE_STATUS["pinchHoldMs"] = 0.0
                    GESTURE_STATUS["pinchHoldThresholdMs"] = float(hold_ms_threshold)
                    GESTURE_STATUS["pendingSingle"] = False
                    GESTURE_STATUS["pendingDeadline"] = 0.0
                    GESTURE_STATUS["cooldownUntil"] = float(cooldown_until)
                    GESTURE_STATUS["lastProcessAt"] = now
                    GESTURE_STATUS["lastPinchDistance"] = -1.0
                    GESTURE_STATUS["dragHandDetected"] = False
                    GESTURE_STATUS["dragHandSpread"] = False
                    GESTURE_STATUS["dragHandSpanPx"] = 0.0
                    GESTURE_STATUS["dragHandBoxWpx"] = 0.0
                    GESTURE_STATUS["dragHandBoxHpx"] = 0.0
                    GESTURE_STATUS["dragHandCenterNormX"] = float(tracking_center_norm[0])
                    GESTURE_STATUS["dragHandCenterNormY"] = float(tracking_center_norm[1])
                    GESTURE_STATUS["leftHandDetected"] = False
                    GESTURE_STATUS["leftHandSpread"] = False
                    GESTURE_STATUS["trackingEnabled"] = bool(tracking_enabled)
                    GESTURE_STATUS["trackingReason"] = "active" if tracking_enabled else str(tracking_disable_reason)
                    GESTURE_STATUS["trackingDisableReason"] = "active" if tracking_enabled else str(tracking_disable_reason)
                    GESTURE_STATUS["trackingCenterNormX"] = float(tracking_center_norm[0])
                    GESTURE_STATUS["trackingCenterNormY"] = float(tracking_center_norm[1])
                    GESTURE_STATUS["trackingX"] = int(tracking_x)
                    GESTURE_STATUS["trackingY"] = int(tracking_y)
                    GESTURE_STATUS["trackingUpdatedAt"] = now
                    GESTURE_STATUS["dragScaleGain"] = float(drag_scale_gain)
                if keypoint_stream_enabled and (now - last_empty_keypoint_publish) >= 0.25:
                    _publish_gesture_keypoints(
                        [],
                        frame_w=0,
                        frame_h=0,
                        mirror_x=mirror_x,
                        frame_seq=local_seq,
                        tracking_enabled=tracking_enabled,
                        tracking_center_norm=tracking_center_norm,
                    )
                    last_empty_keypoint_publish = now
                time.sleep(0.01)
                continue

            # Worker runs much faster than phone frame uploads; if there is no new frame yet,
            # wait for the next upload instead of trying to process a None frame.
            if frame is None:
                time.sleep(0.003)
                continue

            overlay = frame.copy()
            hands_detected = 0
            pinch_now = False
            pinch_point_now = None
            best_ratio = None
            best_mid = None
            drag_hand_found = False
            drag_hand_spread = False
            drag_hand_center = None
            drag_hand_center_any = None
            drag_hand_span_px = 0.0
            drag_hand_box_w_px = 0.0
            drag_hand_box_h_px = 0.0
            drag_hand_spread_span_px = -1.0
            keypoint_hands = []

            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = hands.process(rgb)
            except Exception as e:
                with GESTURE_LOCK:
                    GESTURE_STATUS["lastError"] = f"mediapipe process error: {e}"
                gesture_log(f"mediapipe processing error: {e}", key="mp_error", min_interval_s=1.0)
                _update_overlay_frame(overlay)
                if keypoint_stream_enabled and (now - last_empty_keypoint_publish) >= 0.25:
                    _publish_gesture_keypoints(
                        [],
                        frame_w=int(frame.shape[1]),
                        frame_h=int(frame.shape[0]),
                        mirror_x=mirror_x,
                        frame_seq=local_seq,
                        tracking_enabled=tracking_enabled,
                        tracking_center_norm=tracking_center_norm,
                    )
                    last_empty_keypoint_publish = now
                time.sleep(0.01)
                continue

            if results.multi_hand_landmarks:
                hands_detected = len(results.multi_hand_landmarks)
                handedness_list = results.multi_handedness or []
                for idx, hand in enumerate(results.multi_hand_landmarks):
                    handed = "unknown"
                    handed_score = 0.0
                    try:
                        if idx < len(handedness_list):
                            cls = handedness_list[idx].classification[0]
                            handed = str(cls.label).lower()
                            handed_score = float(getattr(cls, "score", 0.0))
                    except Exception:
                        handed = "unknown"
                        handed_score = 0.0

                    mp_draw.draw_landmarks(
                        overlay,
                        hand,
                        mp_hands.HAND_CONNECTIONS,
                        mp_style.get_default_hand_landmarks_style(),
                        mp_style.get_default_hand_connections_style(),
                    )

                    lm = hand.landmark
                    p4 = lm[4]
                    p8 = lm[8]
                    p5 = lm[5]
                    p17 = lm[17]
                    p0 = lm[0]

                    tip_dist = _lm_dist_points(p4, p8)
                    palm_span = _lm_dist_points(p5, p17)
                    wrist_ref = _lm_dist_points(p0, p5)
                    scale = max(1e-6, palm_span, wrist_ref)
                    ratio = tip_dist / scale
                    mx = 0.5 * (p4.x + p8.x)
                    my = 0.5 * (p4.y + p8.y)
                    if (best_ratio is None) or (ratio < best_ratio):
                        best_ratio = ratio
                        best_mid = (mx, my)

                    h, w = overlay.shape[:2]
                    x4, y4 = int(p4.x * w), int(p4.y * h)
                    x8, y8 = int(p8.x * w), int(p8.y * h)
                    cv2.line(overlay, (x4, y4), (x8, y8), (30, 220, 250), 2, cv2.LINE_AA)
                    cv2.circle(overlay, (x4, y4), 5, (255, 180, 30), -1)
                    cv2.circle(overlay, (x8, y8), 5, (255, 180, 30), -1)

                    if drag_detect_enabled and _is_drag_hand(handed, swap_hands=swap_hands):
                        drag_hand_found = True
                        spread_ok, center_uv, min_adj, thumb_gap, _ = _eval_drag_hand_spread(
                            lm,
                            drag_adj_min_ratio,
                            drag_thumb_index_min_ratio,
                            drag_extend_ratio,
                        )
                        xs = [float(pt.x) * w for pt in lm]
                        ys = [float(pt.y) * h for pt in lm]
                        box_w_px = max(0.0, max(xs) - min(xs))
                        box_h_px = max(0.0, max(ys) - min(ys))
                        span_px = math.sqrt(box_w_px * box_w_px + box_h_px * box_h_px)

                        if span_px > drag_hand_span_px:
                            drag_hand_span_px = span_px
                            drag_hand_box_w_px = box_w_px
                            drag_hand_box_h_px = box_h_px
                            drag_hand_center_any = center_uv

                        if spread_ok and span_px >= drag_hand_spread_span_px:
                            drag_hand_spread = True
                            drag_hand_center = center_uv
                            drag_hand_spread_span_px = span_px
                            drag_hand_span_px = span_px
                            drag_hand_box_w_px = box_w_px
                            drag_hand_box_h_px = box_h_px

                        cx, cy = int(center_uv[0] * w), int(center_uv[1] * h)
                        color = (90, 255, 120) if spread_ok else (80, 180, 255)
                        cv2.circle(overlay, (cx, cy), 9, color, 2, cv2.LINE_AA)
                        cv2.putText(
                            overlay,
                            f"DRAG-HAND spread={spread_ok} span={span_px:.1f}px",
                            (max(6, cx - 90), max(16, cy - 14)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45,
                            color,
                            1,
                            cv2.LINE_AA,
                        )

                    if keypoint_stream_enabled:
                        keypoint_hands.append(
                            {
                                "handedness": handed,
                                "score": round(handed_score, 4),
                                "landmarks": [
                                    [
                                        round(float(pt.x), 5),
                                        round(float(pt.y), 5),
                                        round(float(pt.z), 5),
                                    ]
                                    for pt in lm
                                ],
                            }
                        )

            # Drag tracking state machine.
            if drag_detect_enabled:
                if tracking_enabled:
                    if drag_hand_found and drag_hand_spread and drag_hand_center is not None:
                        tracking_center_norm = drag_hand_center
                        tracking_disable_reason = "active"
                    elif drag_hand_found and (not drag_hand_spread):
                        tracking_enabled = False
                        tracking_disable_reason = "drag_hand_not_spread"
                        gesture_log(
                            "tracking disabled: drag hand not spread (fingers together/touching or fist)",
                            key="drag_disabled_spread",
                            min_interval_s=0.6,
                        )
                    elif not drag_hand_found:
                        tracking_enabled = False
                        tracking_disable_reason = "drag_hand_lost"
                        gesture_log(
                            "tracking disabled: drag hand disappeared, lock at last position",
                            key="drag_disabled_lost",
                            min_interval_s=0.6,
                        )
                else:
                    if drag_hand_found and drag_hand_spread and drag_hand_center is not None:
                        tracking_enabled = True
                        tracking_center_norm = drag_hand_center
                        tracking_disable_reason = "active"
                        gesture_log(
                            "tracking enabled: drag hand fully spread detected (right hand / MediaPipe left)",
                            key="drag_enabled",
                            min_interval_s=0.4,
                        )
            else:
                if tracking_enabled:
                    tracking_enabled = False
                    tracking_disable_reason = "drag_detection_off"
                    gesture_log(
                        f"drag tracking disabled (setting off); locked at ({tracking_x}, {tracking_y})",
                        key="drag_off",
                        min_interval_s=0.4,
                    )
                elif tracking_disable_reason == "active":
                    tracking_disable_reason = "drag_detection_off"

            tracking_x, tracking_y = _norm_to_screen(
                tracking_center_norm[0],
                tracking_center_norm[1],
                mirror_x=mirror_x,
            )
            if keypoint_stream_enabled:
                _publish_gesture_keypoints(
                    keypoint_hands,
                    frame_w=int(frame.shape[1]),
                    frame_h=int(frame.shape[0]),
                    mirror_x=mirror_x,
                    frame_seq=local_seq,
                    tracking_enabled=tracking_enabled,
                    tracking_center_norm=tracking_center_norm,
                )
                if not keypoint_hands:
                    last_empty_keypoint_publish = now

            if enabled and best_ratio is not None:
                smooth_ratio = best_ratio if smooth_ratio is None else (0.45 * best_ratio + 0.55 * smooth_ratio)
                threshold = pinch_off if pinch_down else pinch_on
                pinch_now = smooth_ratio <= threshold
                if pinch_now:
                    if best_mid is not None:
                        pinch_point_now = _norm_to_screen(best_mid[0], best_mid[1], mirror_x=mirror_x)
                else:
                    gesture_log(
                        f"hand detected, no pinch (ratio={smooth_ratio:.4f}, threshold={threshold:.4f})",
                        key="hand_no_pinch",
                        min_interval_s=1.2,
                    )
            else:
                if not enabled:
                    smooth_ratio = None
                pinch_now = False
                if best_ratio is None:
                    smooth_ratio = None
                if enabled and hands_detected == 0:
                    gesture_log("no hands detected", key="no_hands", min_interval_s=1.8)

            if pinch_now and pinch_point_now is not None:
                if not pinch_down:
                    pinch_down = True
                    pinch_started_at = now
                    pinch_ignored = now < cooldown_until
                    pinch_point = (int(pinch_point_now[0]), int(pinch_point_now[1]))
                    with GESTURE_LOCK:
                        GESTURE_STATUS["lastPinchAt"] = now
                    if pinch_ignored:
                        gesture_log("pinch started during cooldown; release will be ignored", key="pinch_cooldown_start", min_interval_s=0.8)
                    else:
                        if smooth_ratio is None:
                            gesture_log(f"pinch detected @ ({pinch_point[0]}, {pinch_point[1]})")
                        else:
                            gesture_log(f"pinch detected @ ({pinch_point[0]}, {pinch_point[1]}), ratio={smooth_ratio:.4f}")
                else:
                    pinch_point = (int(pinch_point_now[0]), int(pinch_point_now[1]))
            else:
                if pinch_down:
                    hold_ms = max(0.0, (now - pinch_started_at) * 1000.0)
                    act_x = int(pinch_point[0]) if pinch_point else int(tracking_x)
                    act_y = int(pinch_point[1]) if pinch_point else int(tracking_y)
                    if pinch_ignored or now < cooldown_until:
                        gesture_log("pinch release ignored due cooldown", key="pinch_release_cooldown", min_interval_s=0.8)
                    else:
                        click_kind = "left" if hold_ms <= max(40.0, hold_ms_threshold) else "right"
                        action_name = "left_click" if click_kind == "left" else "two_finger_click"
                        ok, err = _gesture_click(click_kind, act_x, act_y)
                        if ok:
                            cooldown_until = now + max(0.0, inactive_ms) / 1000.0
                            with GESTURE_LOCK:
                                GESTURE_STATUS["lastAction"] = action_name
                                GESTURE_STATUS["lastActionAt"] = now
                                GESTURE_STATUS["lastActionX"] = int(act_x)
                                GESTURE_STATUS["lastActionY"] = int(act_y)
                                if action_name == "two_finger_click":
                                    GESTURE_STATUS["lastTwoFingerAt"] = now
                                GESTURE_STATUS["lastError"] = ""
                            if action_name == "two_finger_click":
                                gesture_log(
                                    f"pinch hold release ({hold_ms:.0f}ms) -> two-finger click @ ({act_x}, {act_y})"
                                )
                            else:
                                gesture_log(
                                    f"pinch release ({hold_ms:.0f}ms) -> single click @ ({act_x}, {act_y})"
                                )
                        else:
                            with GESTURE_LOCK:
                                GESTURE_STATUS["lastError"] = err
                            gesture_log(f"pinch release click failed: {err}", key="pinch_click_err", min_interval_s=0.8)
                pinch_down = False
                pinch_started_at = 0.0
                pinch_point = None
                pinch_ignored = False

            _put_overlay_info(overlay, f"hands: {hands_detected}", 0, (200, 230, 255))
            _put_overlay_info(
                overlay,
                f"pinch ratio: {smooth_ratio:.4f}" if smooth_ratio is not None else "pinch ratio: n/a",
                1,
            )
            _put_overlay_info(
                overlay,
                f"pinch active: {pinch_down}",
                2,
                (120, 255, 120) if pinch_down else (255, 210, 120),
            )
            _put_overlay_info(
                overlay,
                f"hold ms: {max(0, int((now - pinch_started_at) * 1000)) if pinch_down else 0} / {int(hold_ms_threshold)}",
                3,
            )
            _put_overlay_info(
                overlay,
                f"cooldown ms: {max(0, int((cooldown_until - now) * 1000))}",
                4,
            )
            _put_overlay_info(
                overlay,
                f"drag hand spread: {drag_hand_spread} (adj>{drag_adj_min_ratio:.2f} thumb>{drag_thumb_index_min_ratio:.2f})",
                5,
                (140, 255, 180) if drag_hand_spread else (255, 190, 130),
            )
            _put_overlay_info(
                overlay,
                f"tracking: {'ENABLED' if tracking_enabled else 'DISABLED'} ({tracking_disable_reason})",
                6,
                (120, 255, 120) if tracking_enabled else (255, 170, 120),
            )
            _put_overlay_info(
                overlay,
                f"drag span: {drag_hand_span_px:.1f}px (w={drag_hand_box_w_px:.1f}, h={drag_hand_box_h_px:.1f})",
                7,
                (140, 220, 255),
            )
            h, w = overlay.shape[:2]
            tx = int(tracking_center_norm[0] * w)
            ty = int(tracking_center_norm[1] * h)
            cv2.circle(
                overlay,
                (tx, ty),
                10,
                (120, 255, 150) if tracking_enabled else (220, 180, 100),
                2,
                cv2.LINE_AA,
            )
            cv2.line(overlay, (tx - 12, ty), (tx + 12, ty), (255, 255, 255), 1, cv2.LINE_AA)
            cv2.line(overlay, (tx, ty - 12), (tx, ty + 12), (255, 255, 255), 1, cv2.LINE_AA)
            _update_overlay_frame(overlay)

            with GESTURE_LOCK:
                GESTURE_STATUS["enabled"] = True
                GESTURE_STATUS["framesProcessed"] = int(GESTURE_STATUS.get("framesProcessed", 0)) + 1
                GESTURE_STATUS["handsDetected"] = int(hands_detected)
                GESTURE_STATUS["pinchActive"] = bool(pinch_down)
                GESTURE_STATUS["lastPinchRatio"] = -1.0 if smooth_ratio is None else float(smooth_ratio)
                GESTURE_STATUS["pinchHoldMs"] = max(0.0, (now - pinch_started_at) * 1000.0) if pinch_down else 0.0
                GESTURE_STATUS["pinchHoldThresholdMs"] = float(hold_ms_threshold)
                GESTURE_STATUS["pendingSingle"] = False
                GESTURE_STATUS["pendingDeadline"] = 0.0
                GESTURE_STATUS["cooldownUntil"] = float(cooldown_until)
                GESTURE_STATUS["lastProcessAt"] = now
                GESTURE_STATUS["lastPinchDistance"] = -1.0 if smooth_ratio is None else float(smooth_ratio)
                GESTURE_STATUS["dragHandDetected"] = bool(drag_hand_found)
                GESTURE_STATUS["dragHandSpread"] = bool(drag_hand_spread)
                GESTURE_STATUS["dragHandSpanPx"] = float(max(0.0, drag_hand_span_px))
                GESTURE_STATUS["dragHandBoxWpx"] = float(max(0.0, drag_hand_box_w_px))
                GESTURE_STATUS["dragHandBoxHpx"] = float(max(0.0, drag_hand_box_h_px))
                drag_center_for_status = (
                    drag_hand_center
                    if drag_hand_center is not None
                    else (drag_hand_center_any if drag_hand_center_any is not None else tracking_center_norm)
                )
                GESTURE_STATUS["dragHandCenterNormX"] = float(drag_center_for_status[0])
                GESTURE_STATUS["dragHandCenterNormY"] = float(drag_center_for_status[1])
                GESTURE_STATUS["leftHandDetected"] = bool(drag_hand_found)  # compatibility
                GESTURE_STATUS["leftHandSpread"] = bool(drag_hand_spread)   # compatibility
                GESTURE_STATUS["trackingEnabled"] = bool(tracking_enabled)
                GESTURE_STATUS["trackingReason"] = "active" if tracking_enabled else str(tracking_disable_reason)
                GESTURE_STATUS["trackingDisableReason"] = "active" if tracking_enabled else str(tracking_disable_reason)
                GESTURE_STATUS["trackingCenterNormX"] = float(tracking_center_norm[0])
                GESTURE_STATUS["trackingCenterNormY"] = float(tracking_center_norm[1])
                GESTURE_STATUS["trackingX"] = int(tracking_x)
                GESTURE_STATUS["trackingY"] = int(tracking_y)
                GESTURE_STATUS["trackingUpdatedAt"] = now
                GESTURE_STATUS["dragScaleGain"] = float(drag_scale_gain)

            time.sleep(0.005)


def start_gesture_thread_once():
    global _GESTURE_THREAD_STARTED
    if _GESTURE_THREAD_STARTED:
        return
    def run_worker():
        try:
            gesture_worker()
        except Exception as exc:
            with GESTURE_LOCK:
                GESTURE_STATUS["lastError"] = str(exc)
            gesture_log(f"gesture worker stopped: {exc}")
    t = threading.Thread(target=run_worker, daemon=True)
    t.start()
    _GESTURE_THREAD_STARTED = True
    gesture_log("gesture worker thread started")


# ---------- Pages ----------
@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/host")
def host_page():
    return app.send_static_file("host.html")


@app.route("/gesture_host")
def gesture_host_page():
    return app.send_static_file("gesture_host.html")


# ---------- WebRTC signaling ----------
SIGNAL_LOCK = threading.Lock()
HOST_OFFER = None
VIEWER_ANSWER = None
HOST_CANDIDATES = []
VIEWER_CANDIDATES = []


@app.route("/signal/host_offer", methods=["GET", "POST"])
def signal_host_offer():
    global HOST_OFFER, VIEWER_ANSWER, HOST_CANDIDATES, VIEWER_CANDIDATES
    with SIGNAL_LOCK:
        if request.method == "POST":
            HOST_OFFER = request.get_json(silent=True) or None
            VIEWER_ANSWER = None
            HOST_CANDIDATES = []
            VIEWER_CANDIDATES = []
            return jsonify(ok=True)
        return jsonify(HOST_OFFER or {})


@app.route("/signal/viewer_answer", methods=["GET", "POST"])
def signal_viewer_answer():
    global VIEWER_ANSWER
    with SIGNAL_LOCK:
        if request.method == "POST":
            VIEWER_ANSWER = request.get_json(silent=True) or None
            return jsonify(ok=True)
        return jsonify(VIEWER_ANSWER or {})


@app.route("/signal/host_candidates", methods=["GET", "POST"])
def signal_host_candidates():
    global HOST_CANDIDATES
    with SIGNAL_LOCK:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            cand = data.get("candidate")
            if cand:
                HOST_CANDIDATES.append(cand)
            return jsonify(ok=True, count=len(HOST_CANDIDATES))
        out = HOST_CANDIDATES
        HOST_CANDIDATES = []
        return jsonify(out)


@app.route("/signal/viewer_candidates", methods=["GET", "POST"])
def signal_viewer_candidates():
    global VIEWER_CANDIDATES
    with SIGNAL_LOCK:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            cand = data.get("candidate")
            if cand:
                VIEWER_CANDIDATES.append(cand)
            return jsonify(ok=True, count=len(VIEWER_CANDIDATES))
        out = VIEWER_CANDIDATES
        VIEWER_CANDIDATES = []
        return jsonify(out)


# ---------- Browser auto-launch ----------
BRAVE_PROC = None

def guess_local_ip():
    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        pass
    return ip


def launch_brave_with_flags(url):
    global BRAVE_PROC
    if os.environ.get("VR_OPEN_BROWSER", "1").lower() in ("0", "false", "no"):
        return
    brave_path_env = os.environ.get("VR_BRAVE_PATH")
    if brave_path_env and os.path.exists(brave_path_env):
        brave_path = brave_path_env
    else:
        brave_path = None
        for p in [
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Brave-Browser.app/Contents/MacOS/Brave Browser",
        ]:
            if os.path.exists(p):
                brave_path = p
                break
    if not brave_path:
        print("[Brave] Not found at default paths; open /host manually.")
        return

    flags = [
        "--new-window",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--disable-background-networking",
        "--allow-insecure-localhost",
    ]
    ignore_cert = os.environ.get("VR_BRAVE_IGNORE_CERT_ERRORS", "0").strip().lower() not in ("0", "false", "no")
    if ignore_cert:
        # Local prototype only; avoids self-signed cert handshake spam in Brave logs.
        flags.append("--ignore-certificate-errors")
    try:
        BRAVE_PROC = subprocess.Popen(
            [brave_path, url] + flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("[Brave] launched (quiet mode).")
    except Exception as e:
        BRAVE_PROC = None
        print(f"[Brave] launch failed: {e}")


def kill_brave_if_running():
    global BRAVE_PROC
    if BRAVE_PROC is None:
        return
    try:
        if BRAVE_PROC.poll() is None:
            BRAVE_PROC.terminate()
            try:
                BRAVE_PROC.wait(timeout=3)
            except subprocess.TimeoutExpired:
                BRAVE_PROC.kill()
        print("[Brave] terminated.")
    except Exception as e:
        print(f"[Brave] terminate error: {e}")
    finally:
        BRAVE_PROC = None


# ---------- Server lifecycle ----------
SERVER_THREAD = None
HTTP_SERVER = None
SERVER_PORT = int(os.environ.get("VR_PORT", "8443"))
CERT_FILE = os.environ.get("VR_CERT_FILE", os.path.join(ROOT_DIR, "certs", "localhost.pem"))
KEY_FILE = os.environ.get("VR_KEY_FILE", os.path.join(ROOT_DIR, "certs", "localhost-key.pem"))


def _guess_ip_from_cert_filename(path):
    base = os.path.basename(path or "")
    stem = os.path.splitext(base)[0]
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", stem):
        return stem
    return None


if os.environ.get("VR_HOST_IP"):
    HOST_IP = os.environ.get("VR_HOST_IP")
else:
    _guess_ip = guess_local_ip()
    if _guess_ip and (not _guess_ip.startswith("127.")):
        HOST_IP = _guess_ip
    else:
        HOST_IP = _guess_ip_from_cert_filename(CERT_FILE) or _guess_ip or "127.0.0.1"

BIND_HOST = os.environ.get("VR_BIND_HOST", "0.0.0.0")
HOST_URL = f"https://{HOST_IP}:{SERVER_PORT}/host"
VIEWER_URL = f"https://{HOST_IP}:{SERVER_PORT}/"
GESTURE_HOST_URL = f"https://{HOST_IP}:{SERVER_PORT}/gesture_host"


def _port_in_use(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.2)
    try:
        return sock.connect_ex(("127.0.0.1", int(port))) == 0
    finally:
        sock.close()


def copy_to_clipboard(text):
    try:
        subprocess.run(["pbcopy"], input=str(text).encode("utf-8"), check=True)
        return True, ""
    except Exception as e:
        return False, str(e)


def _list_port_pids(port):
    try:
        out = subprocess.check_output(["lsof", "-nP", "-ti", f"tcp:{int(port)}"], text=True)
    except Exception:
        return []
    pids = []
    for raw in out.splitlines():
        raw = raw.strip()
        if raw.isdigit():
            pids.append(int(raw))
    return sorted(set(pids))


def free_port(port):
    # Never terminate an unrelated process merely because it owns this port.
    return [], [f"Port {port} is occupied. Stop its owner manually or set VR_PORT."]


def start_server_background():
    global SERVER_THREAD, HTTP_SERVER
    if SERVER_THREAD is not None and SERVER_THREAD.is_alive():
        return
    if not os.path.isfile(CERT_FILE) or not os.path.isfile(KEY_FILE):
        raise RuntimeError("TLS files missing. Run .venv/bin/python scripts/setup_certs.py --host YOUR_MAC_IP; see docs/setup.md.")
    if _port_in_use(SERVER_PORT):
        raise RuntimeError(f"Port {SERVER_PORT} is busy; stop its owner or set VR_PORT.")
    HTTP_SERVER = make_server(BIND_HOST, SERVER_PORT, app, threaded=True,
                              ssl_context=(CERT_FILE, KEY_FILE))
    SERVER_THREAD = threading.Thread(target=HTTP_SERVER.serve_forever, daemon=True)
    SERVER_THREAD.start()
    start_phone_link_monitor_once()
    start_gesture_thread_once()


def stop_server_background():
    global HTTP_SERVER, SERVER_THREAD
    with SET_LOCK:
        SETTINGS["cursorEnabled"] = False
        SETTINGS["gestureEnabled"] = False
    if HTTP_SERVER is not None:
        HTTP_SERVER.shutdown()
        HTTP_SERVER.server_close()
        HTTP_SERVER = None
    if SERVER_THREAD is not None:
        SERVER_THREAD.join(timeout=3)
        SERVER_THREAD = None


# ---------- Notebook GUI controls (ipywidgets) ----------
def _ui_update_loop(status_html, gesture_log_html):
    while True:
        try:
            with GESTURE_LOCK:
                st = dict(GESTURE_STATUS)
            now = time.time()
            cool_ms = max(0, int((st.get("cooldownUntil", 0.0) - now) * 1000))
            pend_ms = max(0, int((st.get("pendingDeadline", 0.0) - now) * 1000))
            hold_ms = float(st.get("pinchHoldMs", 0.0))
            hold_thr = float(st.get("pinchHoldThresholdMs", DEFAULT_GESTURE_DOUBLE_MS))
            hb_age_ms = max(0, int((now - float(st.get("lastHeartbeatAt", 0.0))) * 1000)) if st.get("lastHeartbeatAt") else 9999999
            status_html.value = (
                "<div style='font-family:Menlo,Consolas,monospace;font-size:12px;'>"
                f"<b>Gesture</b> enabled={st.get('enabled')} | pinch={st.get('pinchActive')} | "
                f"hold={hold_ms:.0f}/{hold_thr:.0f}ms | pending={st.get('pendingSingle')} ({pend_ms}ms) | cooldown={cool_ms}ms<br/>"
                f"phoneConnected={st.get('phoneConnected')} hbAge={hb_age_ms}ms | cursorAutoSuppressed={st.get('cursorAutoSuppressed')}<br/>"
                f"dragHand={st.get('dragHandDetected')} spread={st.get('dragHandSpread')} | "
                f"spanPx={float(st.get('dragHandSpanPx', 0.0)):.1f} (w={float(st.get('dragHandBoxWpx', 0.0)):.1f}, h={float(st.get('dragHandBoxHpx', 0.0)):.1f}) | "
                f"tracking={st.get('trackingEnabled')} reason={html.escape(str(st.get('trackingDisableReason') or 'none'))} | "
                f"scaleGain={float(st.get('dragScaleGain', 1.0)):.2f}<br/>"
                f"trackPos=({st.get('trackingX')}, {st.get('trackingY')}) norm=({float(st.get('trackingCenterNormX', 0.5)):.3f}, {float(st.get('trackingCenterNormY', 0.5)):.3f}) | "
                f"lastAction={st.get('lastAction')} @ ({st.get('lastActionX')}, {st.get('lastActionY')}) | "
                f"pinchRatio={st.get('lastPinchRatio', -1.0):.4f}<br/>"
                f"MediaPipe={'ok' if st.get('mediapipeAvailable') else 'missing'}"
                f"{' - ' + st.get('mediapipeError') if st.get('mediapipeError') else ''}<br/>"
                f"lastError={html.escape(st.get('lastError') or 'none')}"
                "</div>"
            )

            with GESTURE_LOG_LOCK:
                tail = list(GESTURE_LOGS)[-14:]
            if tail:
                rendered = "<br/>".join(html.escape(x) for x in tail)
            else:
                rendered = "<span style='color:#666'>No gesture logs yet.</span>"
            gesture_log_html.value = (
                "<div style='font-family:Menlo,Consolas,monospace;font-size:12px;"
                "max-height:220px;overflow:auto;background:#111;color:#d9f99d;"
                "padding:8px;border-radius:8px;border:1px solid #333;'>"
                f"{rendered}</div>"
            )
        except Exception:
            pass
        time.sleep(0.25)


def _bump_setting_from_widget(key, cast_fn=float):
    def _handler(change):
        if change.get("name") != "value":
            return
        try:
            val = cast_fn(change.get("new"))
            _set_setting(key, val, origin="server")
        except Exception:
            pass
    return _handler


def build_notebook_gui():
    global _has_widgets, widgets, display
    if not _has_widgets:
        try:
            import ipywidgets as widgets  # type: ignore[no-redef]
            from IPython.display import display  # type: ignore[no-redef]
            _has_widgets = True
        except Exception as e:
            _has_widgets = False
            print(f"ipywidgets import failed: {e}")
            try:
                print("Attempting auto-install: pip install ipywidgets ...")
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "ipywidgets"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                import ipywidgets as widgets  # type: ignore[no-redef]
                from IPython.display import display  # type: ignore[no-redef]
                _has_widgets = True
                print("ipywidgets installed successfully for this environment.")
            except Exception as e_install:
                _has_widgets = False
                print(f"ipywidgets auto-install failed: {e_install}")

    if not _has_widgets:
        try:
            from IPython.display import HTML, display as _display_html  # type: ignore
            _display_html(
                HTML(
                    "<div style='border:1px solid #444;border-radius:10px;padding:12px;"
                    "background:#111;color:#e5e7eb;font-family:Menlo,Consolas,monospace;'>"
                    "<div style='font-weight:700;font-size:16px;margin-bottom:6px;'>GUI unavailable (ipywidgets missing)</div>"
                    "<div>Please run in a notebook cell:</div>"
                    "<pre style='margin:8px 0 0 0;background:#000;padding:8px;border-radius:8px;'>%pip install ipywidgets</pre>"
                    "<div style='margin-top:8px;'>Then restart kernel and run the server cell again.</div>"
                    "</div>"
                )
            )
        except Exception:
            _has_widgets = False
        print("ipywidgets is unavailable; GUI cannot be rendered in-notebook.")
        print("Run: %pip install ipywidgets  then restart kernel and run this cell again.")
        return

    # Header card
    header = widgets.HTML(
        value=(
            "<div style='padding:10px 12px;border:1px solid #2d3748;border-radius:10px;"
            "background:linear-gradient(180deg,#0b1220,#111827);color:#e5e7eb;'>"
            "<div style='font-size:18px;font-weight:700;margin-bottom:6px;'>VR v4.4.1 Control Panel</div>"
            f"<div>Root: <code>{ROOT_DIR}</code></div>"
            f"<div>Host: <a href='{HOST_URL}' target='_blank' style='color:#93c5fd'>{HOST_URL}</a></div>"
            f"<div>Viewer: <a href='{VIEWER_URL}' target='_blank' style='color:#93c5fd'>{VIEWER_URL}</a></div>"
            f"<div>Gesture Host: <a href='{GESTURE_HOST_URL}' target='_blank' style='color:#93c5fd'>{GESTURE_HOST_URL}</a></div>"
            "</div>"
        )
    )

    # Command buttons
    recenter_btn = widgets.Button(description="Recenter", button_style="warning", icon="crosshairs")
    launch_btn = widgets.Button(description="Open Host", button_style="info", icon="external-link")
    gesture_launch_btn = widgets.Button(description="Open Gesture Host", button_style="", icon="eye")
    copy_phone_btn = widgets.Button(description="Copy Phone URL", button_style="", icon="copy")
    free_port_btn = widgets.Button(description="Stop / Check Port", button_style="", icon="plug")
    quit_btn = widgets.Button(description="Quit Server", button_style="danger", icon="stop")

    def _on_recenter(_):
        with SET_LOCK:
            SETTINGS["recenterNonce"] += 1
            SETTINGS["version"] += 1
            SETTINGS["origin"] = "server"
        gesture_log("manual recenter requested from notebook GUI")

    def _on_quit(_):
        gesture_log("quit requested from notebook GUI")
        kill_brave_if_running()
        stop_server_background()

    def _on_launch(_):
        launch_brave_with_flags(HOST_URL)

    def _on_launch_gesture(_):
        launch_brave_with_flags(GESTURE_HOST_URL)

    def _on_copy_phone(_):
        ok, err = copy_to_clipboard(VIEWER_URL)
        if ok:
            gesture_log(f"copied phone URL to clipboard: {VIEWER_URL}")
        else:
            gesture_log(f"copy phone URL failed: {err}", key="copy_url_err", min_interval_s=0.8)

    def _on_free_port(_):
        gesture_log(f"free port requested for {SERVER_PORT}")
        stop_server_background()
        killed, failures = free_port(SERVER_PORT)
        alive = [pid for pid in _list_port_pids(SERVER_PORT) if pid != os.getpid()]
        if alive:
            gesture_log(f"port {SERVER_PORT} still busy by pids={alive}", key="free_port_busy", min_interval_s=0.4)
        elif killed:
            gesture_log(f"port {SERVER_PORT} freed; terminated pids={killed}")
        else:
            gesture_log(f"port {SERVER_PORT} already free")
        if failures:
            gesture_log(f"free-port warnings: {'; '.join(failures[:3])}", key="free_port_warn", min_interval_s=0.8)

    recenter_btn.on_click(_on_recenter)
    launch_btn.on_click(_on_launch)
    gesture_launch_btn.on_click(_on_launch_gesture)
    copy_phone_btn.on_click(_on_copy_phone)
    free_port_btn.on_click(_on_free_port)
    quit_btn.on_click(_on_quit)

    # Toggles / dropdowns
    converge_cb = widgets.Checkbox(value=bool(SETTINGS["converge"]), description="Converge")
    cam_enabled_cb = widgets.Checkbox(value=bool(SETTINGS["camEnabled"]), description="Cam On")
    cursor_enabled_cb = widgets.Checkbox(value=bool(SETTINGS["cursorEnabled"]), description="Gaze Cursor")
    gesture_enabled_cb = widgets.Checkbox(value=bool(SETTINGS["gestureEnabled"]), description="Pinch Click")
    mirror_cb = widgets.Checkbox(value=bool(SETTINGS["gestureMirrorX"]), description="Mirror X")
    drag_detect_cb = widgets.Checkbox(value=bool(SETTINGS["gestureDragDetectEnabled"]), description="Drag Detect")
    keypoint_stream_cb = widgets.Checkbox(value=bool(SETTINGS["gestureKeypointStreamEnabled"]), description="Keypoint Stream")
    swap_hands_cb = widgets.Checkbox(value=bool(SETTINGS["gestureSwapHands"]), description="Swap Drag Hand")

    cam_lens_dd = widgets.Dropdown(options=["normal", "wide"], value=SETTINGS["camLens"], description="Cam Lens")
    cam_feed_dd = widgets.Dropdown(
        options=[
            ("Low (default, fastest)", "low"),
            ("Balanced", "balanced"),
            ("Clear", "clear"),
            ("Ultra Clear (heaviest)", "ultra_clear"),
        ],
        value=str(SETTINGS.get("camFeedProfile", "low")),
        description="Cam Clarity",
    )
    cam_blend_dd = widgets.Dropdown(options=["screen", "normal"], value=SETTINGS["camBlend"], description="Cam Blend")
    filter_dd = widgets.Dropdown(options=[("Simple", "simple"), ("One-Euro", "one_euro")], value=SETTINGS["filterMode"], description="Filter")

    converge_cb.observe(_bump_setting_from_widget("converge", bool), names="value")
    cam_enabled_cb.observe(_bump_setting_from_widget("camEnabled", bool), names="value")
    cursor_enabled_cb.observe(_bump_setting_from_widget("cursorEnabled", bool), names="value")
    gesture_enabled_cb.observe(_bump_setting_from_widget("gestureEnabled", bool), names="value")
    mirror_cb.observe(_bump_setting_from_widget("gestureMirrorX", bool), names="value")
    drag_detect_cb.observe(_bump_setting_from_widget("gestureDragDetectEnabled", bool), names="value")
    keypoint_stream_cb.observe(_bump_setting_from_widget("gestureKeypointStreamEnabled", bool), names="value")
    swap_hands_cb.observe(_bump_setting_from_widget("gestureSwapHands", bool), names="value")
    cam_lens_dd.observe(_bump_setting_from_widget("camLens", str), names="value")
    cam_blend_dd.observe(_bump_setting_from_widget("camBlend", str), names="value")
    filter_dd.observe(_bump_setting_from_widget("filterMode", str), names="value")

    def _on_cam_feed_profile(change):
        if change.get("name") != "value":
            return
        profile = str(change.get("new", "low")).strip().lower()
        if profile not in CAM_FEED_PRESETS:
            return
        with SET_LOCK:
            if _apply_cam_feed_profile_locked(profile):
                SETTINGS["version"] += 1
                SETTINGS["origin"] = "server"
        preset = CAM_FEED_PRESETS.get(profile, {})
        gesture_log(
            f"outside camera profile -> {profile} ({int(preset.get('camMaxWidth', 0))}x"
            f"{int(preset.get('camMaxHeight', 0))}@{int(preset.get('camMaxFps', 0))}fps)"
        )

    cam_feed_dd.observe(_on_cam_feed_profile, names="value")

    # Sliders
    screen_scale = widgets.FloatSlider(value=float(SETTINGS["screenScale"]), min=0.20, max=6.00, step=0.01, description="Scale")
    screen_dist = widgets.FloatSlider(value=float(SETTINGS["screenDist"]), min=0.30, max=8.00, step=0.01, description="Dist")
    curve_radius = widgets.FloatSlider(value=float(SETTINGS["screenCurveRadius"]), min=1.0, max=30.0, step=0.1, description="Curve R")
    eye_px = widgets.FloatSlider(value=float(SETTINGS["eyePx"]), min=-60.0, max=60.0, step=1.0, description="Eye Px")
    cam_opacity = widgets.FloatSlider(value=float(SETTINGS["camOpacity"]), min=0.0, max=100.0, step=1.0, description="Cam %")

    gesture_inactive = widgets.IntSlider(value=int(SETTINGS["gestureInactiveMs"]), min=150, max=2000, step=10, description="Inactive ms")
    gesture_double = widgets.IntSlider(value=int(SETTINGS["gestureDoublePinchMs"]), min=200, max=2500, step=10, description="Hold ms")
    gesture_on = widgets.FloatSlider(value=float(SETTINGS["gesturePinchOn"]), min=0.08, max=0.60, step=0.005, readout_format=".3f", description="Pinch On")
    gesture_off = widgets.FloatSlider(value=float(SETTINGS["gesturePinchOff"]), min=0.12, max=0.80, step=0.005, readout_format=".3f", description="Pinch Off")
    gesture_fw = widgets.IntSlider(value=int(SETTINGS["gestureFrameWidth"]), min=224, max=640, step=8, description="Frame W")
    gesture_fh = widgets.IntSlider(value=int(SETTINGS["gestureFrameHeight"]), min=160, max=480, step=8, description="Frame H")
    gesture_fps = widgets.IntSlider(value=int(SETTINGS["gestureFrameFps"]), min=4, max=24, step=1, description="Frame FPS")
    drag_adj = widgets.FloatSlider(
        value=float(SETTINGS["gestureDragAdjMinRatio"]), min=0.10, max=0.60, step=0.01,
        readout_format=".2f", description="Drag Sep"
    )
    drag_thumb = widgets.FloatSlider(
        value=float(SETTINGS["gestureDragThumbIndexMinRatio"]), min=0.10, max=0.90, step=0.01,
        readout_format=".2f", description="Thumb Gap"
    )
    drag_extend = widgets.FloatSlider(
        value=float(SETTINGS["gestureDragExtendRatio"]), min=1.00, max=1.60, step=0.01,
        readout_format=".2f", description="Finger Ext"
    )
    drag_scale_gain = widgets.FloatSlider(
        value=float(SETTINGS["gestureDragScaleGain"]), min=0.40, max=3.00, step=0.02,
        readout_format=".2f", description="Drag Scale Gain"
    )

    host_w = widgets.IntSlider(value=int(SETTINGS["hostRenderWidth"]), min=640, max=6400, step=40, description="Host W")
    host_h = widgets.IntSlider(value=int(SETTINGS["hostRenderHeight"]), min=360, max=3600, step=20, description="Host H")
    mjpeg_w = widgets.IntSlider(value=int(SETTINGS["mjpegWidth"]), min=640, max=12000, step=80, description="MJPEG W")
    mjpeg_fps = widgets.IntSlider(value=int(SETTINGS["mjpegFps"]), min=5, max=60, step=1, description="MJPEG FPS")
    tex_w = widgets.IntSlider(value=int(SETTINGS["hostTextureWidth"]), min=1024, max=6144, step=64, description="Tex W")
    overlay_fps = widgets.IntSlider(value=int(SETTINGS["gestureOverlayFps"]), min=4, max=30, step=1, description="Overlay FPS")
    overlay_q = widgets.IntSlider(value=int(SETTINGS["gestureOverlayJpegQuality"]), min=40, max=95, step=1, description="Overlay Q")
    preset_dd = widgets.Dropdown(
        options=[
            ("Ultra Clear (max quality)", "ultra_clear"),
            ("Clear (default)", "clear_default"),
            ("Balanced", "balanced"),
            ("Low Latency", "low_latency"),
            ("Ultra Latency", "ultra_latency"),
        ],
        value="ultra_clear",
        description="Preset",
    )
    preset_apply_btn = widgets.Button(description="Apply Preset", button_style="primary", icon="sliders")

    screen_scale.observe(_bump_setting_from_widget("screenScale", float), names="value")
    screen_dist.observe(_bump_setting_from_widget("screenDist", float), names="value")
    curve_radius.observe(_bump_setting_from_widget("screenCurveRadius", float), names="value")
    eye_px.observe(_bump_setting_from_widget("eyePx", float), names="value")
    cam_opacity.observe(_bump_setting_from_widget("camOpacity", float), names="value")

    gesture_inactive.observe(_bump_setting_from_widget("gestureInactiveMs", float), names="value")
    gesture_double.observe(_bump_setting_from_widget("gestureDoublePinchMs", float), names="value")
    gesture_on.observe(_bump_setting_from_widget("gesturePinchOn", float), names="value")
    gesture_off.observe(_bump_setting_from_widget("gesturePinchOff", float), names="value")
    gesture_fw.observe(_bump_setting_from_widget("gestureFrameWidth", float), names="value")
    gesture_fh.observe(_bump_setting_from_widget("gestureFrameHeight", float), names="value")
    gesture_fps.observe(_bump_setting_from_widget("gestureFrameFps", float), names="value")
    drag_adj.observe(_bump_setting_from_widget("gestureDragAdjMinRatio", float), names="value")
    drag_thumb.observe(_bump_setting_from_widget("gestureDragThumbIndexMinRatio", float), names="value")
    drag_extend.observe(_bump_setting_from_widget("gestureDragExtendRatio", float), names="value")
    drag_scale_gain.observe(_bump_setting_from_widget("gestureDragScaleGain", float), names="value")

    host_w.observe(_bump_setting_from_widget("hostRenderWidth", float), names="value")
    host_h.observe(_bump_setting_from_widget("hostRenderHeight", float), names="value")
    mjpeg_w.observe(_bump_setting_from_widget("mjpegWidth", float), names="value")
    mjpeg_fps.observe(_bump_setting_from_widget("mjpegFps", float), names="value")
    tex_w.observe(_bump_setting_from_widget("hostTextureWidth", float), names="value")
    overlay_fps.observe(_bump_setting_from_widget("gestureOverlayFps", float), names="value")
    overlay_q.observe(_bump_setting_from_widget("gestureOverlayJpegQuality", float), names="value")

    def _apply_resolution_preset(preset_key):
        preset = RESOLUTION_PRESETS.get(str(preset_key))
        if not preset:
            return
        host_w.value = int(round(float(preset["hostRenderWidth"])))
        host_h.value = int(round(float(preset["hostRenderHeight"])))
        mjpeg_w.value = int(round(float(preset["mjpegWidth"])))
        mjpeg_fps.value = int(round(float(preset["mjpegFps"])))
        tex_w.value = int(round(float(preset["hostTextureWidth"])))
        gesture_log(
            f"resolution preset applied: {preset_key} -> host={int(host_w.value)}x{int(host_h.value)}, "
            f"mjpegW={int(mjpeg_w.value)}, mjpegFps={int(mjpeg_fps.value)}, texW={int(tex_w.value)}"
        )

    def _on_apply_preset(_):
        _apply_resolution_preset(preset_dd.value)

    preset_apply_btn.on_click(_on_apply_preset)

    status_html = widgets.HTML(value="<i>starting...</i>")
    gesture_log_html = widgets.HTML(value="<i>no logs yet...</i>")
    threading.Thread(target=_ui_update_loop, args=(status_html, gesture_log_html), daemon=True).start()

    def _slider_help(slider, text):
        help_html = widgets.HTML(
            value=f"<div style='font-size:11px;color:#9ca3af;margin:-6px 0 8px 4px;'>{html.escape(str(text))}</div>"
        )
        return widgets.VBox([slider, help_html], layout=widgets.Layout(width="100%"))

    button_bar = widgets.HBox(
        [recenter_btn, launch_btn, gesture_launch_btn, copy_phone_btn, free_port_btn, quit_btn],
        layout=widgets.Layout(gap="8px")
    )
    toggle_bar = widgets.HBox(
        [converge_cb, cam_enabled_cb, cursor_enabled_cb, gesture_enabled_cb, mirror_cb, drag_detect_cb, keypoint_stream_cb, swap_hands_cb],
        layout=widgets.Layout(gap="14px")
    )
    cam_feed_help = widgets.HTML(
        value=(
            "<div style='font-size:11px;color:#9ca3af;margin:0 0 4px 4px;'>"
            "Outside camera clarity profile (not MediaPipe upload). Higher levels are sharper but heavier."
            "</div>"
        )
    )
    enum_bar = widgets.VBox(
        [widgets.HBox([cam_lens_dd, cam_feed_dd, cam_blend_dd, filter_dd], layout=widgets.Layout(gap="12px")), cam_feed_help],
        layout=widgets.Layout(gap="2px")
    )

    tab_main = widgets.VBox(
        [
            _slider_help(screen_scale, "Virtual screen size. Higher value makes the mirrored screen larger in VR."),
            _slider_help(screen_dist, "Distance from your head to the center of the curved screen. Higher value pushes it farther."),
            _slider_help(curve_radius, "Curvature radius in meters. Lower value bends more; higher value looks flatter."),
            _slider_help(eye_px, "Stereo eye split offset. Adjust if depth/parallax feels too weak or too strong."),
            _slider_help(cam_opacity, "Opacity of the passthrough phone camera overlay. Lower = more transparent."),
        ],
        layout=widgets.Layout(padding="6px 4px")
    )
    tab_gesture = widgets.VBox(
        [
            _slider_help(gesture_inactive, "Cooldown after a click action. Higher value reduces accidental repeat clicks."),
            _slider_help(gesture_double, "Hold duration threshold for two-finger click. Release before this = single click."),
            _slider_help(gesture_on, "Pinch ON threshold. Lower makes pinch harder to trigger; higher makes it easier."),
            _slider_help(gesture_off, "Pinch OFF threshold. Keep this above Pinch ON for stable hysteresis."),
            _slider_help(gesture_fw, "Phone frame width sent to MediaPipe. Higher improves detail but adds latency/bandwidth."),
            _slider_help(gesture_fh, "Phone frame height sent to MediaPipe. Higher improves detail but adds latency/bandwidth."),
            _slider_help(gesture_fps, "Gesture analysis upload FPS from phone. Higher is smoother but heavier."),
            _slider_help(drag_adj, "Minimum adjacent-finger separation needed to count as a fully spread drag hand."),
            _slider_help(drag_thumb, "Minimum thumb-index separation needed for spread-hand drag detection."),
            _slider_help(drag_extend, "Finger extension strictness. Higher requires straighter fingers."),
            _slider_help(drag_scale_gain, "How strongly screen size reacts to hand distance while drag-hand is active."),
        ],
        layout=widgets.Layout(padding="6px 4px")
    )
    preset_row = widgets.HBox([preset_dd, preset_apply_btn], layout=widgets.Layout(gap="8px"))
    tab_perf = widgets.VBox(
        [
            preset_row,
            _slider_help(host_w, "Host WebGL render width. Higher gives sharper geometry but more GPU cost."),
            _slider_help(host_h, "Host WebGL render height. Higher gives sharper geometry but more GPU cost."),
            _slider_help(mjpeg_w, "Desktop capture stream width before host texture decode. Higher = clearer text, more load."),
            _slider_help(mjpeg_fps, "Desktop capture stream FPS. Higher = lower motion blur/lag, more bandwidth."),
            _slider_help(tex_w, "Host texture width used to paint the mirrored screen in VR. Higher greatly improves clarity."),
            _slider_help(overlay_fps, "Gesture debug overlay stream FPS for gesture_host page."),
            _slider_help(overlay_q, "Gesture debug overlay JPEG quality for gesture_host page."),
        ],
        layout=widgets.Layout(padding="6px 4px")
    )

    tabs = widgets.Tab(children=[tab_main, tab_gesture, tab_perf])
    tabs.set_title(0, "View")
    tabs.set_title(1, "Gesture")
    tabs.set_title(2, "Performance")

    logs_title = widgets.HTML("<b>Gesture Debug Logs</b>")
    logs_box = widgets.VBox([logs_title, gesture_log_html])

    root = widgets.VBox(
        [header, button_bar, toggle_bar, enum_bar, tabs, status_html, logs_box],
        layout=widgets.Layout(width="100%", gap="8px"),
    )
    display(root)
    gesture_log("notebook GUI rendered")


# ---------- Explicit startup; importing this module does not launch the server ----------
def start(notebook=False):
    start_server_background()
    print("Vision SE v4.4.1 is running (trusted local network only).")
    print(f"Host view (Mac): {HOST_URL}")
    print(f"Phone viewer (Safari, landscape): {VIEWER_URL}")
    print(f"Gesture debug view (Mac): {GESTURE_HOST_URL}")
    print(f"Pairing code: {PAIRING_CODE}")
    print("Enter this code in each browser. Paired devices can view and control the desktop.")
    print("Grant Screen Recording and Accessibility to your Python host app in macOS Settings.")
    print(f"MediaPipe: {'available' if _has_mediapipe else 'unavailable; install requirements-gestures.txt'}")
    copy_to_clipboard(VIEWER_URL)
    launch_brave_with_flags(HOST_URL)
    if notebook:
        build_notebook_gui()


if __name__ == "__main__":
    try:
        start()
        while SERVER_THREAD is not None and SERVER_THREAD.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    except (RuntimeError, OSError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        stop_server_background()
        kill_brave_if_running()
