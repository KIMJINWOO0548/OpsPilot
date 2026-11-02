"""Build the Windows desktop preview from installed tools and cached dependencies only."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

VERSION = '0.3.0-preview.1'
ROOT = Path(__file__).resolve().parents[1]


def write_manifest(directory: Path, version: str) -> dict:
    target = directory / 'release-manifest.json'
    if target.exists():
        raise FileExistsError(target)
    files = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Forbidden linked package input: {path.name}')
        if not path.is_file():
            continue
        name = path.relative_to(directory).as_posix()
        if (path.suffix.lower() in {'.sqlite3', '.db', '.pyc', '.pdb'}
                or any(part in {'.local', '.venv', '__pycache__', 'node_modules'}
                       for part in path.relative_to(directory).parts)
                or path.name.startswith('.env') or path.name == 'access.json'):
            raise ValueError(f'Forbidden release input: {name}')
        with path.open('rb') as source:
            files[name] = hashlib.file_digest(source, 'sha256').hexdigest()
    manifest = {'product': 'OpsPilot-X', 'version': version, 'files': files}
    with target.open('x', encoding='utf-8') as output:
        json.dump(manifest, output, ensure_ascii=False, indent=2)
        output.write('\n')
    return manifest


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    print(subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def publish(project: str, output: Path, *, payload: Path | None = None) -> None:
    cache = Path.home() / '.nuget' / 'packages'
    properties = ['-p:RuntimeFrameworkVersion=10.0.12', '-p:NuGetAudit=false']
    if payload:
        properties.append(f'-p:PayloadPath={payload}')
    run(['dotnet', 'restore', project, '--runtime', 'win-x64', '--source', str(cache),
         '-p:SelfContained=true', *properties])
    run(['dotnet', 'publish', project, '--configuration', 'Release', '--runtime', 'win-x64',
         '--self-contained', 'true', '--no-restore', '--output', str(output),
         '-p:DebugType=None', '-p:DebugSymbols=false', *properties])


def copy_python(destination: Path, licenses: Path) -> list[dict]:
    base = Path(sys.base_prefix)
    for filename in ('python.exe', 'python3.dll', 'python312.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'):
        shutil.copy2(base / filename, destination / filename)
    shutil.copytree(base / 'DLLs', destination / 'DLLs',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '_tkinter.pyd'))
    shutil.copytree(base / 'Lib', destination / 'Lib',
                    ignore=shutil.ignore_patterns('site-packages', '__pycache__', '*.pyc', 'test', 'tests', 'idlelib', 'tkinter', 'turtledemo', 'ensurepip'))
    shutil.copy2(base / 'LICENSE.txt', licenses / 'PYTHON-LICENSE.txt')
    packages = destination / 'Lib' / 'site-packages'
    packages.mkdir()
    versions = []
    for line in (ROOT / 'requirements-runtime.lock').read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        name, expected = line.split('==')
        distribution = importlib.metadata.distribution(name)
        if distribution.version != expected:
            raise ValueError(f'Runtime version mismatch: {name}')
        notices = []
        for relative in distribution.files or ():
            if '..' in relative.parts or relative.suffix == '.pyc' or '__pycache__' in relative.parts:
                continue
            source = Path(distribution.locate_file(relative)).resolve()
            if not source.is_file():
                raise ValueError(f'Missing installed runtime file: {name}/{relative}')
            target = packages / str(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if any('license' in part.lower() or 'notice' in part.lower() for part in relative.parts):
                notices.append(str(relative))
        if not notices:
            raise ValueError(f'Runtime license file missing: {name}')
        versions.append({'name': name, 'version': expected,
                         'license_expression': distribution.metadata.get('License-Expression'),
                         'notices_in_site_packages': notices})
    shutil.copytree(ROOT / 'src' / 'opspilot_x', packages / 'opspilot_x',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (licenses / 'PYTHON-PACKAGES.json').write_text(json.dumps(versions, indent=2) + '\n', encoding='utf-8')
    return versions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / f'OpsPilot-X-{VERSION}-win-x64')
    args = parser.parse_args()
    output = args.output.resolve()
    if os.name != 'nt' or sys.version_info[:2] != (3, 12):
        parser.error('Build requires installed Windows x64 Python 3.12 and .NET 10 SDK')
    if output.exists():
        parser.error('Output already exists; choose a new release directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Preserve failed build inputs for diagnosis; never delete an existing release.
    staging = Path(tempfile.mkdtemp(prefix='opspilot-desktop-', dir=ROOT / '.local'))
    app = staging / 'application'
    app.mkdir()
    run(['pnpm.cmd', 'build'], cwd=ROOT / 'web')
    publish('desktop/OpsPilot.Desktop/OpsPilot.Desktop.csproj', app)
    licenses = app / 'licenses'
    licenses.mkdir(exist_ok=True)
    python = app / 'backend' / 'python'
    python.mkdir(parents=True)
    packages = copy_python(python, licenses)
    shutil.copytree(ROOT / 'web' / 'dist', app / 'backend' / 'web' / 'dist')
    cache = Path.home() / '.nuget' / 'packages'
    shutil.copy2(cache / 'microsoft.web.webview2' / '1.0.4258.31' / 'LICENSE.txt', licenses / 'WEBVIEW2-SDK-LICENSE.txt')
    shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', licenses / 'PROJECT-NOTICES.md')
    for directory in (cache / 'microsoft.netcore.app.runtime.win-x64' / '10.0.12',
                      cache / 'microsoft.windowsdesktop.app.runtime.win-x64' / '10.0.12'):
        for notice in ('LICENSE.TXT', 'THIRD-PARTY-NOTICES.TXT'):
            source = directory / notice
            if source.is_file():
                shutil.copy2(source, licenses / (directory.parent.name + '-' + notice))
    (app / 'READ-ME.txt').write_text(
        'OpsPilot-X Windows desktop preview ' + VERSION + '\n\n'
        'Run OpsPilot-X.exe. WebView2 Evergreen Runtime is required.\n'
        'No Python, Node.js or Docker developer installation is required.\n'
        'On first run choose engineer and approver accounts; no default password.\n'
        'Local data: %LOCALAPPDATA%/OpsPilot-X (kept after app removal).\n'
        'Synthetic evidence, deterministic rules and mock actions only.\n'
        'Unsigned local preview; Windows socket stability and independent release acceptance remain pending.\n'
        'No public benchmark, LLM, OIDC, or enterprise production acceptance.\n', encoding='utf-8')
    manifest = write_manifest(app, VERSION)
    portable = staging / f'OpsPilot-X-{VERSION}-win-x64.zip'
    with zipfile.ZipFile(portable, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(app.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(app).as_posix())
    setup = staging / 'setup'
    publish('desktop/OpsPilot.Setup/OpsPilot.Setup.csproj', setup, payload=portable)
    output.mkdir()
    shutil.copy2(portable, output / portable.name)
    installer = setup / 'OpsPilot-X-Setup.exe'
    shutil.copy2(installer, output / installer.name)
    report = {'version': VERSION, 'release_acceptance': 'pending', 'source_commit': None,
              'packages': packages, 'application_files': len(manifest['files']),
              'application_directory': str(app), 'artifacts': {}}
    for path in output.iterdir():
        if path.is_file():
            with path.open('rb') as artifact:
                report['artifacts'][path.name] = {'bytes': path.stat().st_size,
                    'sha256': hashlib.file_digest(artifact, 'sha256').hexdigest()}
    (output / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'application_files': len(manifest['files']),
                      'release_acceptance': 'pending'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
