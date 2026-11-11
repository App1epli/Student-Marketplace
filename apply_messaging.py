from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
app = root / 'app.py'
if not app.exists():
    raise SystemExit('app.py not found. Put apply_messaging.py and messaging.py next to app.py.')
source = app.read_text(encoding='utf-8')
if 'messaging.install(MarketplaceHandler' in source:
    raise SystemExit('Messaging is already installed. No changes made.')
changes = [
 ('STUDENTS = [', 'import messaging\n\nPOSTGRES_SCHEMA += messaging.SCHEMA\n\nSTUDENTS = ['),
 ('<a href="/sales">Purchase history</a></nav>', '<a href="/sales">Purchase history</a><a href="/messages">Messages</a></nav>'),
 ("                cards.append(f'''<article class=\"listing\">", "                actions += messaging.message_button(conn, r['product_id'], r['seller_id'])\n                cards.append(f'''<article class=\"listing\">"),
 ('def main() -> None:', 'messaging.install(MarketplaceHandler, connect, page)\n\ndef main() -> None:'),
]
for old, new in changes:
    if source.count(old) != 1:
        raise SystemExit(f'Expected exactly one match, got {source.count(old)}: {old[:75]}')
    source = source.replace(old, new, 1)
compile(source, str(app), 'exec')
backup = root / 'app_before_messaging.py.bak'
shutil.copy2(app, backup)
app.write_text(source, encoding='utf-8')
print('Updated app.py. Backup:', backup.name)
print('Run: python app.py')
