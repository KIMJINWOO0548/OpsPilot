"""Stage a portable OpsPilot Flutter workspace from verified local inputs."""

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "qwen2.5-0.5b-instruct-q4_k_m.gguf": "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db",
    "Qwen3-Embedding-0.6B-Q8_0.gguf": "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439",
    "llama-b12649-bin-win-cpu-x64.zip": "0e2ff97a5ef40de3e4ca910231676c044e0813c54727b2012022a2d2401e1fa9",
}
CRT_FILES = ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
ENTRY_FILES = ("OpsPilot-X.cmd", "OpsPilot-Workspace.cmd", "launch_opspilot.py",
               "README.ko.md", "evidence-template.json")


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def stage(args):
    for name, digest in MODELS.items():
        if sha256(args.models / name) != digest:
            raise ValueError(f"Model or runtime digest mismatch: {name}")
    release_files = ("opspilot_review_windows.exe", "flutter_windows.dll", "data/icudtl.dat", "data/app.so")
    for name in release_files:
        if not (args.release / name).is_file():
            raise FileNotFoundError(f"Missing Flutter release component: {name}")
    backend = args.python_bundle / "backend"
    artifacts = [
        *(args.crt / name for name in CRT_FILES),
        backend / "python/python.exe",
        backend / "web/dist/index.html",
        *(ROOT / "desktop/portfolio" / name for name in ENTRY_FILES),
        *(args.models / name for name in ("LICENSE-llama.cpp.txt", "LICENSE-Qwen-chat.txt", "LICENSE-Qwen-embed.txt")),
    ]
    for path in artifacts:
        if not path.is_file():
            raise FileNotFoundError(path)
    destination = args.destination
    if args.archive.exists():
        raise FileExistsError(args.archive)
    destination.mkdir(parents=True)
    for name in release_files[:2]:
        shutil.copy2(args.release / name, destination)
    shutil.copytree(args.release / "data", destination / "data")
    for name in CRT_FILES:
        shutil.copy2(args.crt / name, destination)
    shutil.copytree(
        backend,
        destination / "backend",
        ignore=shutil.ignore_patterns("__pycache__", "opspilot_x", "opspilot_x-*.dist-info"),
    )
    shutil.copytree(
        ROOT / "src/opspilot_x", destination / "backend/python/Lib/site-packages/opspilot_x",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    licenses = destination / "licenses"
    licenses.mkdir()
    for name in ("PYTHON-LICENSE.txt", "PYTHON-PACKAGES.json"):
        shutil.copy2(args.python_bundle / "licenses" / name, licenses)
    for name in ("LICENSE-llama.cpp.txt", "LICENSE-Qwen-chat.txt", "LICENSE-Qwen-embed.txt"):
        shutil.copy2(args.models / name, licenses)
    shutil.copy2(args.models / "MODEL-CARD-Qwen-embed.md", licenses)
    for name in ENTRY_FILES:
        shutil.copy2(ROOT / "desktop/portfolio" / name, destination)
    runtime = destination / "runtime"
    runtime.mkdir()
    for name in MODELS:
        if name.endswith(".gguf"):
            shutil.copy2(args.models / name, runtime)
    llama = runtime / "llama"
    llama.mkdir()
    # All native binaries come from the same verified official release archive.
    with zipfile.ZipFile(args.models / "llama-b12649-bin-win-cpu-x64.zip") as binary:
        copied = set()
        for entry in binary.infolist():
            name = Path(entry.filename).name
            if not (name.endswith(".dll") or name.lower() == "llama-server.exe" or name.startswith("LICENSE")):
                continue
            with binary.open(entry) as source, (llama / name).open("xb") as target:
                shutil.copyfileobj(source, target)
            copied.add(name)
        if "llama-server.exe" not in copied:
            raise ValueError("Verified native input is missing llama-server.exe")
    for name in CRT_FILES:
        if name not in copied:
            shutil.copy2(args.crt / name, llama)
    payload = sorted(path for path in destination.rglob("*") if path.is_file())
    (destination / "release-manifest.json").write_text(json.dumps({
        "target": "Windows x64",
        "kind": "portable local workspace and separately provisioned demo",
        "file_sha256": {path.relative_to(destination).as_posix(): sha256(path) for path in payload},
        "upstream_model_and_runtime_sha256": MODELS,
    }, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(args.archive, "x", compression=zipfile.ZIP_STORED) as result:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                result.write(path, path.relative_to(destination))
    with zipfile.ZipFile(args.archive) as result:
        bad = result.testzip()
        if bad is not None:
            raise ValueError(f"Portable ZIP member failed CRC: {bad}")
        print(json.dumps({"package": str(args.archive), "files": len(result.infolist()),
                          "bytes": args.archive.stat().st_size, "sha256": sha256(args.archive)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("release", "python-bundle", "crt", "models", "destination", "archive"):
        parser.add_argument("--" + option, type=Path, required=True)
    stage(parser.parse_args())
