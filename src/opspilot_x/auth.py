"""Local account credentials and revocable opaque sessions; no identity provider."""
from contextlib import closing, contextmanager
import hashlib
import hmac
import secrets
import sqlite3
import time

from .schema import Actor

ITERATIONS = 600_000
SESSION_SECONDS = 8 * 3600
COOKIE = "opspilot_session"

@contextmanager
def connection(path):
    with closing(sqlite3.connect(str(path), timeout=8)) as db:
        db.row_factory = sqlite3.Row
        with db:
            yield db


def initialize(path):
    with connection(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, user_id TEXT UNIQUE NOT NULL,
            tenant TEXT NOT NULL, team TEXT NOT NULL, role TEXT NOT NULL,
            salt TEXT NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
            csrf_token TEXT NOT NULL, expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts (
            bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, started_at REAL NOT NULL);
        """)
        db.execute('BEGIN IMMEDIATE')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(users)')}
        if 'disabled' not in columns:
            db.execute('ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1))')
        if 'session_version' not in columns:
            db.execute('ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0')


def create_user(path, *, username, password, user_id=None, tenant, team, role):
    actor = Actor(user_id=user_id or username, tenant=tenant, team=team, role=role)
    if not 1 <= len(username) <= 80 or not 12 <= len(password) <= 1024:
        raise ValueError("Username must be 1-80 characters; password must be 12-1024 characters")
    initialize(path)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    with connection(path) as db:
        db.execute('INSERT INTO users (username,user_id,tenant,team,role,salt,password_hash) VALUES (?,?,?,?,?,?,?)',
                   (username, actor.user_id, tenant, team, role, salt, digest))
    return actor


def login(path, username, password, address):
    now = time.time()
    buckets = [hashlib.sha256(('user:' + username).encode()).hexdigest(),
               hashlib.sha256(('ip:' + address).encode()).hexdigest()]
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM login_attempts WHERE started_at < ?', (now - 900,))
        for bucket, limit in zip(buckets, (10, 50)):
            row = db.execute('SELECT attempts FROM login_attempts WHERE bucket=?', (bucket,)).fetchone()
            if row and row['attempts'] >= limit:
                return None
        for bucket in buckets:
            db.execute('INSERT INTO login_attempts VALUES (?,1,?) ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1', (bucket, now))
        row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    salt = bytes.fromhex(row['salt']) if row else bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS).hex()
    if not row or row['disabled'] or not hmac.compare_digest(digest, row['password_hash']):
        return None
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if (not current or current['disabled']
                or current['session_version'] != row['session_version']
                or current['password_hash'] != row['password_hash']):
            return None
        db.execute('DELETE FROM sessions WHERE expires_at <= ?', (now,))
        db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (token_hash(token), username, csrf, now + SESSION_SECONDS))
    return token, dict(Actor(**{k: current[k] for k in ('user_id','tenant','team','role')}).model_dump(), csrf_token=csrf)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def session(path, token):
    if not token or len(token) > 256:
        return None
    with connection(path) as db:
        row = db.execute('SELECT u.user_id,u.tenant,u.team,u.role,s.csrf_token FROM sessions s JOIN users u ON s.username=u.username WHERE token_hash=? AND expires_at>? AND u.disabled=0', (token_hash(token), time.time())).fetchone()
        return dict(row) if row else None


def logout(path, token):
    with connection(path) as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(token),))


def revoke_sessions(path, username, *, disable=False):
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        changed = db.execute('UPDATE users SET session_version=session_version+1, '
                             'disabled=CASE WHEN ? THEN 1 ELSE disabled END WHERE username=?',
                             (disable, username))
        if not changed.rowcount:
            raise ValueError('Unknown account')
        db.execute('DELETE FROM sessions WHERE username=?', (username,))


def disable_user(path, username):
    revoke_sessions(path, username, disable=True)
