#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Callback Server (In-Memory RAM + HTML + Gmail Notification)
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse
from datetime import datetime
import os
import html as html_lib
import threading
import smtplib
from email.message import EmailMessage
import socket
import hashlib
import hmac
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Yerevan")


# ====================== CONFIG ======================
PORT = int(os.environ.get("PORT", 8090))

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 465))
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "")

ADMIN_LOGIN = os.environ.get("ADMIN_LOGIN", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
AUTH_SECRET = os.environ.get("AUTH_SECRET", hashlib.sha256(f"{ADMIN_LOGIN}:{ADMIN_PASSWORD}".encode("utf-8")).hexdigest())
AUTH_COOKIE_NAME = "callback_auth"


def make_auth_token():
    msg = f"{ADMIN_LOGIN}:{ADMIN_PASSWORD}".encode("utf-8")
    return hmac.new(AUTH_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def is_authenticated(handler):
    cookie_header = handler.headers.get("Cookie", "")
    expected = make_auth_token()
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith(AUTH_COOKIE_NAME + "="):
            val = part.split("=", 1)[1]
            if hmac.compare_digest(val, expected):
                return True
    return False


# ====================== IN-MEMORY (RAM) STORAGE ======================
_callbacks = []
_next_id = 1
_lock = threading.Lock()


def save_callback(phone):
    global _next_id
    with _lock:
        row = {
            "id": _next_id,
            "phone": phone,
            "created_at": datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
        }
        _next_id += 1
        _callbacks.append(row)


def get_callbacks():
    with _lock:
        rows_sorted = sorted(_callbacks, key=lambda x: x["id"], reverse=True)
        return [(r["id"], r["phone"], r["created_at"]) for r in rows_sorted]


def delete_callback(callback_id):
    try:
        target_id = int(callback_id)
    except (TypeError, ValueError):
        return
    with _lock:
        global _callbacks
        _callbacks = [r for r in _callbacks if r["id"] != target_id]


# ====================== MAIL SENDING ======================
def send_mail(phone):
    if not SENDER_EMAIL or not SMTP_PASSWORD or not RECEIVER_EMAIL:
        print("Failed to send email: missing SENDER_EMAIL, SMTP_PASSWORD, or RECEIVER_EMAIL", flush=True)
        return

    content = f"Զանգի պատվեր՝ {phone}"
    msg = EmailMessage()
    msg["Subject"] = content
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg.set_content(content)

    try:
        # Resolve IPv4 address explicitly to avoid IPv6 [Errno 101] Network is unreachable
        ipv4_host = socket.getaddrinfo(SMTP_HOST, SMTP_PORT, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]

        if SMTP_PORT == 587:
            with smtplib.SMTP(ipv4_host, SMTP_PORT, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SENDER_EMAIL, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(ipv4_host, SMTP_PORT, timeout=15) as server:
                server.login(SENDER_EMAIL, SMTP_PASSWORD)
                server.send_message(msg)

        print("Email sent successfully!", flush=True)
    except Exception as e:
        print(f"Failed to send email: {type(e).__name__}: {e}", flush=True)


# ====================== HTTP HANDLER ======================
class CallbackHandler(BaseHTTPRequestHandler):

    def render_login(self, error_msg=""):
        err_html = f'<p style="color:#d9534f;">{html_lib.escape(error_msg)}</p>' if error_msg else ""
        page = f"""<!DOCTYPE html>
<html>
<head>
  <title>Login</title>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Arial, sans-serif; margin: 60px; background: #f5f5f5; }}
    .box {{ width: 320px; background: white; padding: 24px; border: 1px solid #ccc; border-radius: 4px; }}
    input {{ width: 100%; box-sizing: border-box; padding: 9px; margin: 6px 0 14px 0; border: 1px solid #ccc; border-radius: 4px; }}
    button {{ width: 100%; background: #337ab7; color: white; border: none; padding: 10px; cursor: pointer; border-radius: 4px; }}
  </style>
</head>
<body>
  <div class="box">
    <h2>Login</h2>
    {err_html}
    <form method="POST" action="/login">
      <label for="username">Login</label>
      <input type="text" id="username" name="username" required autofocus>
      <label for="password">Password</label>
      <input type="password" id="password" name="password" required>
      <button type="submit">Log in</button>
    </form>
  </div>
</body>
</html>
"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/callback":
            params = parse_qs(parsed.query)
            phone = params.get("phoneNum", [None])[0]
            if phone:
                phone = phone.strip()
            if phone:
                save_callback(phone)
                print("Phone:", phone, flush=True)
                #send_mail(phone)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return

        if path == "/login":
            self.render_login()
            return

        if path == "/":
            if not is_authenticated(self):
                self.render_login()
                return

            callbacks = get_callbacks()

            html = """<!DOCTYPE html>
<html>
<head>
  <title>Callbacks</title>
  <meta charset="UTF-8">
  <style>
    body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
    h1 { margin-bottom: 20px; }
    table { border-collapse: collapse; width: 700px; background: white; }
    th, td { border: 1px solid #ccc; padding: 10px; text-align: left; }
    th { background: #eee; }
    button {
      background: #d9534f; color: white; border: none;
      padding: 7px 12px; cursor: pointer; border-radius: 4px;
    }
    button:hover { background: #c9302c; }
  </style>
</head>
<body>
  <h1>Callback Numbers</h1>
  <table>
    <tr>
      <th>Phone</th>
      <th>Date</th>
      <th>Action</th>
    </tr>
"""
            for callback_id, phone, created_at in callbacks:
                safe_phone = html_lib.escape(str(phone))
                safe_date = html_lib.escape(str(created_at))
                safe_id = html_lib.escape(str(callback_id))
                html += f"""
    <tr>
      <td>{safe_phone}</td>
      <td>{safe_date}</td>
      <td>
        <form method="POST" action="/delete" onsubmit="return confirm('Delete this callback?');">
          <input type="hidden" name="id" value="{safe_id}">
          <button type="submit">Delete</button>
        </form>
      </td>
    </tr>
"""

            html += """
  </table>
</body>
</html>
"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/login":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            params = parse_qs(body)
            username = params.get("username", [""])[0]
            password = params.get("password", [""])[0]
            if hmac.compare_digest(username, ADMIN_LOGIN) and hmac.compare_digest(password, ADMIN_PASSWORD):
                token = make_auth_token()
                self.send_response(303)
                self.send_header("Set-Cookie", f"{AUTH_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax")
                self.send_header("Location", "/")
                self.end_headers()
            else:
                self.render_login("Invalid login or password")
            return

        if path == "/delete":
            if not is_authenticated(self):
                self.render_login()
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            params = parse_qs(body)
            callback_id = params.get("id", [None])[0]
            if callback_id:
                delete_callback(callback_id)
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()


# ====================== START SERVER ======================
if __name__ == "__main__":
    HTTPServer.allow_reuse_address = True

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        pass

    server = ThreadedHTTPServer(("0.0.0.0", PORT), CallbackHandler)
    print(f"Server running on port {PORT} (RAM storage)...", flush=True)
    server.serve_forever()