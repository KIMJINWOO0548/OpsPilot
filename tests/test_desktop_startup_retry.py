import asyncio
import io
import json
from types import SimpleNamespace

import pytest
import uvicorn

from opspilot_x import desktop_runtime as desktop


def socket_error(code):
    error = OSError("test socket error")
    error.winerror = code
    return error


@pytest.fixture
def boot(monkeypatch):
    state = SimpleNamespace(
        sockets=[], bind_errors=[], loop_errors=[], listen_errors=[], serve_error=None,
        setups=0, loops=0, serving=0, watchers=[], owner_has_closed=False,
    )
    monkeypatch.setattr(desktop, "configure_paths", lambda *_: "test.sqlite3")
    monkeypatch.setattr(desktop.auth, "initialize", lambda _: None)

    def setup(*_):
        state.setups += 1
        return True

    monkeypatch.setattr(desktop, "setup_accounts", setup)

    class Socket:
        def __init__(self, family, type_):
            assert family == desktop.socket.AF_INET and type_ == desktop.socket.SOCK_STREAM
            self.closed = False
            state.sockets.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.closed = True

        def bind(self, address):
            assert address == ("127.0.0.1", 0)
            if state.bind_errors:
                raise state.bind_errors.pop(0)

        def getsockname(self):
            return ("127.0.0.1", 43100 + len(state.sockets))

    class Server:
        def __init__(self, config):
            assert config.host == "127.0.0.1"
            self.started = self.should_exit = False

        async def startup(self, sockets=None):
            assert len(sockets) == 1 and not sockets[0].closed
            if state.listen_errors:
                raise state.listen_errors.pop(0)
            self.started = True

        async def serve(self, sockets=None):
            await self.startup(sockets=sockets)
            state.serving += 1
            if state.serve_error:
                raise state.serve_error

        def run(self, sockets=None):
            with Runner() as runner:
                runner.run(self.serve(sockets=sockets))

    class Runner:
        def __enter__(self):
            state.loops += 1
            if state.loop_errors:
                raise state.loop_errors.pop(0)
            return self

        def __exit__(self, *_):
            pass

        def run(self, coro):
            with pytest.raises(StopIteration):
                coro.send(None)

    class Thread:
        def __init__(self, *, target, daemon, name):
            assert daemon and name == "desktop-parent"
            state.watchers.append(target)

        def start(self):
            if state.owner_has_closed:
                state.watchers[-1]()

    monkeypatch.setattr(desktop.socket, "socket", Socket)
    monkeypatch.setattr(uvicorn, "Server", Server)
    monkeypatch.setattr(asyncio, "Runner", Runner)
    monkeypatch.setattr(desktop.threading, "Thread", Thread)
    return state


def run():
    output = io.StringIO()
    token = "a" * 64
    result = desktop.run("data", "web", io.StringIO(json.dumps({"token": token}) + "\n"), output)
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    return result, events


@pytest.mark.parametrize("boundary", ("bind_errors", "loop_errors", "listen_errors"))
def test_transient_socket_error_reopens_resources_before_ready(boot, boundary, capsys):
    getattr(boot, boundary).extend((socket_error(10014), socket_error(10014)))
    status, events = run()
    assert status == 0
    assert [event["event"] for event in events] == ["ready"]
    assert events[0]["origin"] == "http://127.0.0.1:43103"
    assert len(boot.sockets) == 3 and all(socket.closed for socket in boot.sockets)
    assert boot.setups == boot.serving == len(boot.watchers) == 1
    assert capsys.readouterr().err.splitlines() == [
        "Desktop loopback startup interrupted (WinError 10014). Retrying (2/3).",
        "Desktop loopback startup interrupted (WinError 10014). Retrying (3/3).",
    ]


def test_persistent_socket_error_stops_after_three_attempts(boot):
    boot.loop_errors.extend(socket_error(10014) for _ in range(4))
    with pytest.raises(OSError) as raised:
        run()
    assert raised.value.winerror == 10014
    assert len(boot.sockets) == boot.loops == 3 and all(socket.closed for socket in boot.sockets)
    assert boot.setups == len(boot.watchers) == 1
    assert boot.serving == 0


def test_unexpected_socket_error_is_not_retried(boot):
    boot.bind_errors.append(socket_error(10048))
    with pytest.raises(OSError) as raised:
        run()
    assert raised.value.winerror == 10048
    assert len(boot.sockets) == 1 and boot.sockets[0].closed


def test_socket_error_after_ready_does_not_restart_server(boot):
    boot.serve_error = socket_error(10014)
    with pytest.raises(OSError) as raised:
        run()
    assert raised.value.winerror == 10014
    assert len(boot.sockets) == boot.serving == len(boot.watchers) == 1
    assert boot.sockets[0].closed


def test_parent_eof_before_start_opens_no_listener(boot):
    boot.owner_has_closed = True
    assert run() == (0, [])
    assert not boot.sockets and boot.serving == 0
