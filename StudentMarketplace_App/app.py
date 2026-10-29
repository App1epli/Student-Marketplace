from __future__ import annotations

import html
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse


BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "database"
DB_PATH = DB_DIR / "student_marketplace.db"
HOST, PORT = "127.0.0.1", 8000

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_number TEXT NOT NULL UNIQUE CHECK (trim(student_number) <> ''),
    full_name TEXT NOT NULL CHECK (trim(full_name) <> ''),
    email TEXT NOT NULL UNIQUE CHECK (email = lower(trim(email)) AND instr(email, '@') > 1),
    study_program TEXT NOT NULL CHECK (trim(study_program) <> ''),
    study_year INTEGER NOT NULL CHECK (study_year BETWEEN 1 AND 4)
);
CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL UNIQUE CHECK (trim(category_name) <> ''),
    description TEXT NOT NULL CHECK (trim(description) <> ''),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER NOT NULL REFERENCES students(student_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    category_id INTEGER NOT NULL REFERENCES categories(category_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    product_name TEXT NOT NULL CHECK (trim(product_name) <> ''),
    description TEXT NOT NULL CHECK (trim(description) <> ''),
    price NUMERIC NOT NULL CHECK (price > 0),
    item_condition TEXT NOT NULL CHECK (item_condition IN ('New', 'Like New', 'Good', 'Fair')),
    status TEXT NOT NULL DEFAULT 'Available' CHECK (status IN ('Available', 'Sold', 'Removed')),
    listed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS purchases (
    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id INTEGER NOT NULL REFERENCES students(student_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    product_id INTEGER NOT NULL UNIQUE REFERENCES products(product_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    purchase_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    agreed_price NUMERIC NOT NULL CHECK (agreed_price > 0),
    payment_method TEXT NOT NULL CHECK (payment_method IN ('Cash', 'Bank Transfer'))
);
"""

STUDENTS = [
    ("2026001", "Dana Omar", "dana.omar@example.edu", "Information Systems", 2),
    ("2026002", "Ayan Bek", "ayan.bek@example.edu", "Computer Science", 3),
    ("2026003", "Amir Sadyk", "amir.sadyk@example.edu", "Business Informatics", 1),
    ("2026004", "Aisha Nurlan", "aisha.nurlan@example.edu", "Information Systems", 2),
    ("2026005", "Dias Kairat", "dias.kairat@example.edu", "Computer Science", 4),
]
CATEGORIES = [
    ("Electronics", "Small personal electronics and accessories"),
    ("Books and Study", "Textbooks, notes, and study supplies"),
    ("Dorm Essentials", "Useful furniture and accessories for student rooms"),
    ("Clothing and Bags", "Clothing, backpacks, and everyday carry items"),
]
PRODUCTS = [
    (1, 1, "Scientific Calculator", "Scientific calculator with protective cover.", 2500, "Good", "Available"),
    (1, 2, "Java Programming Textbook", "Introductory Java textbook with clean pages.", 3500, "Like New", "Available"),
    (2, 1, "Wireless Mouse", "Wireless mouse with USB receiver.", 5500, "Good", "Available"),
    (3, 3, "Desk Lamp", "Adjustable LED desk lamp for a study desk.", 6000, "Good", "Available"),
    (2, 4, "Campus Backpack", "Everyday backpack with laptop sleeve.", 4000, "Fair", "Sold"),
    (5, 3, "Laptop Stand", "Foldable aluminium laptop stand.", 7000, "New", "Removed"),
]


def connect() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def initialize_database() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO students (student_number, full_name, email, study_program, study_year) VALUES (?, ?, ?, ?, ?)",
                STUDENTS,
            )
            conn.executemany(
                "INSERT INTO categories (category_name, description) VALUES (?, ?)", CATEGORIES
            )
            conn.executemany(
                "INSERT INTO products (seller_id, category_id, product_name, description, price, item_condition, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                PRODUCTS,
            )
            conn.execute(
                "INSERT INTO purchases (buyer_id, product_id, agreed_price, payment_method) VALUES (4, 5, 3800, 'Cash')"
            )
    finally:
        conn.close()


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def money(value: object) -> str:
    amount = f"{float(value):,.0f}".replace(",", " ")
    return f"{amount} ₸"


def plural_word(value: int, one: str, few: str, many: str) -> str:
    tail = value % 100
    if 11 <= tail <= 14:
        return many
    elif value % 10 == 1:
        return one
    return few if value % 10 in (2, 3, 4) else many


def plural_ru(value: int, one: str, few: str, many: str) -> str:
    return f"{value} {plural_word(value, one, few, many)}"


CATEGORY_LABELS = {
    "Electronics": "Электроника",
    "Books and Study": "Книги и учёба",
    "Dorm Essentials": "Для дома и общежития",
    "Clothing and Bags": "Одежда и сумки",
}
CONDITION_LABELS = {"New": "Новое", "Like New": "Как новое", "Good": "Хорошее", "Fair": "Есть следы использования"}
STATUS_LABELS = {"Available": "В продаже", "Sold": "Продано", "Removed": "Снято с продажи", "All": "Все объявления"}


def page(title: str, content: str, notice: str = "") -> bytes:
    banner = f'<div class="notice" role="status"><span class="notice-icon">✓</span><span>{e(notice)}</span></div>' if notice else ""
    document = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#142d44"><title>{e(title)} | Студенческий маркет</title>
<style>
:root{{--ink:#203244;--muted:#728092;--blue:#315d85;--pale:#f2f5f8;--line:#e3e8ee;--green:#277653;--gold:#d29b52;--paper:#fff}}
*{{box-sizing:border-box}}body{{margin:0;background:#f7f8fa;color:var(--ink);font:15px/1.55 Inter,"Segoe UI",Arial,sans-serif}}
header{{background:linear-gradient(110deg,#142d44,#244664);color:#fff;padding:17px max(calc((100vw - 1180px)/2),24px)}}.topbar{{max-width:1180px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:20px}}.brand{{display:flex;align-items:center;gap:11px;color:white;text-decoration:none}}.brand-mark{{width:39px;height:39px;border-radius:13px;background:#fff;color:#244664;display:grid;place-items:center;font-weight:800;font-size:17px}}.brand-title{{font-weight:750;font-size:18px;letter-spacing:-.3px}}.brand-sub{{font-size:12px;color:#c6d4df;margin-top:1px}}.demo-pill{{font-size:12px;color:#e4ebf0;border:1px solid #ffffff35;padding:6px 10px;border-radius:99px}}
main{{max-width:1180px;margin:0 auto;padding:22px 22px 50px}}.nav{{display:flex;gap:8px;margin:0 0 22px;flex-wrap:wrap}}.nav a{{color:#66788a;text-decoration:none;padding:8px 12px;border-radius:8px;font-size:14px}}.nav a:hover,.nav a.active{{background:#e9eef3;color:#203244}}
a.button,button{{display:inline-flex;align-items:center;justify-content:center;gap:7px;border:0;border-radius:8px;background:#315d85;color:white;padding:10px 14px;text-decoration:none;font:inherit;font-size:14px;font-weight:650;cursor:pointer;transition:background .15s,transform .15s}}a.button:hover,button:hover{{background:#254a6d;transform:translateY(-1px)}}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{{outline:3px solid #99bedb;outline-offset:2px}}
.hero{{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding:12px 0 24px}}.eyebrow{{font-size:12px;letter-spacing:1.1px;text-transform:uppercase;color:#7d8da0;font-weight:700}}.hero h1{{font-size:32px;line-height:1.15;letter-spacing:-1px;margin:6px 0 8px;color:#1d3449}}.hero p{{color:#6d7c8c;margin:0;max-width:620px}}.stats{{display:flex;gap:10px;flex-wrap:wrap}}.stat{{background:#fff;border:1px solid var(--line);padding:9px 13px;border-radius:10px;color:var(--muted);font-size:12px;white-space:nowrap}}.stat b{{color:var(--ink);font-size:18px;margin-right:5px;vertical-align:-1px}}
.workspace{{display:grid;grid-template-columns:minmax(0,1fr) 335px;gap:20px;align-items:start}}.panel{{background:var(--paper);border:1px solid var(--line);border-radius:13px;padding:18px;box-shadow:0 3px 12px #1a30400a}}h2{{font-size:18px;letter-spacing:-.25px;margin:0}}.panel-heading{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}}.subtle{{color:var(--muted);font-size:13px}}
.filters{{display:grid;grid-template-columns:minmax(150px,1fr) 180px 150px auto;gap:8px;margin-bottom:13px}}input,select,textarea{{width:100%;border:1px solid #d9e0e7;border-radius:8px;padding:10px 11px;background:white;color:var(--ink);font:inherit;font-size:14px}}input::placeholder,textarea::placeholder{{color:#9aa5b1}}textarea{{min-height:84px;resize:vertical}}label{{display:block;font-size:13px;font-weight:650;margin:12px 0 5px}}.hint{{font-size:12px;color:var(--muted);margin-top:4px}}
.catalog{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}.listing{{border:1px solid var(--line);border-radius:11px;background:#fff;padding:15px;min-width:0;display:flex;flex-direction:column;gap:10px;transition:border-color .15s,box-shadow .15s}}.listing:hover{{border-color:#bdccda;box-shadow:0 5px 16px #1d34490b}}.listing-top{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}}.listing h3{{font-size:16px;line-height:1.3;margin:0;letter-spacing:-.2px}}.muted{{color:var(--muted);font-size:12px}}.description{{color:#59697a;font-size:13px;min-height:39px}}.tags{{display:flex;gap:6px;flex-wrap:wrap}}.tag,.badge{{display:inline-flex;align-items:center;border-radius:99px;background:#f0f3f6;color:#5e6d7c;padding:3px 9px;font-size:11px}}.badge{{background:#e9f5ee;color:var(--green);font-weight:650;white-space:nowrap}}.badge.sold{{background:#f2f0ed;color:#857355}}.price{{font-weight:750;font-size:20px;letter-spacing:-.4px;color:#223e56;white-space:nowrap}}.seller{{font-size:12px;color:#6a7886}}.card-bottom{{display:flex;justify-content:space-between;align-items:center;gap:9px;margin-top:auto;padding-top:4px}}details.buy{{border-top:1px solid var(--line);padding-top:10px;margin-top:2px}}details.buy summary{{color:var(--blue);font-size:13px;font-weight:650;cursor:pointer;list-style:none;display:flex;justify-content:space-between}}details.buy summary::-webkit-details-marker{{display:none}}details.buy summary:after{{content:'+';font-size:18px;line-height:1}}details.buy[open] summary:after{{content:'−'}}.buy-fields{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}}.buy-fields select{{font-size:12px;padding:8px}}.buy-fields button{{grid-column:1/-1;width:100%}}
.form-panel{{position:sticky;top:16px}}.form-intro{{font-size:13px;color:var(--muted);margin:5px 0 13px}}.form-grid{{display:grid;grid-template-columns:1fr 1fr;gap:0 9px}}.wide{{grid-column:1/-1}}.form-actions{{margin-top:14px}}.form-actions button{{width:100%}}.safe-note{{font-size:11px;color:#83909d;margin:11px 0 0;line-height:1.45}}.empty{{padding:42px 18px;text-align:center;border:1px dashed #d6dfe7;border-radius:10px;color:var(--muted);grid-column:1/-1}}.empty-icon{{font-size:27px;color:#9cabb9;margin-bottom:7px}}.notice{{display:flex;gap:9px;align-items:center;background:#eff7f1;border:1px solid #d6e9dc;color:#286343;padding:10px 13px;border-radius:9px;margin-bottom:15px;font-size:14px}}.notice-icon{{font-weight:800}}
.sales-table{{width:100%;border-collapse:collapse;margin-top:14px}}th,td{{text-align:left;border-bottom:1px solid var(--line);padding:11px 9px;font-size:13px}}th{{background:#f6f8fa;color:#657587;font-weight:650}}footer{{max-width:1180px;margin:20px auto 0;padding:18px 4px 0;border-top:1px solid var(--line);color:#8793a0;font-size:12px}}
@media(max-width:950px){{.workspace{{grid-template-columns:1fr}}.form-panel{{position:static}}.filters{{grid-template-columns:1fr 1fr}}.hero{{align-items:flex-start;flex-direction:column}}}}
@media(max-width:620px){{main{{padding:16px 14px 36px}}header{{padding:14px}}.demo-pill{{display:none}}.hero h1{{font-size:27px}}.catalog{{grid-template-columns:1fr}}.filters{{grid-template-columns:1fr 1fr}}.filters input{{grid-column:1/-1}}.filters button{{grid-column:1/-1}}.panel{{padding:14px}}}}
</style></head><body><header><div class="topbar"><a class="brand" href="/"><span class="brand-mark">SM</span><span><span class="brand-title">Студенческий маркет</span><br><span class="brand-sub">Вещи находят новых владельцев</span></span></a><span class="demo-pill">Учебный проект</span></div></header>
<main>{banner}<nav class="nav"><a class="active" href="/">Каталог</a><a href="/sales">История покупок</a></nav>{content}
<footer>Демонстрационный проект. Все аккаунты и объявления в примере вымышлены.</footer></main></body></html>"""
    return document.encode("utf-8")


def listing_form(conn: sqlite3.Connection) -> str:
    students = conn.execute("SELECT student_id, full_name FROM students ORDER BY full_name").fetchall()
    categories = conn.execute("SELECT category_id, category_name FROM categories WHERE is_active = 1 ORDER BY category_name").fetchall()
    seller_options = '<option value="">Выберите продавца</option>' + "".join(
        f'<option value="{r["student_id"]}">{e(r["full_name"])}</option>' for r in students
    )
    category_options = '<option value="">Выберите категорию</option>' + "".join(
        f'<option value="{r["category_id"]}">{e(CATEGORY_LABELS.get(r["category_name"], r["category_name"]))}</option>' for r in categories
    )
    condition_options = "".join(
        f'<option value="{e(value)}">{e(label)}</option>' for value, label in CONDITION_LABELS.items()
    )
    return f"""<section class="panel form-panel"><h2>Разместить объявление</h2>
<p class="form-intro">Расскажите о вещи - покупатели увидят её в каталоге.</p>
<form method="post" action="/listing"><div class="form-grid">
<div class="wide"><label for="seller">Кто продаёт</label><select id="seller" name="seller_id" required>{seller_options}</select></div>
<div class="wide"><label for="category">Категория</label><select id="category" name="category_id" required>{category_options}</select></div>
<div class="wide"><label for="name">Название</label><input id="name" name="product_name" maxlength="120" placeholder="Например, учебник по программированию" required></div>
<div class="wide"><label for="description">Описание</label><textarea id="description" name="description" placeholder="Состояние, комплектность и другие детали" required></textarea></div>
<div><label for="price">Цена, ₸</label><input id="price" name="price" type="number" min="1" step="0.01" placeholder="3500" required></div>
<div><label for="condition">Состояние</label><select id="condition" name="item_condition">{condition_options}</select></div>
</div><div class="form-actions"><button type="submit">Опубликовать объявление</button></div>
<p class="safe-note">Укажите честную цену и опишите состояние товара. Объявление можно будет сразу увидеть в каталоге.</p></form></section>"""


class MarketplaceHandler(BaseHTTPRequestHandler):
    server_version = "StudentMarketplace/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_page(self, data: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, path: str) -> None:
        self.send_response(303)
        self.send_header("Location", path)
        self.end_headers()

    def form(self) -> dict[str, str]:
        length = min(int(self.headers.get("Content-Length", "0")), 20_000)
        values = parse_qs(self.rfile.read(length).decode("utf-8", "replace"), keep_blank_values=True)
        return {key: value[0].strip() for key, value in values.items()}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        conn = connect()
        try:
            if parsed.path == "/sales":
                rows = conn.execute("""SELECT pu.purchase_id, pu.purchase_date, pu.agreed_price,
                    pu.payment_method, buyer.full_name AS buyer, p.product_name, seller.full_name AS seller
                    FROM purchases pu JOIN students buyer ON buyer.student_id = pu.buyer_id
                    JOIN products p ON p.product_id = pu.product_id
                    JOIN students seller ON seller.student_id = p.seller_id
                    ORDER BY pu.purchase_date DESC, pu.purchase_id DESC""").fetchall()
                body = '<section class="panel"><div class="panel-heading"><div><div class="eyebrow">Ваш маркет</div><h2>История покупок</h2></div><span class="tag">' + e(plural_ru(len(rows), 'покупка', 'покупки', 'покупок')) + '</span></div>'
                if rows:
                    body += '<table class="sales-table"><thead><tr><th>Товар</th><th>Покупатель</th><th>Продавец</th><th>Цена</th><th>Оплата</th><th>Дата</th></tr></thead><tbody>'
                    body += "".join(f"<tr><td>{e(r['product_name'])}</td><td>{e(r['buyer'])}</td><td>{e(r['seller'])}</td><td>{money(r['agreed_price'])}</td><td>{'Наличные' if r['payment_method'] == 'Cash' else 'Перевод'}</td><td>{e(r['purchase_date'])}</td></tr>" for r in rows)
                    body += "</tbody></table>"
                else:
                    body += '<div class="empty"><div class="empty-icon">↗</div><strong>Покупок пока нет</strong><br><span class="muted">Когда товар купят, запись появится здесь.</span></div>'
                body += "</section>"
                self.send_page(page("История покупок", body))
                return
            if parsed.path != "/":
                self.send_page(page("Страница не найдена", '<section class="panel"><h2>Такой страницы нет</h2><p>Вернитесь в каталог и продолжайте покупки.</p><a class="button" href="/">Открыть каталог</a></section>'), 404)
                return

            search = params.get("q", [""])[0].strip()
            status = params.get("status", ["Available"])[0]
            if status not in ("Available", "Sold", "Removed", "All"):
                status = "Available"
            categories = conn.execute("SELECT category_id, category_name FROM categories WHERE is_active=1 ORDER BY category_name").fetchall()
            category_id = params.get("category", [""])[0]
            if category_id and not category_id.isdigit():
                category_id = ""
            clauses, args = [], []
            if status != "All":
                clauses.append("p.status = ?"); args.append(status)
            if category_id:
                clauses.append("p.category_id = ?"); args.append(int(category_id))
            if search:
                clauses.append("(p.product_name LIKE ? OR p.description LIKE ? OR c.category_name LIKE ? OR s.full_name LIKE ?)")
                term = f"%{search}%"; args.extend([term, term, term, term])
            where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            rows = conn.execute("""SELECT p.product_id, p.product_name, p.description, p.price,
                p.item_condition, p.status, c.category_name, s.full_name AS seller, s.student_id AS seller_id
                FROM products p JOIN categories c ON c.category_id=p.category_id
                JOIN students s ON s.student_id=p.seller_id""" + where + " ORDER BY CASE p.status WHEN 'Available' THEN 0 ELSE 1 END, p.price, p.product_id", args).fetchall()
            counts = {r["status"]: r["n"] for r in conn.execute("SELECT status, COUNT(*) AS n FROM products GROUP BY status")}
            people = conn.execute("SELECT student_id, full_name FROM students ORDER BY full_name").fetchall()
            cards = []
            for r in rows:
                badge = "badge" if r["status"] == "Available" else "badge inactive"
                actions = ""
                if r["status"] == "Available":
                    buyers = "".join(
                        f'<option value="{p["student_id"]}">{e(p["full_name"])}</option>'
                        for p in people if p["student_id"] != r["seller_id"]
                    )
                    actions = f'''<details class="buy"><summary>Оформить покупку</summary>
                    <form method="post" action="/purchase" class="buy-fields"><input type="hidden" name="product_id" value="{r['product_id']}">
                    <select name="buyer_id" aria-label="Кто покупает" required>{buyers}</select>
                    <select name="payment_method" aria-label="Способ оплаты"><option value="Cash">Наличные</option><option value="Bank Transfer">Перевод</option></select>
                    <button type="submit">Подтвердить покупку</button></form></details>'''
                cards.append(f'''<article class="listing"><div class="listing-top"><div><div class="tags"><span class="tag">{e(CATEGORY_LABELS.get(r['category_name'], r['category_name']))}</span><span class="tag">{e(CONDITION_LABELS.get(r['item_condition'], r['item_condition']))}</span></div><h3 style="margin-top:9px">{e(r['product_name'])}</h3></div><span class="{badge}">{e(STATUS_LABELS.get(r['status'], r['status']))}</span></div>
                    <div class="description">{e(r['description'])}</div><div class="card-bottom"><div><div class="price">{money(r['price'])}</div><div class="seller">Продавец: {e(r['seller'])}</div></div></div>{actions}</article>''')
            items = "".join(cards) or '<div class="empty"><div class="empty-icon">⌕</div><strong>Ничего не нашлось</strong><br><span class="muted">Попробуйте изменить запрос или выбрать другую категорию.</span></div>'
            category_options = '<option value="">Все категории</option>' + "".join(
                f'<option value="{r["category_id"]}"' + (' selected' if str(r["category_id"]) == category_id else '') +
                f'>{e(CATEGORY_LABELS.get(r["category_name"], r["category_name"]))}</option>' for r in categories
            )
            status_options = "".join(
                f'<option value="{value}"' + (' selected' if status == value else '') + f'>{label}</option>'
                for value, label in STATUS_LABELS.items()
            )
            body = f'''<section class="hero"><div><div class="eyebrow">Покупай рядом, продавай просто</div><h1>Найди нужное для учёбы</h1><p>Учебники, техника и вещи для комнаты от студентов твоего университета.</p></div>
            <div class="stats"><span class="stat"><b>{counts.get('Available',0)}</b> в продаже</span><span class="stat"><b>{counts.get('Sold',0)}</b> {e(plural_word(counts.get('Sold',0), 'продажа', 'продажи', 'продаж'))}</span></div></section>
            <div class="workspace"><section class="panel"><div class="panel-heading"><div><div class="eyebrow">Студенческие объявления</div><h2>Каталог товаров</h2></div><span class="subtle">{e(plural_ru(len(rows), 'объявление', 'объявления', 'объявлений'))}</span></div>
            <form class="filters" method="get" action="/"><input name="q" placeholder="Название, описание или продавец" value="{e(search)}" aria-label="Поиск по объявлениям">
            <select name="category" aria-label="Категория">{category_options}</select><select name="status" aria-label="Статус объявления">{status_options}</select><button type="submit">Найти</button></form>
            <div class="catalog">{items}</div></section>{listing_form(conn)}</div>'''
            notice = params.get("notice", [""])[0]
            self.send_page(page("Каталог товаров", body, notice))
        finally:
            conn.close()

    def do_POST(self) -> None:
        form = self.form()
        conn = connect()
        try:
            if self.path == "/listing":
                name, description = form.get("product_name", ""), form.get("description", "")
                try:
                    seller_id, category_id = int(form["seller_id"]), int(form["category_id"])
                    price = round(float(form["price"]), 2)
                    condition = form.get("item_condition", "")
                    if not name or not description or price <= 0 or condition not in ("New", "Like New", "Good", "Fair"):
                        raise ValueError
                    conn.execute("INSERT INTO products (seller_id, category_id, product_name, description, price, item_condition) VALUES (?, ?, ?, ?, ?, ?)",
                                 (seller_id, category_id, name, description, price, condition))
                except (KeyError, ValueError, OverflowError, sqlite3.IntegrityError):
                    self.send_page(page("Ошибка объявления", '<section class="panel"><h2>Не удалось разместить объявление</h2><p>Проверьте обязательные поля и укажите цену больше нуля.</p><a class="button" href="/">Вернуться в каталог</a></section>'), 400)
                    return
                self.redirect("/?notice=" + quote("Объявление опубликовано"))
                return
            if self.path == "/purchase":
                try:
                    buyer_id, product_id = int(form["buyer_id"]), int(form["product_id"])
                    payment = form.get("payment_method", "")
                    if payment not in ("Cash", "Bank Transfer"):
                        raise ValueError
                    conn.execute("BEGIN IMMEDIATE")
                    product = conn.execute("SELECT * FROM products WHERE product_id=?", (product_id,)).fetchone()
                    if not product or product["status"] != "Available":
                        raise ValueError("Это объявление уже недоступно.")
                    if product["seller_id"] == buyer_id:
                        raise ValueError("Нельзя купить собственное объявление.")
                    if not conn.execute("SELECT 1 FROM students WHERE student_id=?", (buyer_id,)).fetchone():
                        raise ValueError("Выберите покупателя из списка.")
                    conn.execute("INSERT INTO purchases (buyer_id, product_id, agreed_price, payment_method) VALUES (?, ?, ?, ?)",
                                 (buyer_id, product_id, product["price"], payment))
                    changed = conn.execute("UPDATE products SET status='Sold' WHERE product_id=? AND status='Available'", (product_id,)).rowcount
                    if changed != 1:
                        raise ValueError("Это объявление уже недоступно.")
                    conn.commit()
                except (KeyError, ValueError, sqlite3.IntegrityError, sqlite3.OperationalError) as exc:
                    if conn.in_transaction:
                        conn.rollback()
                    message = str(exc) or "Не удалось оформить покупку."
                    self.redirect("/?notice=" + quote(message))
                    return
                self.redirect("/?notice=" + quote("Покупка успешно оформлена"))
                return
            self.send_page(page("Not found", '<section class="panel"><h2>Unknown action</h2><a href="/">Return to marketplace</a></section>'), 404)
        finally:
            conn.close()


def main() -> None:
    initialize_database()
    if "--init-db" in sys.argv:
        with connect() as conn:
            print(f"Database ready: {DB_PATH}")
            print(f"Students: {conn.execute('SELECT COUNT(*) FROM students').fetchone()[0]}")
            print(f"Products: {conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]}")
        return
    server = ThreadingHTTPServer((HOST, PORT), MarketplaceHandler)
    print(f"Student Marketplace is running at http://{HOST}:{PORT}")
    print(f"SQLite database: {DB_PATH}")
    print("Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
