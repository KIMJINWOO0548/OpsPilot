"""Start the unpacked OpsPilot-X portfolio bundle on Windows."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from http.client import HTTPConnection, HTTPException
import json
import msvcrt
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time


_PROFILE_MARKER = "OpsPilot-X portable synthetic profile, version 1\n"
_ACCOUNTS = {"author": ("demo-author", "engineer"), "reviewer": ("demo-reviewer", "approver")}
_MODELS = (
    ("chat", "qwen2.5-0.5b-instruct-q4_k_m.gguf", "/v1/chat/completions", 4096, ()),
    ("embed", "Qwen3-Embedding-0.6B-Q8_0.gguf", "/v1/embeddings", 8192,
     ("--embedding", "--pooling", "last", "-b", "4096", "-ub", "4096")),
)


def _owned_file(path: Path) -> bool:
    return path.is_file() and path.resolve() == path and path.stat().st_nlink == 1


@contextmanager
def _launch_lock(bundle: Path):
    path = bundle / ".opspilot-portfolio-lock"
    try:
        with path.open("xb"):
            pass
    except FileExistsError:
        if not _owned_file(path):
            raise RuntimeError("The bundle's launch lock is not a regular local file.") from None
    with path.open("r+b") as lock:
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("This copy of OpsPilot-X is already running.") from None
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def _prepare(bundle: Path) -> Path:
    profile = bundle / "demo-data"
    if profile.exists() or profile.is_symlink():
        marker = profile / "PORTFOLIO-PROFILE"
        database = profile / "opspilot.sqlite3"
        credentials = profile / "credentials.json"
        if (not profile.is_dir() or profile.resolve() != profile
                or not all(_owned_file(path) for path in (marker, database, credentials))
                or marker.read_text(encoding="utf-8") != _PROFILE_MARKER):
            raise RuntimeError("The existing demo-data folder cannot be used. Unpack a clean copy.")
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = profile / (database.name + suffix)
            if (sidecar.exists() or sidecar.is_symlink()) and not _owned_file(sidecar):
                raise RuntimeError("The existing demo database has an unsafe sidecar file.")
        try:
            existing = json.loads(credentials.read_text(encoding="utf-8"))
            if any(existing[name]["username"] != username
                   or not isinstance(existing[name]["password"], str)
                   or len(existing[name]["password"]) < 12 for name, (username, _) in _ACCOUNTS.items()):
                raise ValueError("Invalid demo credentials")
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("Demo credentials are unavailable. Unpack a clean copy.") from None
        return profile

    from opspilot_x.auth import create_user

    with TemporaryDirectory(prefix=".opspilot-profile-", dir=bundle) as scratch:
        staged = Path(scratch) / "demo-data"
        staged.mkdir()
        accounts = {}
        for name, (username, role) in _ACCOUNTS.items():
            password = secrets.token_urlsafe(24)
            create_user(staged / "opspilot.sqlite3", username=username, password=password,
                        tenant="demo", team="team_a", role=role)
            accounts[name] = {"username": username, "password": password}
        (staged / "credentials.json").write_text(json.dumps(accounts, indent=2) + "\n", encoding="utf-8")
        (staged / "PORTFOLIO-PROFILE").write_text(_PROFILE_MARKER, encoding="utf-8")
        staged.rename(profile)
    return profile


def _local_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _ready(port: int, protected_route: str) -> bool:
    connection = HTTPConnection("127.0.0.1", port, timeout=0.5)
    try:
        connection.request("GET", "/health", headers={"Connection": "close"})
        with connection.getresponse() as response:
            if response.status != 200 or json.loads(response.read(1024)) != {"status": "ok"}:
                return False
        connection.request("POST", protected_route, body=b"{}", headers={
            "Content-Type": "application/json", "Connection": "close",
        })
        with connection.getresponse() as response:
            if response.status != 401:
                raise RuntimeError("A model service did not require its launch key.")
        return True
    except (OSError, HTTPException, ValueError):
        return False
    finally:
        connection.close()


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _start_model(server: Path, profile: Path, asset, key_file: Path, env: dict[str, str]):
    kind, model, route, context, options = asset
    log_path = profile / f"model-{kind}.log"
    if (log_path.exists() or log_path.is_symlink()) and not _owned_file(log_path):
        raise RuntimeError("A model log points outside the demo profile.")
    deadline = time.monotonic() + 75
    for _ in range(2):
        port = _local_port()
        with log_path.open("wb") as log:
            process = subprocess.Popen([
                str(server), "-m", str(server.parent.parent / model),
                "--host", "127.0.0.1", "--port", str(port), "--alias", f"opspilot-{kind}",
                "--api-key-file", str(key_file), "--cors-origins", "http://127.0.0.1",
                "--no-webui", "--no-agent", "--no-slots",
                "-ngl", "0", "-t", "4", "-c", str(context), "-np", "1", *options,
            ], cwd=server.parent, env=env, stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            while process.poll() is None and time.monotonic() < deadline:
                if _ready(port, route):
                    return port, process
                time.sleep(0.2)
        except BaseException:
            _stop(process)
            raise
        _stop(process)
        with log_path.open("rb") as log:
            if b"couldn't bind HTTP server socket" not in log.read(65536):
                break
    raise RuntimeError(f"The local {kind} model did not start. See demo-data/model-{kind}.log.")


def _run(bundle: Path, profile: Path) -> int:
    runtime = bundle / "runtime"
    server = runtime / "llama" / "llama-server.exe"
    app = bundle / "opspilot_review_windows.exe"
    if not all(path.is_file() for path in (
        server, app, bundle / "backend" / "web" / "dist" / "index.html",
        *(runtime / model[1] for model in _MODELS),
    )):
        raise RuntimeError("The bundle is incomplete. Extract all files before starting.")
    api_key = secrets.token_hex(32)
    model_env = {
        name: value for name, value in os.environ.items()
        if not name.upper().startswith(("LLAMA_", "HF_", "HUGGINGFACE_"))
    }
    with TemporaryDirectory(prefix="opspilot-model-key-") as scratch:
        key_file = Path(scratch) / "model-key.txt"
        key_file.write_text(api_key + "\n", encoding="ascii")
        processes = []
        try:
            print("Starting two local model services...", flush=True)
            ports = []
            for asset in _MODELS:
                port, process = _start_model(server, profile, asset, key_file, model_env)
                processes.append(process)
                ports.append(port)

            print(f"Demo sign-ins: {profile / 'credentials.json'}", flush=True)
            app_env = os.environ.copy()
            app_env.update(
                OPSPILOT_CHAT_PORT=str(ports[0]),
                OPSPILOT_EMBED_PORT=str(ports[1]),
                OPSPILOT_MODEL_KEY=api_key,
            )
            ui = subprocess.Popen([
                str(app), "--bundle", str(bundle), "--data-dir", str(profile),
                "--appearance-dir", str(profile),
            ], cwd=bundle, env=app_env)
            processes.append(ui)
            return ui.wait()
        finally:
            for process in reversed(processes):
                _stop(process)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", help="Seed or validate the synthetic demo profile")
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    try:
        with _launch_lock(bundle):
            profile = _prepare(bundle)
            if args.prepare:
                print(json.dumps({"profile": str(profile), "credentials": str(profile / "credentials.json")}))
                return 0
            return _run(bundle, profile)
    except (OSError, RuntimeError) as error:
        print(f"OpsPilot-X could not start: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
