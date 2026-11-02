import io
import json
import sqlite3

import pytest

from opspilot_x import auth, desktop_runtime as desktop

TOKEN = 'a' * 64
ORIGIN = 'http://127.0.0.1:43210'


def accounts():
    return {role: {'username': role, 'password': 'test-only-password-2026'}
            for role in ('engineer', 'approver')}


def invoke(headers, path='/health', scope_type='http'):
    messages, reached = [], []

    async def inner(scope, receive, send):
        reached.append(scope)
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})

    async def send(message):
        messages.append(message)

    async def receive():
        return {'type': 'http.request', 'body': b''}

    coroutine = desktop.DesktopBoundary(inner, ORIGIN, TOKEN)(
        {'type': scope_type, 'path': path, 'headers': headers}, receive, send)
    # These ASGI coroutines perform no I/O; no socket/event-loop workaround is used.
    with pytest.raises(StopIteration):
        coroutine.send(None)
    return messages, reached


@pytest.mark.parametrize('path', ['/', '/health', '/assets/app.js', '/docs', '/api/v1/auth/login'])
def test_boundary_requires_host_and_token_for_every_path(path):
    headers = [(b'host', b'127.0.0.1:43210'),
               (b'x-opspilot-desktop-token', TOKEN.encode())]
    assert invoke(headers, path)[0][0]['status'] == 200
    for bad in (headers[:1], headers[1:], headers + headers[:1],
                [(b'host', b'localhost:43210'), headers[1]],
                [headers[0], (headers[1][0], b'wrong')],
                headers + [(b'origin', b'https://evil.example')],
                headers + [(b'sec-fetch-site', b'cross-site')]):
        messages, reached = invoke(bad, path)
        assert messages[0]['status'] == 403
        assert not reached


def test_boundary_websocket_and_valid_origin():
    headers = [(b'host', b'127.0.0.1:43210'),
               (b'x-opspilot-desktop-token', TOKEN.encode()),
               (b'origin', ORIGIN.encode())]
    assert invoke(headers)[1]
    assert invoke([], scope_type='websocket')[0] == [{'type': 'websocket.close', 'code': 1008}]


def test_setup_creates_both_roles_compatible_with_existing_auth(tmp_path):
    path = tmp_path / 'accounts.db'
    auth.initialize(path)
    desktop.create_initial_accounts(path, accounts())
    for role in ('engineer', 'approver'):
        token, user = auth.login(path, role, accounts()[role]['password'], '127.0.0.1')
        assert user['role'] == role
        assert auth.session(path, token)['role'] == role
    with auth.connection(path) as db:
        before = [tuple(row) for row in db.execute('SELECT * FROM users')]
    with pytest.raises(ValueError):
        desktop.create_initial_accounts(path, accounts())
    with auth.connection(path) as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM users')] == before


@pytest.mark.parametrize('problem', ['duplicate', 'short', 'insert_failure'])
def test_setup_failure_leaves_no_partial_accounts(tmp_path, problem):
    path = tmp_path / 'accounts.db'
    auth.initialize(path)
    body = accounts()
    if problem == 'duplicate':
        body['approver']['username'] = 'engineer'
    elif problem == 'short':
        body['approver']['password'] = 'short'
    else:
        with auth.connection(path) as db:
            db.execute("CREATE TRIGGER fail_approver BEFORE INSERT ON users WHEN NEW.role='approver' BEGIN SELECT RAISE(ABORT, 'test'); END")
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        desktop.create_initial_accounts(path, body)
    with auth.connection(path) as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0


@pytest.mark.parametrize('value', ['', 'a' * 63, 'A' * 64, 'g' * 64, None, 42])
def test_invalid_initial_token(value):
    with pytest.raises(ValueError):
        desktop.read_configuration(io.StringIO(json.dumps({'token': value}) + '\n'))


