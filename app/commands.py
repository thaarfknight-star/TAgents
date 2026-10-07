# -*- coding: utf-8 -*-
"""حلقه‌ی فرمان (command loop) — استفاده‌ی مجدد از طراحی قدیمی ریپو.

ارسال فرمان:
    دکمه‌ی «توقف کار» / «شروع مجدد» یک فایل inbox/cmd-<epoch>.json با اسکیمای
    {"id","action":"pause|resume","agent":"<id>","ts","by":"taha"}
    از طریق GitHub Contents API می‌سازد. توکن را کاربر یک‌بار در دیالوگ
    تنظیمات وارد می‌کند و در %APPDATA%/TAgents/config.json ذخیره می‌شود
    (هرگز داخل ریپو).

دریافت گزارش:
    واچر سمت BabyT پوشه‌ی inbox را می‌خواند، کرون‌های آن ایجنت را
    pause/resume می‌کند و گزارش را در outbox/rep-<epoch>.json می‌گذارد:
    {"id","cmd_id","ok","summary","details":[],"ts"}
    این ماژول outbox را پول می‌کند و گزارش‌های تازه را سیگنال می‌دهد.
"""

import base64
import datetime
import json
import os
import time

import requests
from PyQt6 import QtCore, QtWidgets

from app.feed import run_in_thread

REPO = "thaarfknight-star/TAgents"
API = "https://api.github.com"
OUTBOX_POLL_MS = 20_000


def get_config_dir():
    """مسیر پوشه‌ی تنظیمات محلی (توکن اینجاست، نه داخل ریپو)."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = os.path.join(appdata, "TAgents")
    else:
        base = os.path.join(os.path.expanduser("~"), ".config", "TAgents")
    os.makedirs(base, exist_ok=True)
    return base


def _config_path():
    return os.path.join(get_config_dir(), "config.json")


def get_token():
    try:
        with open(_config_path(), "r", encoding="utf-8") as fh:
            return (json.load(fh).get("github_token") or "").strip()
    except (OSError, ValueError):
        return ""


def save_token(token):
    with open(_config_path(), "w", encoding="utf-8") as fh:
        json.dump({"github_token": token.strip()}, fh, ensure_ascii=False, indent=2)


class SettingsDialog(QtWidgets.QDialog):
    """دیالوگ یک‌باره‌ی وارد کردن توکن GitHub."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تنظیمات — توکن GitHub")
        self.setModal(True)
        self.resize(420, 200)
        layout = QtWidgets.QVBoxLayout(self)

        info = QtWidgets.QLabel(
            "برای ارسال فرمان «توقف/شروع» به ایجنت‌ها، یک توکن GitHub با دسترسی "
            "repo لازم است.\nتوکن فقط روی همین سیستم در پوشه‌ی تنظیمات محلی "
            "ذخیره می‌شود و هرگز داخل ریپو قرار نمی‌گیرد."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.tokenEdit = QtWidgets.QLineEdit()
        self.tokenEdit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.tokenEdit.setPlaceholderText("توکن GitHub…")
        self.tokenEdit.setText(get_token())
        layout.addWidget(self.tokenEdit)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        ok_btn = QtWidgets.QPushButton("💾 ذخیره")
        cancel_btn = QtWidgets.QPushButton("انصراف")
        row.addWidget(ok_btn)
        row.addWidget(cancel_btn)
        layout.addLayout(row)

        ok_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)

    def _save(self):
        token = self.tokenEdit.text().strip()
        if not token:
            QtWidgets.QMessageBox.warning(self, "خطا", "توکن خالی است.")
            return
        save_token(token)
        self.accept()


class CommandClient(QtCore.QObject):
    """ارسال فرمان به inbox و پول گزارش‌ها از outbox."""

    command_sent = QtCore.pyqtSignal(dict)      # cmd dict
    command_failed = QtCore.pyqtSignal(str)
    report_received = QtCore.pyqtSignal(dict)   # report dict
    outbox_error = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._threads = []
        self._seen = self._load_seen()
        self._outbox_timer = QtCore.QTimer(self)
        self._outbox_timer.timeout.connect(self.poll_outbox)
        self._outbox_timer.start(OUTBOX_POLL_MS)

    # ---------- دیده‌شده‌ها ----------
    def _seen_path(self):
        return os.path.join(get_config_dir(), "seen_reports.json")

    def _load_seen(self):
        try:
            with open(self._seen_path(), "r", encoding="utf-8") as fh:
                return set(json.load(fh))
        except (OSError, ValueError):
            return set()

    def _save_seen(self):
        try:
            with open(self._seen_path(), "w", encoding="utf-8") as fh:
                json.dump(sorted(self._seen), fh, ensure_ascii=False)
        except OSError:
            pass

    # ---------- ارسال فرمان ----------
    def _headers(self, token):
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def send(self, agent_id, action):
        """action یکی از pause | resume است."""
        token = get_token()
        if not token:
            self.command_failed.emit("توکن GitHub تنظیم نشده است.")
            return
        epoch = int(time.time())
        cmd = {
            "id": f"cmd-{epoch}",
            "action": action,
            "agent": agent_id,
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "by": "taha",
        }

        def _put():
            content = base64.b64encode(
                json.dumps(cmd, ensure_ascii=False).encode("utf-8")
            ).decode()
            resp = requests.put(
                f"{API}/repos/{REPO}/contents/inbox/{cmd['id']}.json",
                headers=self._headers(token),
                json={
                    "message": f"cmd: {action} {agent_id} by taha",
                    "content": content,
                },
                timeout=15,
            )
            resp.raise_for_status()
            return cmd

        run_in_thread(self, _put, self.command_sent.emit, self.command_failed.emit)

    # ---------- پول outbox ----------
    def poll_outbox(self):
        token = get_token()
        if not token:
            return

        def _list():
            resp = requests.get(
                f"{API}/repos/{REPO}/contents/outbox",
                headers=self._headers(token),
                timeout=15,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json()
            return items if isinstance(items, list) else []

        def _on_list(items):
            for item in items:
                name = item.get("name", "")
                if (
                    name.startswith("rep-")
                    and name.endswith(".json")
                    and name not in self._seen
                ):
                    self._fetch_report(item.get("path", f"outbox/{name}"), name)

        run_in_thread(self, _list, _on_list, self.outbox_error.emit)

    def _fetch_report(self, path, name):
        token = get_token()

        def _get():
            resp = requests.get(
                f"{API}/repos/{REPO}/contents/{path}",
                headers=self._headers(token),
                timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json()
            return json.loads(base64.b64decode(payload["content"]).decode("utf-8"))

        def _on(report):
            self._seen.add(name)
            self._save_seen()
            self.report_received.emit(report if isinstance(report, dict) else {})

        run_in_thread(self, _get, _on, self.outbox_error.emit)
