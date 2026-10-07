# -*- coding: utf-8 -*-
"""مانیتور شبکه‌ی ایجنت‌های TAgents — برنامه‌ی اصلی (PyQt6).

این برنامه فقط شبکه‌ی main را پوشش می‌دهد: BabyT (هماهنگ‌کننده) + پنج ایجنت
(TAgent و TAgent1 تا TAgent4). شبکه‌ی work جداست و دست‌نخورده می‌ماند.

چیدمان (راست‌چین):
    سمت راست: بوم گراف تک‌شبکه‌ای (نودها دایره با ایموجی+نام، BabyT در مرکز،
              پنج ایجنت main دورش)
    سمت چپ:   پنل جزئیات ایجنت انتخاب‌شده
    پایین:    لاگ فعالیت

رنگ وضعیت نودها:
    سبز چشمک‌زن = مشغول به کار | خاکستری = بیکار
    کهربایی = متوقف‌شده | قرمز = خطا
"""

import datetime
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtGui, QtWidgets

from app import __version__
from app.agent_meta import AGENTS, AGENT_BY_ID, GROUP_FA, STATUS_FA
from app.commands import CommandClient, SettingsDialog, get_token
from app.feed import (
    STALE_AFTER_SEC,
    FeedPoller,
    fa_digits,
    format_relative_fa,
    parse_iso,
)

APP_TITLE = "مانیتور شبکه‌ی ایجنت‌ها"

STATUS_COLOR = {
    "working": "#22e584",  # سبز
    "idle": "#8b93a3",     # خاکستری
    "paused": "#ffb020",   # کهربایی
    "error": "#ff4d5e",    # قرمز
}

QSS = """
QWidget { background-color: #0b0f17; color: #e8edf5; font-family: "Segoe UI", "Vazirmatn", sans-serif; font-size: 13px; }
QGroupBox { border: 1px solid #1e2a3d; border-radius: 10px; margin-top: 14px; background: #101724; }
QGroupBox::title { subcontrol-origin: margin; right: 12px; padding: 0 8px; color: #00e5ff; }
QLabel#Title { font-size: 20px; font-weight: bold; color: #00e5ff; }
QLabel#Muted { color: #9aa4b5; }
QLabel#TaskText { background: #0b0f17; border: 1px solid #1e2a3d; border-radius: 8px; padding: 10px; }
QPushButton { background: #16202f; border: 1px solid #00e5ff; border-radius: 8px; padding: 8px 14px; color: #e8edf5; }
QPushButton:hover { background: #1b2940; }
QPushButton:disabled { border-color: #3a4356; color: #5b6577; background: #121826; }
QPushButton#Danger { border-color: #ffb020; }
QPushButton#Go { border-color: #22e584; }
QTextEdit#Log { background: #080b11; border: 1px solid #1e2a3d; border-radius: 8px; font-family: "Consolas", monospace; font-size: 12px; }
QLineEdit { background: #0b0f17; border: 1px solid #1e2a3d; border-radius: 8px; padding: 8px; }
QListWidget { background: #0b0f17; border: 1px solid #1e2a3d; border-radius: 8px; }
"""