def test_initial_configuration_and_invalid_paths(tmp_path):
    assert desktop.read_configuration(io.StringIO(json.dumps({'token': TOKEN}))) == TOKEN
    with pytest.raises(ValueError):
        desktop.configure_paths('relative', str(tmp_path))
    with pytest.raises(ValueError):
        desktop.configure_paths(str(tmp_path / 'data'), str(tmp_path / 'missing'))


def test_setup_pipe_retry_and_cancel(tmp_path):
    path = tmp_path / 'accounts.db'
    auth.initialize(path)
    output = io.StringIO()
    assert desktop.setup_accounts(path, io.StringIO('{}\n' + json.dumps(accounts()) + '\n'), output)
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [event['event'] for event in events] == ['setup_required', 'setup_error']
    assert accounts()['engineer']['password'] not in output.getvalue()
    second = tmp_path / 'cancel.db'
    auth.initialize(second)
    assert not desktop.setup_accounts(second, io.StringIO('{"event":"stop"}\n'), io.StringIO())
    with auth.connection(second) as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0


def test_existing_accounts_do_not_prompt_or_modify(tmp_path):
    path = tmp_path / 'accounts.db'
    auth.initialize(path)
    desktop.create_initial_accounts(path, accounts())
    output = io.StringIO()
    assert desktop.setup_accounts(path, io.StringIO(''), output)
    assert output.getvalue() == ''


def test_configuration_uses_private_paths_before_api(tmp_path, monkeypatch):
    web = tmp_path / 'web' / 'dist'
    (web / 'assets').mkdir(parents=True)
    (web / 'index.html').write_text('test', encoding='utf-8')
    for key in ('OPSPILOT_DB', 'OPSPILOT_WEB_DIR', 'OPSPILOT_SECURE_COOKIE'):
        monkeypatch.delenv(key, raising=False)
    path = desktop.configure_paths(str(tmp_path / 'data'), str(web))
    assert desktop.os.environ['OPSPILOT_DB'] == str(path)
    assert desktop.os.environ['OPSPILOT_WEB_DIR'] == str(web.parent)
    assert desktop.os.environ['OPSPILOT_SECURE_COOKIE'] == 'false'


def test_main_bad_configuration_has_no_secret_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(desktop.sys, 'stdin', io.StringIO('{"token":"secret-invalid-token"}'))
    monkeypatch.setattr(desktop.logging, 'disable', lambda level: None)
    assert desktop.main(['--data-dir', str(tmp_path), '--web-dir', str(tmp_path)]) == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert output.err == 'Desktop backend startup or service failed.\n'


def test_real_runner_ready_health_and_eof_shutdown(tmp_path):
    import queue
    import subprocess
    import sys
    import threading
    import urllib.request

    web = tmp_path / 'web' / 'dist'
    (web / 'assets').mkdir(parents=True)
    (web / 'index.html').write_text('test', encoding='utf-8')
    process = subprocess.Popen(
        [sys.executable, '-I', '-u', '-m', 'opspilot_x.desktop_runtime',
         '--data-dir', str(tmp_path / 'data'), '--web-dir', str(web)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8')
    lines = queue.Queue()

    def read_events():
        for line in process.stdout:
            lines.put(line)
        lines.put('')

    threading.Thread(target=read_events, daemon=True).start()
    try:
        process.stdin.write(json.dumps({'token': TOKEN}) + '\n')
        process.stdin.flush()
        assert json.loads(lines.get(timeout=15)) == {'event': 'setup_required'}
        process.stdin.write(json.dumps(accounts()) + '\n')
        process.stdin.flush()
        line = lines.get(timeout=15)
        assert line, process.stderr.read()
        ready = json.loads(line)
        assert ready['event'] == 'ready' and ready['token'] == TOKEN
        assert ready['origin'].startswith('http://127.0.0.1:')
        request = urllib.request.Request(ready['origin'] + '/health',
                                        headers={'X-OpsPilot-Desktop-Token': TOKEN})
        with urllib.request.urlopen(request, timeout=5) as response:
            assert json.load(response)['ok']
        process.stdin.close()
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for pipe in (process.stdin, process.stdout, process.stderr):
            pipe.close()
