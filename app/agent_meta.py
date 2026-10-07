# -*- coding: utf-8 -*-
"""راستر استاتیک دوازده نود شبکه: BabyT (هماهنگ‌کننده) + یازده ایجنت.

این فایل فقط هویت ثابث نودهاست (شناسه، نام، ایموجی، گروه، نقش فارسی).
وضعیت لحظه‌ای هر ایجنت از فید status.json می‌آید (app/feed.py).
"""

AGENTS = [
    {"id": "babyt",    "name": "BabyT",    "emoji": "🧠", "group": "main", "role_fa": "هماهنگ‌کننده‌ی شبکه"},
    {"id": "tagent",   "name": "TAgent",   "emoji": "🎮", "group": "main", "role_fa": "رفیق گیمر (Rainbow Six)"},
    {"id": "tagent1",  "name": "TAgent1",  "emoji": "🎮", "group": "main", "role_fa": "رفیق گیمر"},
    {"id": "tagent2",  "name": "TAgent2",  "emoji": "🎮", "group": "main", "role_fa": "رفیق گیمر"},
    {"id": "tagent3",  "name": "TAgent3",  "emoji": "🎮", "group": "main", "role_fa": "رفیق گیمر"},
    {"id": "tagent4",  "name": "TAgent4",  "emoji": "🎮", "group": "main", "role_fa": "رفیق گیمر"},
    {"id": "iasinsta", "name": "IASinsta", "emoji": "📹", "group": "work", "role_fa": "نگهبان پیج اینستاگرام IAS"},
    {"id": "bepagent", "name": "BEPagent", "emoji": "☀️", "group": "work", "role_fa": "نگهبان پیج @bepco.official"},
    {"id": "iasagent", "name": "IASagent", "emoji": "🖥️", "group": "work", "role_fa": "متخصص IAS Viewer (دسکتاپ)"},
    {"id": "ivaagent", "name": "IVAagent", "emoji": "🤖", "group": "work", "role_fa": "مسئول نسخه‌ی اندروید IAS-Viewer"},
    {"id": "licagent", "name": "LICagent", "emoji": "🔑", "group": "work", "role_fa": "متخصص لایسنس و License Manager"},
    {"id": "lawagent", "name": "LAWagent", "emoji": "⚖️", "group": "work", "role_fa": "متخصص حقوقی و قراردادها"},
]

AGENT_BY_ID = {a["id"]: a for a in AGENTS}

GROUP_FA = {
    "main": "ایجنت‌های main",
    "work": "ایجنت‌های work",
}

STATUS_FA = {
    "working": "مشغول به کار",
    "idle": "بیکار",
    "paused": "متوقف‌شده",
    "error": "خطا",
}