class NetworkCanvas(QtWidgets.QWidget):
    """بوم گراف شبکه با رسم دستی: نودها، یال‌ها، رنگ وضعیت."""

    nodeClicked = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.statuses = {}
        self.selected_id = "babyt"
        self._nodes = []
        self._blink = 0
        self._blink_timer = QtCore.QTimer(self)
        self._blink_timer.timeout.connect(self._on_blink)
        self._blink_timer.start(550)
        self.setMouseTracking(True)
        self.setMinimumSize(440, 440)

    # ---------- داده ----------
    def set_statuses(self, statuses):
        self.statuses = statuses
        self.update()

    def set_selected(self, agent_id):
        self.selected_id = agent_id
        self.update()

    def _on_blink(self):
        self._blink = (self._blink + 1) % 4
        if any(
            self.statuses.get(a["id"], {}).get("status") == "working" for a in AGENTS
        ):
            self.update()

    def _node_status(self, agent_id):
        return self.statuses.get(agent_id, {}).get("status", "idle")

    # ---------- چیدمان ----------
    def _layout(self):
        w, h = max(1, self.width()), max(1, self.height())
        cx, cy = w / 2, h / 2 - 8
        scale = min(1.0, min(w, h) / 560.0)
        r1 = min(w, h) * 0.30
        nodes = [("babyt", cx, cy, 46 * scale)]
        main_agents = [a for a in AGENTS if a["id"] != "babyt"]
        for i, a in enumerate(main_agents):
            ang = math.radians(-90 + i * (360.0 / len(main_agents)))
            nodes.append(
                (a["id"], cx + r1 * math.cos(ang), cy + r1 * math.sin(ang), 36 * scale)
            )
        self._nodes = nodes
        return nodes

    # ---------- رسم ----------
    def paintEvent(self, event):  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor("#0b0f17"))
        nodes = self._layout()
        by_id = {nid: (x, y, r) for nid, x, y, r in nodes}
        cx, cy, _ = by_id["babyt"]

        # یال‌ها: BabyT به همه
        edge_pen = QtGui.QPen(QtGui.QColor(0, 229, 255, 45), 1.5)
        painter.setPen(edge_pen)
        for nid, x, y, r in nodes:
            if nid == "babyt":
                continue
            painter.drawLine(QtCore.QPointF(cx, cy), QtCore.QPointF(x, y))

        # نودها
        for nid, x, y, r in nodes:
            meta = AGENT_BY_ID[nid]
            status = self._node_status(nid)
            color = QtGui.QColor(STATUS_COLOR.get(status, "#8b93a3"))

            if status == "working":
                # هاله‌ی چشمک‌زن
                alpha = 40 + int(45 * abs(math.sin(self._blink * math.pi / 2)))
                for k, rr in enumerate((r + 14, r + 8)):
                    glow = QtGui.QColor(color)
                    glow.setAlpha_(max(0, alpha - k * 18))
                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
                    painter.setBrush(glow)
                    painter.drawEllipse(QtCore.QPointF(x, y), rr, rr)

            # دایره‌ی نود
            painter.setBrush(QtGui.QColor("#141b29"))
            painter.setPen(QtGui.QPen(color, 3))
            painter.drawEllipse(QtCore.QPointF(x, y), r, r)

            # حلقه‌ی انتخاب
            if nid == self.selected_id:
                painter.setPen(
                    QtGui.QPen(QtGui.QColor("#ffffff"), 2, QtCore.Qt.PenStyle.DashLine)
                )
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QtCore.QPointF(x, y), r + 5, r + 5)

            # ایموجی
            font = QtGui.QFont()
            font.setPixelSize(int(r * 0.95))
            painter.setFont(font)
            painter.setPen(QtGui.QColor("#ffffff"))
            painter.drawText(
                QtCore.QRectF(x - r, y - r, r * 2, r * 2),
                QtCore.Qt.AlignmentFlag.AlignCenter,
                meta["emoji"],
            )

            # نام زیر نود
            name_font = QtGui.QFont()
            name_font.setPixelSize(12)
            if nid == "babyt":
                name_font.setBold(True)
            painter.setFont(name_font)
            painter.setPen(
                QtGui.QColor("#00e5ff") if nid == "babyt" else QtGui.QColor("#e8edf5")
            )
            painter.drawText(
                QtCore.QRectF(x - 60, y + r + 2, 120, 20),
                QtCore.Qt.AlignmentFlag.AlignHCenter
                | QtCore.Qt.AlignmentFlag.AlignTop,
                meta["name"],
            )

        self._draw_legend(painter)

    def _draw_legend(self, painter):
        items = [
            ("working", "مشغول"),
            ("idle", "بیکار"),
            ("paused", "متوقف"),
            ("error", "خطا"),
        ]
        font = QtGui.QFont()
        font.setPixelSize(12)
        painter.setFont(font)
        fm = QtGui.QFontMetrics(font)
        x = 14.0
        y = self.height() - 14.0
        for status, label in items:
            color = QtGui.QColor(STATUS_COLOR[status])
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QtCore.QPointF(x + 6, y - 4), 6, 6)
            painter.setPen(QtGui.QColor("#9aa4b5"))
            w = fm.horizontalAdvance(label)
            painter.drawText(QtCore.QPointF(x + 18, y), label)
            x += 18 + w + 18

    # ---------- تعامل ----------
    def _hit_test(self, pos):
        for nid, x, y, r in reversed(self._nodes):
            if math.hypot(pos.x() - x, pos.y() - y) <= r + 6:
                return nid
        return None

    def mousePressEvent(self, event):  # noqa: N802
        nid = self._hit_test(event.position())
        if nid:
            self.set_selected(nid)
            self.nodeClicked.emit(nid)

    def mouseMoveEvent(self, event):  # noqa: N802
        nid = self._hit_test(event.position())
        self.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
            if nid
            else QtCore.Qt.CursorShape.ArrowCursor
        )


