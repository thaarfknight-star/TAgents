# -*- coding: utf-8 -*-
"""نگهبان توکن (Token Sentinel) — نسخه‌ی ویندوز.

مشخصات (مشترک با اندروید — رفتار هر دو پلتفرم یکسان است):

۱. صندوق توکن: افزودن/حذف چند توکن گیت‌هاب. ذخیره‌سازی امن فقط با keyring
   (Windows Credential Manager). توکن خام هرگز در لاگ، فایل، ریپو یا چت
   نوشته نمی‌شود.

۲. بازرس توکن (برای هر توکن):
   - اعتبارسنجی با GET /user → نمایش مالک: login، name، آواتار، نوع اکانت.
   - تشخیص نوع توکن: پیشوند ghp_ یعنی classic، و github_pat_ یعنی fine-grained؛
     تأیید با هدرهای پاسخ: X-OAuth-Scopes (classic) یا
     X-Accepted-GitHub-Permissions (fine-grained).
   - سیگنال مصرف: GET /rate_limit → نمایش limit/remaining/reset؛ اگر remaining
     به‌طور غیرعادی کم بود، «هشدار مصرف مشکوک».
   - فعالیت اخیر: GET /users/{login}/events/public (۱۰ مورد آخر) → فقط
     «سرنخ فعالیت اکانت» (فعالیت عمومی اکانت است، نه لزوماً با این توکن).
   - برچسب دستی: فیلد «این توکن دست کیه؟» — چون تشخیص خودکار اینکه چه
     شخص/AI از توکن مشترک استفاده می‌کند از سمت گیت‌هاب ممکن نیست.

۳. دکمه‌ی «قطع دسترسی»: POST /credentials/revoke با بدنه‌ی
   {"credentials": ["<token>"]} — بدون احراز هویت؛ PATهای classic و
   fine-grained را revoke می‌کند. دیالوگ تأیید دو مرحله‌ای فارسی + هشدار:
   «قطع یعنی revoke کامل توکن برای همه‌ی مصرف‌کننده‌ها؛ نمی‌شود فقط یک نفر
   را جدا کرد». اگر توکن همان توکن فید/پوش برنامه باشد، هشدار اضافه.

۴. رابط کاربری: فارسی RTL، تم تیره‌ی نئونی هماهنگ با برنامه.
"""

import datetime
import json
import os
import time
import uuid

import requests
from PyQt6 import QtCore, QtGui, QtWidgets

from app.commands import get_config_dir, get_token as get_app_token
from app.feed import fa_digits, format_relative_fa, parse_iso, run_in_thread

try:
    import keyring
    _KEYRING_OK = True
except Exception:
    keyring = None
    _KEYRING_OK = False

SERVICE_NAME = "TAgents-TokenSentinel"
API = "https://api.github.com"
REVOKE_URL = "https://api.github.com/credentials/revoke"


# ---------- صندوق امن ----------

def _vault_path():
    return os.path.join(get_config_dir(), "token_vault.json")


