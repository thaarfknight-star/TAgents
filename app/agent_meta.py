# -*- coding: utf-8 -*-
"""راستر استاتیک شش نود شبکه‌ی main: BabyT (هماهنگ‌کننده) + پنج ایجنت.

این برنامه فقط شبکه‌ی main را پوشش می‌دهد؛ شبکه‌ی work جداست و
دست‌نخورده می‌ماند. این فایل فقط هویت ثابث نودهاست
(شناسه، نام، ایموجی، گروه، نقش فارسی).
وضعیت لحظه‌ای هر ایجنت از فید status.json می‌آید (app/feed.py).
"""

AGENTS = [
    {"id": "babyt",    "name": "BabyT",    "emoji": "🧠", "group": "main", "role_fa": "هماهنگ‌کننده‌ی شبکه"},
    {"id": "tagent",   "name": "TAgent",   "emoji": "🎮", "group": "main", "role_fa": "رفیق گیمر (Rainbow Six)"},
    {"id": "tagent1",  "name": "TAgent1",  "emoji": "1️⃣", "group": "main", "role_fa": "رفیق گیمر"},
    {"id": "tagent2",  "name": "TAgent2",  "emoji": "2️⃣", "group": "main", "role_fa": "رفیق گیمر"},
    {"id": "tagent3",  "name": "TAgent3",  "emoji": "3️⃣", "group": "main", "role_fa": "رفیق گیمر"},
    {"id": "tagent4",  "name": "TAgent4",  "emoji": "4️⃣", "group": "main", "role_fa": "رفیق گیمر"},
]

AGENT_BY_ID = {a["id"]: a for a in AGENTS}

GROUP_FA = {
    "main": "ایجنت‌های main",
}

STATUS_FA = {
    "working": "مشغول به کار",
    "idle": "بیکار",
    "paused": "متوقف‌شده",
    "error": "خطا",
}