class DetailPanel(QtWidgets.QGroupBox):
    """پنل جزئیات ایجنت انتخاب‌شده (سمت چپ)."""

    pauseRequested = QtCore.pyqtSignal()
    resumeRequested = QtCore.pyqtSignal()
    refreshRequested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("جزئیات ایجنت", parent)
        self._agent_id = "babyt"
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        self.nameLabel = QtWidgets.QLabel()
        self.nameLabel.setStyleSheet("font-size: 19px; font-weight: bold;")
        self.nameLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.nameLabel)

        self.roleLabel = QtWidgets.QLabel()
        self.roleLabel.setObjectName("Muted")
        self.roleLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.roleLabel.setWordWrap(True)
        layout.addWidget(self.roleLabel)

        self.badge = QtWidgets.QLabel()
        self.badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.badge.setStyleSheet(
            "font-weight: bold; border-radius: 12px; padding: 6px;"
        )
        layout.addWidget(self.badge)

        layout.addWidget(QtWidgets.QLabel("مشغول به:"))
        self.taskLabel = QtWidgets.QLabel("—")
        self.taskLabel.setObjectName("TaskText")
        self.taskLabel.setWordWrap(True)
        self.taskLabel.setMinimumHeight(64)
        self.taskLabel.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignRight
        )
        layout.addWidget(self.taskLabel)

        self.lastLabel = QtWidgets.QLabel("آخرین فعالیت: —")
        self.lastLabel.setObjectName("Muted")
        self.lastLabel.setWordWrap(True)
        layout.addWidget(self.lastLabel)

        self.todayLabel = QtWidgets.QLabel()
        self.todayLabel.setObjectName("Muted")
        layout.addWidget(self.todayLabel)

        layout.addStretch(1)

        self.pauseBtn = QtWidgets.QPushButton("⏸ توقف کار")
        self.pauseBtn.setObjectName("Danger")
        self.resumeBtn = QtWidgets.QPushButton("▶ شروع مجدد")
        self.resumeBtn.setObjectName("Go")
        self.refreshBtn = QtWidgets.QPushButton("🔄 به‌روزرسانی")
        layout.addWidget(self.pauseBtn)
        layout.addWidget(self.resumeBtn)
        layout.addWidget(self.refreshBtn)

        self.pauseBtn.clicked.connect(self.pauseRequested.emit)
        self.resumeBtn.clicked.connect(self.resumeRequested.emit)
        self.refreshBtn.clicked.connect(self.refreshRequested.emit)

        self.refresh("babyt", {})

    def refresh(self, agent_id, status):
        self._agent_id = agent_id
        meta = AGENT_BY_ID[agent_id]
        status = status or {}
        st = status.get("status", "idle")
        color = STATUS_COLOR.get(st, "#8b93a3")

        self.nameLabel.setText(f"{meta['emoji']} {meta['name']}")
        self.roleLabel.setText(f"{meta['role_fa']} — {GROUP_FA[meta['group']]}")
        self.badge.setText(STATUS_FA.get(st, st))
        self.badge.setStyleSheet(
            "font-weight: bold; border-radius: 12px; padding: 6px; "
            f"background: {color}26; color: {color}; border: 1px solid {color};"
        )

        task = (status.get("current_task") or "").strip() or "—"
        self.taskLabel.setText(task)

        last = parse_iso(status.get("last_activity"))
        self.lastLabel.setText(
            "آخرین فعالیت: " + (format_relative_fa(last) if last else "—")
        )
        done = status.get("today_done", 0)
        try:
            done = int(done)
        except (TypeError, ValueError):
            done = 0
        self.todayLabel.setText(f"امروز: {fa_digits(done)} کار انجام شده")

        self.pauseBtn.setEnabled(st != "paused")
        self.resumeBtn.setEnabled(st == "paused")


