from contextlib import closing
import hashlib
import sqlite3

import pytest

from opspilot_x import auth


PASSWORD = 'temporary-test-password-2026'


def provision(path, username='engineer'):
    auth.create_user(path, username=username, password=PASSWORD,
                     tenant='demo', team='team_a', role='engineer')


def test_disable_revokes_existing_sessions_and_denies_new_login(tmp_path):
    db = tmp_path / 'auth.sqlite3'
    provision(db)
    provision(db, 'other')
    token, _ = auth.login(db, 'engineer', PASSWORD, 'local')
    other, _ = auth.login(db, 'other', PASSWORD, 'local')
    assert auth.session(db, token)
    auth.disable_user(db, 'engineer')
    auth.disable_user(db, 'engineer')
    assert auth.session(db, token) is None
    assert auth.login(db, 'engineer', PASSWORD, 'local') is None
    assert auth.session(db, other)['user_id'] == 'other'


def test_revoke_only_keeps_credentials_valid_but_denies_old_token(tmp_path):
    db = tmp_path / 'auth.sqlite3'
    provision(db)
    token, _ = auth.login(db, 'engineer', PASSWORD, 'local')
    auth.revoke_sessions(db, 'engineer')
    assert auth.session(db, token) is None
    replacement, _ = auth.login(db, 'engineer', PASSWORD, 'local')
    assert replacement != token and auth.session(db, replacement)
    with pytest.raises(ValueError, match='Unknown account'):
        auth.disable_user(db, 'missing')
    with pytest.raises(ValueError, match='Unknown account'):
        auth.revoke_sessions(db, 'missing')


@pytest.mark.parametrize('operation', ['disable_user', 'revoke_sessions'])
def test_revoke_during_password_verification_cannot_issue_new_session(tmp_path, monkeypatch, operation):
    db = tmp_path / 'auth.sqlite3'
    provision(db)
    pbkdf = hashlib.pbkdf2_hmac

    def revoke_while_hashing(*args, **kwargs):
        getattr(auth, operation)(db, 'engineer')
        return pbkdf(*args, **kwargs)

    monkeypatch.setattr(auth.hashlib, 'pbkdf2_hmac', revoke_while_hashing)
    assert auth.login(db, 'engineer', PASSWORD, 'local') is None
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0


def test_legacy_user_migration_preserves_account_and_is_repeatable(tmp_path):
    db = tmp_path / 'old.sqlite3'
    salt = bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', PASSWORD.encode(), salt, auth.ITERATIONS).hex()
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute('CREATE TABLE users (username TEXT PRIMARY KEY,user_id TEXT UNIQUE NOT NULL,'
                     'tenant TEXT NOT NULL,team TEXT NOT NULL,role TEXT NOT NULL,'
                     'salt TEXT NOT NULL,password_hash TEXT NOT NULL)')
        conn.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?)',
                     ('legacy','legacy','demo','team_a','engineer',salt.hex(),digest))
    auth.initialize(db)
    auth.initialize(db)
    token, _ = auth.login(db, 'legacy', PASSWORD, 'local')
    assert auth.session(db, token)['user_id'] == 'legacy'
    auth.disable_user(db, 'legacy')
    assert auth.session(db, token) is None


@pytest.mark.parametrize('action', ['disable', 'revoke-sessions'])
def test_management_cli_revokes_without_password_prompt(tmp_path, monkeypatch, action, capsys):
    import sys
    from scripts.manage_users import main
    db = tmp_path / 'auth.sqlite3'
    provision(db)
    token, _ = auth.login(db, 'engineer', PASSWORD, 'local')
    monkeypatch.setattr(sys, 'argv', ['manage_users.py', '--db', str(db),
                                    '--username', 'engineer', '--action', action])

    def no_password_prompt(*args):
        pytest.fail('Revocation must not read or ask for a password')

    monkeypatch.setattr('scripts.manage_users.getpass.getpass', no_password_prompt)
    main()
    assert auth.session(db, token) is None
    assert 'sessions revoked' in capsys.readouterr().out
    assert (auth.login(db, 'engineer', PASSWORD, 'local') is None) == (action == 'disable')


def test_management_cli_refuses_missing_database_and_incomplete_create(tmp_path, monkeypatch):
    import sys
    from scripts.manage_users import main
    db = tmp_path / 'missing.sqlite3'
    monkeypatch.setattr(sys, 'argv', ['manage_users.py', '--db', str(db),
                                    '--username', 'unknown', '--action', 'disable'])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 2 and not db.exists()
    monkeypatch.setattr(sys, 'argv', ['manage_users.py', '--db', str(db), '--username', 'new'])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 2 and not db.exists()


def test_management_cli_keeps_existing_create_invocation(tmp_path, monkeypatch):
    import sys
    from scripts.manage_users import main
    db = tmp_path / 'auth.sqlite3'
    monkeypatch.setattr(sys, 'argv', ['manage_users.py', '--db', str(db), '--username', 'new',
                                    '--tenant', 'demo', '--team', 'team_a', '--role', 'engineer'])
    monkeypatch.setenv('OPSPILOT_INITIAL_PASSWORD', PASSWORD)
    main()
    assert auth.login(db, 'new', PASSWORD, 'local') is not None


@pytest.mark.parametrize('operation', ['disable_user', 'revoke_sessions'])
def test_revocation_is_enforced_at_api_boundary(client, tmp_path, operation):
    from conftest import PASSWORD as API_PASSWORD
    db = tmp_path / 'test.sqlite3'
    assert client.get('/api/v1/auth/me').status_code == 200
    getattr(auth, operation)(db, 'engineer-1')
    assert client.get('/api/v1/auth/me').status_code == 401
    assert client.get('/api/v1/proposals').status_code == 401
    response = client.post('/api/v1/auth/login',
                           json={'username': 'engineer-1', 'password': API_PASSWORD})
    assert response.status_code == (401 if operation == 'disable_user' else 200)
