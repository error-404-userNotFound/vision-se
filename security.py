"""Per-run device pairing for the local desktop server."""
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta
from threading import Lock
from flask import request, session, redirect, jsonify, render_template_string

PAIR_PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pair with Vision SE</title><style>
body{background:#10151e;color:#edf2fa;font:18px system-ui;max-width:460px;margin:12vh auto;padding:24px}
input,button{font:inherit;padding:12px;box-sizing:border-box;width:100%;margin-top:12px;border-radius:8px}
.error{color:#ffb9a8}</style><h1>Pair with Vision SE</h1>
<p>Enter the pairing code shown in the Mac terminal or notebook.</p>
<p>This browser will be able to view and control the Mac desktop until the server restarts or the session expires.</p>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post"><input name="code" type="password" autocomplete="off" required aria-label="Pairing code">
<button>Pair this browser</button></form></html>"""


def configure_pairing(app):
    code = secrets.token_hex(8)
    app.secret_key = secrets.token_bytes(32)
    app.config.update(SESSION_COOKIE_NAME="vision_se_session", SESSION_COOKIE_SECURE=True,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
                      SESSION_REFRESH_EACH_REQUEST=False,
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
                      MAX_CONTENT_LENGTH=4 * 1024 * 1024)
    attempts = defaultdict(deque)
    lock = Lock()

    @app.before_request
    def require_pairing():
        # Reject browser requests initiated from a different origin, including login CSRF.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("Origin")
            if ((origin and origin != request.host_url.rstrip("/")) or
                    request.headers.get("Sec-Fetch-Site") == "cross-site"):
                return jsonify(error="Cross-origin request rejected"), 403
        if request.path == "/pair":
            return None
        if not session.get("paired"):
            if request.path in ("/", "/host", "/gesture_host"):
                return redirect("/pair?next=" + request.path)
            return jsonify(error="Pair this browser at /pair first"), 401

    @app.after_request
    def security_headers(response):
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.path == "/pair":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/pair", methods=["GET", "POST"])
    def pair():
        error = None
        if request.method == "POST":
            now = time.monotonic()
            ip = request.remote_addr or "unknown"
            with lock:
                # Bound memory as well as per-address attempts.
                for key in list(attempts):
                    if not attempts[key] or attempts[key][-1] <= now - 60:
                        del attempts[key]
                if ip not in attempts and len(attempts) >= 1024:
                    return "Try again shortly", 429
                q = attempts[ip]
                while q and q[0] <= now - 60:
                    q.popleft()
                if len(q) >= 10:
                    return render_template_string(PAIR_PAGE, error="Too many attempts. Wait one minute."), 429
                q.append(now)
            supplied = request.form.get("code", "")
            if hmac.compare_digest(supplied.encode(), code.encode()):
                session.clear()
                session["paired"] = True
                session.permanent = True
                target = request.args.get("next", "/")
                if target not in ("/", "/host", "/gesture_host"):
                    target = "/"
                return redirect(target)
            error = "Incorrect pairing code."
        return render_template_string(PAIR_PAGE, error=error), (401 if error else 200)

    return code
