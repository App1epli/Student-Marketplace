"""Small, dependency-free UI catalogs shared by Jinja and browser scripts.

English source strings are message keys. Product names, descriptions, names,
reviews and chat messages are user content and are never translated.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, abort, has_request_context, redirect, request

bp = Blueprint("i18n", __name__)
LANGUAGES = (("kk", "KZ", "Қазақша"), ("ru", "RU", "Русский"), ("en", "EN", "English"))
DEFAULT_LANGUAGE = "en"
CATALOGS = {code: json.loads((Path(__file__).parent / "locales" / f"{code}.json").read_text(encoding="utf-8"))
            for code in ("kk", "ru")}


# Keep the browser payload limited to wallet, photo and chat feedback.
CLIENT_MESSAGES = frozenset({
    '+ Add card',
    'Add a card to continue',
    'Add a card to unlock the purchase button.',
    'Add a valid card before buying this item.',
    'Add card',
    'Adding card…',
    'Adding your test card…',
    'Card added. You can now complete your demo purchase.',
    'Card could not be added. Please try again.',
    'Choose up to 3 JPG, PNG or WebP photos, 1 MB each.',
    'Could not load the wallet. Please try again.',
    'EXP {expiry}',
    'Enter a cardholder name using 2–80 letters, spaces, apostrophes or hyphens.',
    'Enter a current or future expiry date as MM/YY.',
    'Enter the expiry date as MM/YY.',
    'Enter valid demo card details.',
    'Loading your saved card…',
    'No messages yet. Send a greeting to start chatting!',
    'No files selected',
    'Check out this item on Student Marketplace!',
    'Link copied!',
    'Copy this link: {url}',
    'Could not share this link.',
    'Pay with demo card · {total}',
    'Preview: {name}',
    'Processing demo order…',
    'Removing card…',
    'Replace card',
    'Select a buyer from the list.',
    'Select a buyer to add a card.',
    'Select a demo buyer.',
    'Send demo card details as JSON.',
    'The database is unavailable. Please try again later.',
    'The request could not be completed.',
    'This test card has expired. Enter a current or future expiry date.',
    'Use the demo CVV 123.',
    'Use the test card 4242 4242 4242 4242. Real cards are not accepted.',
    'Your test card has expired. Replace it to continue.',
    '{count} photo ready to upload',
    '{count} photos ready to upload',
})


def get_language():
    code = request.cookies.get("language") if has_request_context() else None
    return code if code in {entry[0] for entry in LANGUAGES} else DEFAULT_LANGUAGE


def translate(message, **values):
    text = str(message) if message is not None else ""
    translated = CATALOGS.get(get_language(), {}).get(text, text)
    # Replace named placeholders only, leaving arbitrary/user-provided braces alone.
    return re.sub(r"\{(\w+)\}", lambda match: str(values.get(match[1], match[0])), translated)


def count_label(kind, count):
    language = get_language()
    if language == "ru":
        form = 0 if count % 10 == 1 and count % 100 != 11 else 1 if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14 else 2
        nouns = {"listing": ("объявление", "объявления", "объявлений"),
                 "purchase": ("покупка", "покупки", "покупок"),
                 "rating": ("оценка", "оценки", "оценок"),
                 "conversation": ("диалог", "диалога", "диалогов"),
                 "message": ("сообщение", "сообщения", "сообщений"),
                 "photo": ("фото", "фото", "фото")}
        noun = nouns[kind][form]
    elif language == "kk":
        noun = {"listing": "хабарландыру", "purchase": "сатып алу", "rating": "баға",
                "conversation": "чат", "message": "хабарлама", "photo": "фото"}[kind]
    else:
        noun = kind + ("s" if count != 1 else "")
    return f"{count} {noun}"


@bp.app_context_processor
def inject_i18n():
    language = get_language()
    return {"_": translate, "language": language, "languages": LANGUAGES,
            "count_label": count_label,
            "client_translations": {key: value for key, value in CATALOGS.get(language, {}).items()
                                    if key in CLIENT_MESSAGES}}


@bp.post("/language")
def set_language():
    code = request.form.get("language")
    if code not in {entry[0] for entry in LANGUAGES}:
        abort(400)
    target = request.form.get("next", "/")
    # Redirect only to paths on this site, including the current filters/hash.
    try:
        parsed = urlsplit(target)
    except ValueError:
        target = "/"
        parsed = urlsplit(target)
    if (not target.startswith("/") or target.startswith("//") or parsed.scheme or parsed.netloc
            or "\\" in target or any(ord(char) < 32 or ord(char) == 127 for char in target)):
        target = "/"
    response = redirect(target, code=303)
    response.set_cookie("language", code, max_age=365 * 24 * 60 * 60, httponly=True,
                        secure=request.is_secure, samesite="Lax")
    return response
