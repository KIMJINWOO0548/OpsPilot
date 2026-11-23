from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import sqlite3
from threading import Barrier, Lock
from types import SimpleNamespace

from opspilot_x import auth


PASSWORD = "synthetic-login-password"
WRONG = "synthetic-incorrect-password"
USERNAME = "trial-operator"
ADDRESS = "192.0.2.10"


def provision(path):
    auth.create_user(path, username=USERNAME, password=PASSWORD,
                     tenant="trial", team="operations", role="engineer")


def bucket(kind, value):
    return hashlib.sha256(f"{kind}:{value}".encode()).hexdigest()


def counts(path):
    with closing(sqlite3.connect(path)) as db:
        return dict(db.execute("SELECT bucket, attempts FROM login_attempts"))


def test_twenty_successful_logins_do_not_use_failure_quota(tmp_path):
    path = tmp_path / "logins.sqlite3"
    provision(path)
    for attempt in range(1, 21):
        result = auth.login(path, USERNAME, PASSWORD, ADDRESS)
        assert result is not None, f"valid login attempt {attempt} was refused"
        token, user = result
        assert auth.session(path, token)["user_id"] == user["user_id"] == USERNAME
    assert counts(path) == {}


def test_success_preserves_previous_failures_and_account_limit(tmp_path):
    path = tmp_path / "logins.sqlite3"
    provision(path)
    for _ in range(9):
        assert auth.login(path, USERNAME, WRONG, ADDRESS) is None
    assert auth.login(path, USERNAME, PASSWORD, ADDRESS) is not None
    assert counts(path) == {bucket("user", USERNAME): 9, bucket("ip", ADDRESS): 9}

    assert auth.login(path, USERNAME, WRONG, "192.0.2.11") is None
    assert auth.login(path, USERNAME, PASSWORD, "192.0.2.12") is None
    assert counts(path)[bucket("user", USERNAME)] == 10


def test_success_preserves_source_failures_across_accounts(tmp_path):
    path = tmp_path / "logins.sqlite3"
    provision(path)
    for attempt in range(49):
        assert auth.login(path, f"missing-user-{attempt}", WRONG, ADDRESS) is None
    assert auth.login(path, USERNAME, PASSWORD, ADDRESS) is not None
    assert counts(path)[bucket("ip", ADDRESS)] == 49

    assert auth.login(path, "another-missing-user", WRONG, ADDRESS) is None
    assert auth.login(path, USERNAME, PASSWORD, ADDRESS) is None
    assert counts(path)[bucket("ip", ADDRESS)] == 50
    assert auth.login(path, USERNAME, PASSWORD, "192.0.2.12") is not None


def test_concurrent_failures_still_limit_password_verifications(tmp_path, monkeypatch):
    path = tmp_path / "logins.sqlite3"
    provision(path)
    start = Barrier(12)
    lock = Lock()
    actual_hash = hashlib.pbkdf2_hmac
    hashes = 0

    def count_hash(*args, **kwargs):
        nonlocal hashes
        with lock:
            hashes += 1
        return actual_hash(*args, **kwargs)

    def attempt(_):
        start.wait(timeout=10)
        return auth.login(path, USERNAME, WRONG, ADDRESS)

    monkeypatch.setattr(auth.hashlib, "pbkdf2_hmac", count_hash)
    with ThreadPoolExecutor(max_workers=12) as executor:
        assert list(executor.map(attempt, range(12))) == [None] * 12
    assert hashes == 10
    assert counts(path) == {bucket("user", USERNAME): 10, bucket("ip", ADDRESS): 10}


def test_finishing_success_does_not_refund_a_new_window(tmp_path, monkeypatch):
    path = tmp_path / "logins.sqlite3"
    provision(path)
    clock = SimpleNamespace(now=10_000)
    monkeypatch.setattr(auth, "time", SimpleNamespace(time=lambda: clock.now))
    actual_hash = hashlib.pbkdf2_hmac

    def expire_reservation_while_hashing(*args, **kwargs):
        # A new failure opens a new window before the original success finishes.
        monkeypatch.setattr(auth.hashlib, "pbkdf2_hmac", actual_hash)
        clock.now += 901
        assert auth.login(path, USERNAME, WRONG, ADDRESS) is None
        return actual_hash(*args, **kwargs)

    monkeypatch.setattr(auth.hashlib, "pbkdf2_hmac", expire_reservation_while_hashing)
    assert auth.login(path, USERNAME, PASSWORD, ADDRESS) is not None
    assert counts(path) == {bucket("user", USERNAME): 1, bucket("ip", ADDRESS): 1}


def test_existing_sqlite_failure_window_is_preserved(tmp_path, monkeypatch):
    path = tmp_path / "logins.sqlite3"
    provision(path)
    clock = SimpleNamespace(now=10_000)
    monkeypatch.setattr(auth, "time", SimpleNamespace(time=lambda: clock.now))
    with auth.connection(path) as db:
        db.execute("INSERT INTO login_attempts VALUES (?, 10, ?)",
                   (bucket("user", USERNAME), clock.now))
    auth.initialize(path)

    assert auth.login(path, USERNAME, PASSWORD, ADDRESS) is None
    clock.now += 901
    assert auth.login(path, USERNAME, PASSWORD, ADDRESS) is not None
    assert counts(path) == {}
