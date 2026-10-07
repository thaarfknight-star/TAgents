# -*- coding: utf-8 -*-
"""پولر فید وضعیت شبکه.

هر ۱۵ ثانیه فایل status.json را از برنچ main ریپو می‌خواند:
    https://raw.githubusercontent.com/thaarfknight-star/TAgents/main/status.json

هیچ داده‌ی «لایو»ی ساخته نمی‌شود؛ اگر فید قدیمی باشد، قدمت آن
به کاربر نشان داده می‌شود (برچسب «آخرین به‌روزرسانی»).
"""

import datetime

import requests
from PyQt6 import QtCore

FEED_URL = "https://raw.githubusercontent.com/thaarfknight-star/TAgents/main/status.json"
POLL_INTERVAL_MS = 15_000
STALE_AFTER_SEC = 5 * 60  # بعد از ۵ دقیقه، فید «قدیمی» حساب می‌شود

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_digits(value):
    """تبدیل ارقام لاتین به فارسی."""
    return str(value).translate(_FA_DIGITS)


def parse_iso(value):
    """پارس زمان ISO؛ در صورت نامعتبر بودن None برمی‌گرداند."""
    if not value:
        return None
    try:
        v = str(value).replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        return None


def format_relative_fa(dt, now=None):
    """زمان نسبی فارسی: «۳ دقیقه پیش»."""
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    secs = int((now - dt).total_seconds())
    if secs < 0:
        secs = 0
    if secs < 60:
        return "چند لحظه پیش"
    if secs < 3600:
        return f"{fa_digits(secs // 60)} دقیقه پیش"
    if secs < 86400:
        return f"{fa_digits(secs // 3600)} ساعت پیش"
    return f"{fa_digits(secs // 86400)} روز پیش"


class _Worker(QtCore.QObject):
    done = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    @QtCore.pyqtSlot()
    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


def run_in_thread(owner, fn, on_done, on_failed):
    """اجرای fn در یک QThread جدا و تحویل نتیجه به کال‌بک‌ها."""
    thread = QtCore.QThread(owner)
    worker = _Worker(fn)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.done.connect(on_done)
    worker.failed.connect(on_failed)
    worker.done.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    owner._threads.append(thread)
    thread.finished.connect(
        lambda: owner._threads.remove(thread) if thread in owner._threads else None
    )
    thread.start()


class FeedPoller(QtCore.QObject):
    """هر POLL_INTERVAL_MS یک‌بار فید را می‌خواند و سیگنال می‌دهد."""

    updated = QtCore.pyqtSignal(dict)
    error = QtCore.pyqtSignal(str)

    def __init__(self, url=FEED_URL, interval_ms=POLL_INTERVAL_MS, parent=None):
        super().__init__(parent)
        self.url = url
        self._threads = []
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.poll_now)
        self._timer.start(interval_ms)

    def poll_now(self):
        def _fetch():
            resp = requests.get(self.url, timeout=12)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or "agents" not in data:
                raise ValueError("ساختار فید نامعتبر است")
            return data

        run_in_thread(self, _fetch, self.updated.emit, self.error.emit)