class ReportDialog(QtWidgets.QDialog):
    """نمایش گزارش برگشتی از outbox."""

    def __init__(self, report, parent=None):
        super().__init__(parent)
        self.setWindowTitle("گزارش اجرای فرمان")
        self.resize(440, 320)
        layout = QtWidgets.QVBoxLayout(self)

        ok = report.get("ok")
        head = QtWidgets.QLabel("✅ موفق" if ok else "❌ ناموفق")
        head.setStyleSheet(
            f"font-size: 17px; font-weight: bold; color: {'#22e584' if ok else '#ff4d5e'};"
        )
        head.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(head)

        summary = QtWidgets.QLabel(report.get("summary", "—"))
        summary.setWordWrap(True)
        summary.setObjectName("TaskText")
        layout.addWidget(summary)

        details = report.get("details") or []
        if details:
            layout.addWidget(QtWidgets.QLabel("جزئیات:"))
            lst = QtWidgets.QListWidget()
            for d in details:
                QtWidgets.QListWidgetItem(str(d), lst)
            layout.addWidget(lst)

        meta = QtWidgets.QLabel(
            f"فرمان: {report.get('cmd_id', '—')} — ایجنت: {report.get('agent', report.get('cmd_id', '—'))}"
        )
        meta.setObjectName("Muted")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        btn = QtWidgets.QPushButton("باشه")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} v{__version__}")
        self.resize(1180, 780)
        self.statuses = {}
        self._prev = {}
        self._first_feed = False

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setSpacing(8)

        # سربرگ
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(f"🛰 {APP_TITLE}")
        title.setObjectName("Title")
        header.addWidget(title)
        header.addStretch(1)
        self.feedLabel = QtWidgets.QLabel("در حال اتصال به فید…")
        self.feedLabel.setObjectName("Muted")
        header.addWidget(self.feedLabel)
        settings_btn = QtWidgets.QPushButton("⚙ تنظیمات توکن")
        settings_btn.clicked.connect(self._open_settings)
        header.addWidget(settings_btn)
        root.addLayout(header)

        # محتوا: اول بوم (در RTL می‌رود سمت راست)، بعد پنل جزئیات
        content = QtWidgets.QHBoxLayout()
        self.canvas = NetworkCanvas()
        content.addWidget(self.canvas, 3)
        self.detail = DetailPanel()
        self.detail.setFixedWidth(300)
        content.addWidget(self.detail, 0)
        root.addLayout(content, 1)

        # لاگ فعالیت
        root.addWidget(QtWidgets.QLabel("📋 لاگ فعالیت"))
        self.logView = QtWidgets.QTextEdit()
        self.logView.setObjectName("Log")
        self.logView.setReadOnly(True)
        self.logView.setMaximumHeight(150)
        root.addWidget(self.logView)

        # سیم‌کشی
        self.canvas.nodeClicked.connect(self._on_node_clicked)
        self.detail.pauseRequested.connect(lambda: self._send_command("pause"))
        self.detail.resumeRequested.connect(lambda: self._send_command("resume"))
        self.detail.refreshRequested.connect(self._manual_refresh)

        self.feed = FeedPoller(parent=self)
        self.feed.updated.connect(self._on_feed_updated)
        self.feed.error.connect(self._on_feed_error)

        self.cmd = CommandClient(self)
        self.cmd.command_sent.connect(self._on_command_sent)
        self.cmd.command_failed.connect(self._on_command_failed)
        self.cmd.report_received.connect(self._on_report)

        self.log("برنامه شروع شد. در حال دریافت فید وضعیت…")
        self.feed.poll_now()
        self.cmd.poll_outbox()

    # ---------- لاگ ----------
    def log(self, text):
        ts = fa_digits(datetime.datetime.now().strftime("%H:%M:%S"))
        self.logView.append(
            f'<span style="color:#5b6577">[{ts}]</span> {text}'
        )
        # سقف ۵۰۰ خط: خط‌های قدیمی‌تر را از ابتدا حذف کن
        doc = self.logView.document()
        excess = doc.blockCount() - 500
        if excess > 0:
            cursor = QtGui.QTextCursor(doc)
            cursor.movePosition(QtGui.QTextCursor.MoveMode.Start)
            cursor.movePosition(
                QtGui.QTextCursor.MoveMode.Down,
                QtGui.QTextCursor.MoveMode.KeepAnchor,
                excess,
            )
            cursor.removeSelectedText()

    # ---------- فید ----------
    def _on_feed_updated(self, data):
        agents = data.get("agents", [])
        new_statuses = {}
        for a in agents:
            if isinstance(a, dict) and a.get("id") in AGENT_BY_ID:
                new_statuses[a["id"]] = a
        self.statuses = new_statuses
        self.canvas.set_statuses(new_statuses)
        self.detail.refresh(self.detail._agent_id, new_statuses.get(self.detail._agent_id, {}))

        # برچسب قدمت فید
        dt = parse_iso(data.get("updated_at"))
        if dt:
            age = (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds()
            rel = format_relative_fa(dt)
            if age <= STALE_AFTER_SEC:
                self.feedLabel.setText(f"🟢 متصل — آخرین به‌روزرسانی: {rel}")
            else:
                self.feedLabel.setText(f"🟡 فید قدیمی است — آخرین به‌روزرسانی: {rel}")
        else:
            self.feedLabel.setText("🟡 فید بدون مهر زمانی")

        # لاگ تغییر وضعیت‌ها
        if not self._first_feed:
            self._first_feed = True
            self.log(f"اتصال به فید برقرار شد ({fa_digits(len(new_statuses))} ایجنت).")
        else:
            for aid, st in new_statuses.items():
                old = (self._prev.get(aid) or {}).get("status")
                new = st.get("status")
                if old and new and old != new:
                    name = AGENT_BY_ID[aid]["name"]
                    self.log(
                        f"{name}: {STATUS_FA.get(old, old)} ← {STATUS_FA.get(new, new)}"
                    )
        self._prev = new_statuses

    def _on_feed_error(self, msg):
        self.feedLabel.setText("🔴 خطا در دریافت فید")
        self.log(f"⚠ خطای فید: {msg}")

    # ---------- فرمان‌ها ----------
    def _ensure_token(self):
        if get_token():
            return True
        dlg = SettingsDialog(self)
        return dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and bool(get_token())

    def _send_command(self, action):
        aid = self.detail._agent_id
        if aid == "babyt" and action == "pause":
            QtWidgets.QMessageBox.information(
                self, "توجه", "BabyT هماهنگ‌کننده است؛ توقف آن از اینجا پشتیبانی نمی‌شود."
            )
            return
        if not self._ensure_token():
            return
        name = AGENT_BY_ID[aid]["name"]
        verb = "توقف کار" if action == "pause" else "شروع مجدد"
        self.log(f"⏳ ارسال فرمان «{verb}» برای {name}…")
        self.cmd.send(aid, action)

    def _on_command_sent(self, cmd):
        name = AGENT_BY_ID.get(cmd.get("agent", ""), {}).get("name", cmd.get("agent"))
        verb = "توقف کار" if cmd.get("action") == "pause" else "شروع مجدد"
        self.log(f"📤 فرمان «{verb}» برای {name} ثبت شد ({cmd.get('id')}). منتظر گزارش…")

    def _on_command_failed(self, msg):
        self.log(f"❌ خطا در ارسال فرمان: {msg}")
        QtWidgets.QMessageBox.warning(self, "خطا", f"ارسال فرمان ناموفق بود:\n{msg}")

    def _on_report(self, report):
        ok = report.get("ok")
        cmd_id = report.get("cmd_id", "—")
        self.log(
            f"{'✅' if ok else '❌'} گزارش رسید ({cmd_id}): {report.get('summary', '—')}"
        )
        ReportDialog(report, self).show()

    def _on_node_clicked(self, agent_id):
        self.detail.refresh(agent_id, self.statuses.get(agent_id, {}))

    def _manual_refresh(self):
        self.log("🔄 به‌روزرسانی دستی…")
        self.feed.poll_now()
        self.cmd.poll_outbox()

    def _open_settings(self):
        SettingsDialog(self).exec()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft)
    app.setApplicationName("TAgents Monitor")
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
