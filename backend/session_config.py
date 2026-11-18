"""Use an explicit session key or a persistent, random key shared via PostgreSQL."""
import secrets
from flask.sessions import SecureCookieSessionInterface
from backend.database import connect


class PersistentSessionInterface(SecureCookieSessionInterface):
    def open_session(self, app, request):
        if not app.secret_key:
            # Bootstrap only the key store; normal schema migrations remain explicit.
            with connect() as conn:
                conn.execute("SELECT pg_advisory_xact_lock(87421932)")
                conn.execute("""CREATE TABLE IF NOT EXISTS application_settings (
                    setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL)""")
                conn.execute("""INSERT INTO application_settings (setting_key, setting_value)
                    VALUES ('session_secret', ?) ON CONFLICT DO NOTHING""", (secrets.token_hex(32),))
                key = conn.execute("SELECT setting_value FROM application_settings WHERE setting_key='session_secret'").fetchone()[0]
            app.secret_key = key
        return super().open_session(app, request)
