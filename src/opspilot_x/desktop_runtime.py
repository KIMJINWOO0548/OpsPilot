"""Private pipe-controlled desktop entry point; never a public bootstrap API."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import sys
import threading

from . import auth


class DesktopBoundary:
    def __init__(self, app, origin, token):
        self.app = app
        self.origin = origin.encode('ascii')
        self.host = origin.removeprefix('http://').encode('ascii')
        self.token = token.encode('ascii')

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            return await self.app(scope, receive, send)
        headers = scope.get('headers', [])

        def values(name):
            return [value for key, value in headers if key.lower() == name]

        tokens = values(b'x-opspilot-desktop-token')
        origins = values(b'origin')
        allowed = (values(b'host') == [self.host] and len(tokens) == 1
                   and hmac.compare_digest(tokens[0], self.token)
                   and (not origins or origins == [self.origin])
                   and b'cross-site' not in values(b'sec-fetch-site'))
        if scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1008})
        elif not allowed:
            await send({'type': 'http.response.start', 'status': 403,
                        'headers': [(b'content-type', b'application/json'),
                                    (b'cache-control', b'no-store')]})
            await send({'type': 'http.response.body', 'body': b'{"detail":"Desktop request denied"}'})
        else:
            await self.app(scope, receive, send)


def emit(output, event, **fields):
    output.write(json.dumps({'event': event, **fields}) + '\n')
    output.flush()


def read_message(stream):
    line = stream.readline(16385)
    if not line:
        return {'event': 'stop'}
    if len(line) > 16384:
        raise ValueError('Pipe message too large')
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ValueError('Invalid pipe message')
    return message


def read_configuration(stream):
    token = read_message(stream).get('token')
    if not isinstance(token, str) or re.fullmatch('[0-9a-f]{64}', token) is None:
        raise ValueError('Invalid desktop configuration')
    return token


def configure_paths(data_dir, web_dir):
    data, web = Path(data_dir), Path(web_dir)
    if not data.is_absolute() or not web.is_absolute():
        raise ValueError('Desktop paths must be absolute')
    if web.name != 'dist' or not (web / 'index.html').is_file() or not (web / 'assets').is_dir():
        raise ValueError('Desktop frontend build missing')
    data.mkdir(parents=True, exist_ok=True)
    path = data / 'opspilot.sqlite3'
    os.environ['OPSPILOT_DB'] = str(path)
    os.environ['OPSPILOT_WEB_DIR'] = str(web.parent)
    os.environ['OPSPILOT_SECURE_COOKIE'] = 'false'
    return path


def create_initial_accounts(path, message):
    rows = []
    for role in ('engineer', 'approver'):
        account = message.get(role)
        if not isinstance(account, dict):
            raise ValueError('Two accounts required')
        username, password = account.get('username'), account.get('password')
        if (not isinstance(username, str) or not 1 <= len(username) <= 80
                or not isinstance(password, str) or not 12 <= len(password) <= 1024):
            raise ValueError('Invalid account fields')
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt),
                                     auth.ITERATIONS).hex()
        rows.append((username, username, 'demo', 'team_a', role, salt, digest))
    if rows[0][0] == rows[1][0]:
        raise ValueError('Accounts must be distinct')
    with auth.connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            raise ValueError('Accounts already configured')
        db.executemany('INSERT INTO users (username,user_id,tenant,team,role,salt,password_hash) '
                       'VALUES (?,?,?,?,?,?,?)', rows)


def setup_accounts(path, stream, output):
    with auth.connection(path) as db:
        if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            return True
    emit(output, 'setup_required')
    while True:
        try:
            message = read_message(stream)
            if message.get('event') == 'stop':
                return False
            create_initial_accounts(path, message)
            return True
        except (ValueError, sqlite3.Error):
            emit(output, 'setup_error', message='Account setup failed. Check both account names and password lengths.')


def run(data_dir, web_dir, stream, output):
    token = read_configuration(stream)
    path = configure_paths(data_dir, web_dir)
    auth.initialize(path)
    if not setup_accounts(path, stream, output):
        return 0

    # api.app is created at import time; the private data paths must be set first.
    from .api import app
    import uvicorn

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        origin = f'http://127.0.0.1:{listener.getsockname()[1]}'
        boundary = DesktopBoundary(app, origin, token)
        config = uvicorn.Config(boundary, host='127.0.0.1', proxy_headers=False,
                                access_log=False, log_config=None, log_level='critical',
                                timeout_graceful_shutdown=5)

        class DesktopServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                if self.started and not self.should_exit:
                    emit(output, 'ready', origin=origin, token=token)

        server = DesktopServer(config)

        def watch_parent():
            try:
                while read_message(stream).get('event') != 'stop':
                    pass
            except (ValueError, OSError):
                pass
            finally:
                server.should_exit = True

        threading.Thread(target=watch_parent, daemon=True, name='desktop-parent').start()
        server.run(sockets=[listener])
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='OpsPilot-X private desktop runtime')
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--web-dir', required=True)
    args = parser.parse_args(argv)
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    # Untrusted request bodies and account secrets must never reach traceback logs.
    logging.disable(logging.CRITICAL)
    try:
        return run(args.data_dir, args.web_dir, sys.stdin, sys.stdout)
    except (Exception, KeyboardInterrupt) as error:
        code = getattr(error, 'winerror', None)
        suffix = f' (WinError {code})' if isinstance(code, int) else ''
        sys.stderr.write(f'Desktop backend startup or service failed{suffix}.\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