def _load_vault():
    try:
        with open(_vault_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save_vault(items):
    with open(_vault_path(), "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)


def keyring_available():
    return _KEYRING_OK


def list_tokens():
    """فهرست متادیتای توکن‌ها (بدون مقدار خام)."""
    return _load_vault()


def _mask_token(token):
    t = (token or "").strip()
    if len(t) <= 8:
        return "****"
    return f"{t[:4]}****{t[-4:]}"


def add_token(label, token_value):
    """افزودن توکن جدید. مقدار خام فقط در keyring ذخیره می‌شود."""
    if not _KEYRING_OK:
        raise RuntimeError("keyring در دسترس نیست؛ ذخیره‌ی امن ممکن نیست.")
    token_value = (token_value or "").strip()
    if not token_value:
        raise ValueError("توکن خالی است.")
    tid = "tkn-" + uuid.uuid4().hex[:12]
    keyring.set_password(SERVICE_NAME, tid, token_value)
    items = _load_vault()
    items.append({
        "id": tid,
        "label": (label or "").strip() or "بدون نام",
        "hint": _mask_token(token_value),
        "owner_label": "",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    _save_vault(items)
    return tid


def remove_token(tid):
    if _KEYRING_OK:
        try:
            keyring.delete_password(SERVICE_NAME, tid)
        except Exception:
            pass
    items = [it for it in _load_vault() if it.get("id") != tid]
    _save_vault(items)


def get_token_secret(tid):
    """بازیابی مقدار خام توکن — فقط برای فراخوانی API، هرگز لاگ نکنید."""
    if not _KEYRING_OK:
        raise RuntimeError("keyring در دسترس نیست.")
    return keyring.get_password(SERVICE_NAME, tid)


def set_owner_label(tid, owner_label):
    items = _load_vault()
    for it in items:
        if it.get("id") == tid:
            it["owner_label"] = (owner_label or "").strip()
    _save_vault(items)


def detect_kind(token_value):
    t = (token_value or "").strip()
    if t.startswith("github_pat_"):
        return "fine-grained"
    if t.startswith("ghp_"):
        return "classic"
    return "unknown"


# ---------- بازرس ----------

class TokenInspector(QtCore.QObject):
    inspected = QtCore.pyqtSignal(dict)   # نتیجه‌ی کامل
    failed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._threads = []

    def inspect(self, tid):
        def _do():
            secret = get_token_secret(tid)
            if not secret:
                raise ValueError("توکن در صندوق امن پیدا نشد.")
            headers = {
                "Authorization": f"Bearer {secret}",
                "Accept": "application/vnd.github+json",
            }
            # ۱) اعتبارسنجی /user
            r = requests.get(f"{API}/user", headers=headers, timeout=15)
            r.raise_for_status()
            user = r.json()
            login = user.get("login", "")
            scopes = r.headers.get("X-OAuth-Scopes", "")
            accepted = r.headers.get("X-Accepted-GitHub-Permissions", "")
            kind_prefix = detect_kind(secret)
            if scopes:
                kind = "classic"
            elif accepted:
                kind = "fine-grained"
            else:
                kind = kind_prefix

            # ۲) rate_limit
            rl = requests.get(f"{API}/rate_limit", headers=headers, timeout=15)
            rl.raise_for_status()
            core = (rl.json().get("resources", {}).get("core", {}))
            limit = core.get("limit")
            remaining = core.get("remaining")
            reset_ts = core.get("reset")
            suspicious = False
            try:
                if limit and remaining is not None and limit > 0:
                    # اگر کمتر از ۱۰٪ سهمیه مانده، مشکوک
                    suspicious = (remaining / limit) < 0.10
            except Exception:
                suspicious = False

            # ۳) فعالیت عمومی اخیر (فقط سرنخ)
            events = []
            try:
                er = requests.get(
                    f"{API}/users/{login}/events/public",
                    headers={"Accept": "application/vnd.github+json"},
                    params={"per_page": 10},
                    timeout=15,
                )
                if er.status_code == 200:
                    for ev in er.json()[:10]:
                        events.append({
                            "type": ev.get("type", ""),
                            "repo": (ev.get("repo") or {}).get("name", ""),
                            "created_at": ev.get("created_at", ""),
                        })
            except Exception:
                events = []

            return {
                "id": tid,
                "valid": True,
                "login": login,
                "name": user.get("name") or "",
                "avatar_url": user.get("avatar_url") or "",
                "account_type": user.get("type") or "",
                "token_kind": kind,
                "scopes": scopes,
                "accepted_permissions": accepted,
                "rate_limit": limit,
                "rate_remaining": remaining,
                "rate_reset": reset_ts,
                "suspicious": suspicious,
                "events": events,
            }

        run_in_thread(self, _do, self.inspected.emit, self.failed.emit)


def revoke_token_secret(secret):
    """revoke کردن توکن از طریق Credential Revocation API.

    حتماً بدون هدر Authorization (درخواست احرازهویتی 403 می‌گیرد).
    پاسخ موفق طبق داک رسمی 202 است.
    """
    resp = requests.post(
        REVOKE_URL,
        json={"credentials": [secret]},
        headers={"Accept": "application/vnd.github+json"},
        timeout=15,
    )
    if resp.status_code in (200, 202, 204):
        return True
    resp.raise_for_status()
    return True


# ---------- رابط کاربری ----------

class TokenSentinelDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🛡 نگهبان توکن")
        self.resize(640, 560)
        self._current = None
        self._inspect_data = {}
        self.inspector = TokenInspector(self)
        self.inspector.inspected.connect(self._on_inspected)
        self.inspector.failed.connect(self._on_inspect_failed)

        root = QtWidgets.QVBoxLayout(self)

        note = QtWidgets.QLabel(
            "گیت‌هاب راهی برای تشخیص اینکه «چه کسی» از یک توکن مشترک استفاده "
            "می‌کند ندارد — توکن bearer است و همه‌ی مصرف‌کننده‌ها یکسان دیده "
            "می‌شوند. قطع دسترسی هم فقط برای همه‌ی مصرف‌کننده‌ها ممکن است، "
            "نه تکی. برای هر توکن خودتان بنویسید دست کیست."
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        root.addWidget(note)

        if not keyring_available():
            warn = QtWidgets.QLabel(
                "⚠ keyring در دسترس نیست؛ ذخیره‌ی امن توکن ممکن نیست. "
                "پکیج keyring را نصب کنید."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #ff4d5e; font-weight: bold;")
            root.addWidget(warn)

        # فهرست توکن‌ها
        root.addWidget(QtWidgets.QLabel("توکن‌های ذخیره‌شده:"))
        self.tokenList = QtWidgets.QListWidget()
        self.tokenList.itemSelectionChanged.connect(self._on_select)
        root.addWidget(self.tokenList)

        btnRow = QtWidgets.QHBoxLayout()
        self.addBtn = QtWidgets.QPushButton("➕ افزودن توکن")
        self.delBtn = QtWidgets.QPushButton("🗑 حذف")
        self.importBtn = QtWidgets.QPushButton("📥 توکن برنامه → صندوق")
        self.importBtn.setToolTip("کپی توکن فعلی برنامه (فید/فرمان) به صندوق نگهبان برای بازرسی — توکن برنامه سر جایش می‌ماند.")
        btnRow.addWidget(self.addBtn)
        btnRow.addWidget(self.delBtn)
        btnRow.addWidget(self.importBtn)
        btnRow.addStretch(1)
        root.addLayout(btnRow)
        self.addBtn.clicked.connect(self._on_add)
        self.delBtn.clicked.connect(self._on_delete)
        self.importBtn.clicked.connect(self._on_import_app_token)

        # جزئیات
        self.detailBox = QtWidgets.QGroupBox("بازرسی توکن")
        dl = QtWidgets.QVBoxLayout(self.detailBox)

        self.ownerLabel = QtWidgets.QLabel("توکنی انتخاب نشده است.")
        self.ownerLabel.setWordWrap(True)
        dl.addWidget(self.ownerLabel)

        self.avatarLabel = QtWidgets.QLabel()
        self.avatarLabel.setFixedSize(48, 48)
        self.avatarLabel.setScaledContents(True)
        dl.addWidget(self.avatarLabel)

        self.kindLabel = QtWidgets.QLabel()
        self.kindLabel.setWordWrap(True)
        self.kindLabel.setObjectName("Muted")
        dl.addWidget(self.kindLabel)

        self.rateLabel = QtWidgets.QLabel()
        self.rateLabel.setWordWrap(True)
        dl.addWidget(self.rateLabel)

        self.suspLabel = QtWidgets.QLabel()
        self.suspLabel.setWordWrap(True)
        self.suspLabel.setStyleSheet("color: #ffb020; font-weight: bold;")
        dl.addWidget(self.suspLabel)

        dl.addWidget(QtWidgets.QLabel("فعالیت اخیر اکانت (فقط سرنخ — فعالیت عمومی اکانت است، نه لزوماً با این توکن):"))
        self.eventsList = QtWidgets.QListWidget()
        self.eventsList.setMaximumHeight(110)
        dl.addWidget(self.eventsList)

        # برچسب دستی
        dl.addWidget(QtWidgets.QLabel("این توکن دست کیه؟ (برچسب دستی شما)"))
        ownRow = QtWidgets.QHBoxLayout()
        self.ownerEdit = QtWidgets.QLineEdit()
        self.ownerEdit.setPlaceholderText("مثلاً: لپ‌تاپ طه، ChatGPT، سرور بیلد…")
        self.ownerSaveBtn = QtWidgets.QPushButton("💾 ذخیره برچسب")
        ownRow.addWidget(self.ownerEdit, 1)
        ownRow.addWidget(self.ownerSaveBtn)
        dl.addLayout(ownRow)
        self.ownerSaveBtn.clicked.connect(self._on_save_owner_label)

        # دکمه‌ی قطع
        self.revokeBtn = QtWidgets.QPushButton("⛔ قطع دسترسی این توکن")
        self.revokeBtn.setObjectName("Danger")
        dl.addWidget(self.revokeBtn)
        self.revokeBtn.clicked.connect(self._on_revoke)

        root.addWidget(self.detailBox, 1)

        closeBtn = QtWidgets.QPushButton("بستن")
        closeBtn.clicked.connect(self.accept)
        root.addWidget(closeBtn)

        self._reload_list()

    # ---------- فهرست ----------
    def _reload_list(self):
        self.tokenList.clear()
        for it in list_tokens():
            label = it.get("label", "بدون نام")
            hint = it.get("hint", "")
            owner = it.get("owner_label", "")
            text = f"{label}  ({hint})" + (f" — دست: {owner}" if owner else "")
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, it.get("id"))
            self.tokenList.addItem(item)

    def _selected_id(self):
        items = self.tokenList.selectedItems()
        if not items:
            return None
        return items[0].data(QtCore.Qt.ItemDataRole.UserRole)

    def _on_select(self):
        tid = self._selected_id()
        self._current = tid
        self._inspect_data = {}
        if not tid:
            return
        # برچسب دستی فعلی را نشان بده
        for it in list_tokens():
            if it.get("id") == tid:
                self.ownerEdit.setText(it.get("owner_label", ""))
        self.ownerLabel.setText("⏳ در حال بازرسی توکن…")
        self.kindLabel.setText("")
        self.rateLabel.setText("")
        self.suspLabel.setText("")
        self.eventsList.clear()
        self.avatarLabel.clear()
        self.inspector.inspect(tid)

    # ---------- افزودن / حذف ----------
    def _on_add(self):
        if not keyring_available():
            QtWidgets.QMessageBox.warning(
                self, "خطا", "keyring در دسترس نیست؛ ذخیره‌ی امن ممکن نیست."
            )
            return
        label, ok1 = QtWidgets.QInputDialog.getText(self, "افزودن توکن", "نام توکن (مثلاً: توکن اصلی):")
        if not ok1:
            return
        token, ok2 = QtWidgets.QInputDialog.getText(
            self, "افزودن توکن", "مقدار توکن GitHub:",
            echo=QtWidgets.QLineEdit.EchoMode.Password,
        )
        if not ok2 or not token.strip():
            return
        try:
            add_token(label, token)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "خطا", f"افزودن توکن ناموفق بود:\n{exc}")
            return
        # token متغیر محلی است؛ از حافظه پاکش می‌کنیم (هرگز لاگ نمی‌شود)
        token = None
        self._reload_list()

    def _on_import_app_token(self):
        """کپی توکن فعلی برنامه به صندوق (بدون تغییر ذخیره‌سازی برنامه)."""
        if not keyring_available():
            QtWidgets.QMessageBox.warning(
                self, "خطا", "keyring در دسترس نیست؛ ذخیره‌ی امن ممکن نیست."
            )
            return
        app_token = ""
        try:
            app_token = (get_app_token() or "").strip()
        except Exception:
            app_token = ""
        if not app_token:
            QtWidgets.QMessageBox.information(
                self, "توکن برنامه", "توکنی در تنظیمات برنامه ذخیره نشده است."
            )
            return
        # اگر قبلاً با همین hint وارد شده، تکراری اضافه نکن
        hint = _mask_token(app_token)
        for it in list_tokens():
            if it.get("hint") == hint and "برنامه" in it.get("label", ""):
                QtWidgets.QMessageBox.information(
                    self, "توکن برنامه", "این توکن قبلاً در صندوق هست."
                )
                return
        try:
            add_token("توکن برنامه (فید/فرمان)", app_token)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "خطا", f"وارد کردن ناموفق بود:\n{exc}")
            return
        finally:
            app_token = None
        self._reload_list()
        QtWidgets.QMessageBox.information(
            self, "انجام شد",
            "توکن برنامه در صندوق نگهبان کپی شد (توکن برنامه سر جایش ماند)."
        )

    def _on_delete(self):
        tid = self._selected_id()
        if not tid:
            return
        ans = QtWidgets.QMessageBox.question(
            self, "حذف توکن",
            "توکن از صندوق امن این سیستم حذف شود؟\n(این کار توکن را در گیت‌هاب revoke نمی‌کند.)",
        )
        if ans == QtWidgets.QMessageBox.StandardButton.Yes:
            remove_token(tid)
            self._current = None
            self._reload_list()
            self.ownerLabel.setText("توکنی انتخاب نشده است.")

    # ---------- نتیجه‌ی بازرسی ----------
    def _on_inspected(self, data):
        if data.get("id") != self._current:
            return
        self._inspect_data = data
        login = data.get("login", "")
        name = data.get("name", "")
        atype = data.get("account_type", "")
        self.ownerLabel.setText(f"👤 مالک: {login}" + (f" ({name})" if name else "") + (f" — نوع اکانت: {atype}" if atype else ""))

        kind = data.get("token_kind", "unknown")
        kind_fa = {"classic": "کلاسیک (ghp_)", "fine-grained": "دقیق (github_pat_)"}.get(kind, "نامشخص")
        scopes = data.get("scopes") or ""
        if scopes:
            extra = f" — اسکوپ‌ها: {scopes}"
        elif kind == "fine-grained":
            # صادقانه: هدر X-Accepted-GitHub-Permissions فقط نیازمندی آن
            # اندپوینت را نشان می‌دهد، نه دسترسی‌های واقعی توکن؛ پس نمایش نمی‌دهیم.
            extra = " — فهرست دقیق دسترسی‌ها از هدرها قابل استخراج نیست"
        else:
            extra = ""
        self.kindLabel.setText(f"نوع توکن: {kind_fa}{extra}")

        limit = data.get("rate_limit")
        remaining = data.get("rate_remaining")
        reset_ts = data.get("rate_reset")
        if limit is not None and remaining is not None:
            reset_s = ""
            try:
                dt = datetime.datetime.fromtimestamp(int(reset_ts), tz=datetime.timezone.utc)
                reset_s = f" — ریست: {format_relative_fa(dt)}"
            except Exception:
                pass
            self.rateLabel.setText(
                f"سهمیه‌ی API: {fa_digits(remaining)} از {fa_digits(limit)} مانده{reset_s}"
            )
        else:
            self.rateLabel.setText("سهمیه‌ی API: نامشخص")

        if data.get("suspicious"):
            self.suspLabel.setText(
                "⚠ هشدار مصرف مشکوک: سهمیه‌ی باقی‌مانده به‌طور غیرعادی کم است — "
                "احتمالاً کس دیگری هم دارد از این توکن استفاده می‌کند."
            )
        else:
            self.suspLabel.setText("")

        self.eventsList.clear()
        for ev in data.get("events", []):
            etype = ev.get("type", "")
            repo = ev.get("repo", "")
            when = ev.get("created_at", "")
            dt = parse_iso(when)
            rel = format_relative_fa(dt) if dt else when
            QtWidgets.QListWidgetItem(f"{etype} در {repo} — {rel}", self.eventsList)

        # آواتار
        avatar_url = data.get("avatar_url") or ""
        if avatar_url:
            def _fetch_avatar():
                r = requests.get(avatar_url, timeout=12)
                r.raise_for_status()
                return r.content
            def _set_avatar(content):
                if self._current != data.get("id"):
                    return
                img = QtGui.QImage.fromData(content)
                if not img.isNull():
                    self.avatarLabel.setPixmap(QtGui.QPixmap.fromImage(img))
            def _ignore(_msg):
                pass
            run_in_thread(self.inspector, _fetch_avatar, _set_avatar, _ignore)

    def _on_inspect_failed(self, msg):
        self.ownerLabel.setText(f"❌ بازرسی ناموفق بود: {msg}")

    def _on_save_owner_label(self):
        tid = self._selected_id()
        if not tid:
            return
        set_owner_label(tid, self.ownerEdit.text())
        self._reload_list()
        # انتخاب را نگه دار
        for i in range(self.tokenList.count()):
            if self.tokenList.item(i).data(QtCore.Qt.ItemDataRole.UserRole) == tid:
                self.tokenList.setCurrentRow(i)
                break

    # ---------- قطع دسترسی ----------
    def _on_revoke(self):
        tid = self._selected_id()
        if not tid:
            return
        # مرحله‌ی اول
        ans1 = QtWidgets.QMessageBox.warning(
            self, "قطع دسترسی — مرحله‌ی ۱ از ۲",
            "⚠ توجه: قطع یعنی revoke کامل توکن برای همه‌ی مصرف‌کننده‌ها.\n"
            "نمی‌شود فقط یک نفر را جدا کرد — همه از این توکن می‌افتند.\n\n"
            "ادامه می‌دهید؟",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if ans1 != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        # هشدار اگر توکن خود برنامه است
        try:
            secret = get_token_secret(tid)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "خطا", f"خواندن توکن ناموفق بود:\n{exc}")
            return
        app_token = ""
        try:
            app_token = (get_app_token() or "").strip()
        except Exception:
            app_token = ""
        extra_warn = ""
        if app_token and secret and secret.strip() == app_token:
            extra_warn = ("\n\n⛔ هشدار اضافه: این همان توکنی است که خود برنامه برای "
                         "فید/پوش استفاده می‌کند — بعد از قطع، فید می‌خوابد و باید "
                         "توکن جدید در تنظیمات بگذارید.")
        # مرحله‌ی دوم
        ans2 = QtWidgets.QMessageBox.warning(
            self, "قطع دسترسی — مرحله‌ی ۲ از ۲ (تأیید نهایی)",
            "این عمل برگشت‌ناپذیر است. توکن برای همیشه باطل می‌شود." + extra_warn +
            "\n\nواقعاً قطع شود؟",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if ans2 != QtWidgets.QMessageBox.StandardButton.Yes:
            secret = None
            return
        try:
            revoke_token_secret(secret)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "خطا", f"قطع دسترسی ناموفق بود:\n{exc}")
            return
        finally:
            secret = None
        # بعد از revoke موفق، توکن را از صندوق هم حذف کن
        remove_token(tid)
        self._current = None
        self._reload_list()
        self.ownerLabel.setText("✅ توکن با موفقیت قطع (revoke) و از صندوق حذف شد.")
        QtWidgets.QMessageBox.information(self, "انجام شد", "توکن قطع شد و از صندوق امن حذف شد.")
