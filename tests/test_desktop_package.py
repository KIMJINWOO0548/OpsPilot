import importlib.util
from pathlib import Path


def builder():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'build_desktop.py'
    spec = importlib.util.spec_from_file_location('build_desktop', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_manifest_hashes_only_distribution_files(tmp_path):
    module = builder()
    (tmp_path / 'OpsPilot-X.exe').write_bytes(b'executable')
    manifest = module.write_manifest(tmp_path, '0.3.0-preview.1')
    assert manifest['product'] == 'OpsPilot-X'
    assert manifest['version'] == '0.3.0-preview.1'
    assert len(manifest['files']['OpsPilot-X.exe']) == 64
    assert 'release-manifest.json' not in manifest['files']


def test_release_manifest_refuses_database_and_secret_inputs(tmp_path):
    import pytest

    module = builder()
    (tmp_path / 'opspilot.sqlite3').write_bytes(b'private data')
    with pytest.raises(ValueError, match='Forbidden'):
        module.write_manifest(tmp_path, '0.3.0-preview.1')
    assert not (tmp_path / 'release-manifest.json').exists()


def test_release_manifest_refuses_existing_manifest(tmp_path):
    import pytest

    module = builder()
    original = tmp_path / 'release-manifest.json'
    original.write_text('original')
    with pytest.raises(FileExistsError):
        module.write_manifest(tmp_path, '0.3.0-preview.1')
    assert original.read_text() == 'original'


def test_manifest_accepts_private_build_staging_but_rejects_private_payload(tmp_path):
    import pytest

    module = builder()
    staging = tmp_path / '.local' / 'application'
    staging.mkdir(parents=True)
    (staging / 'OpsPilot-X.exe').write_bytes(b'app')
    assert module.write_manifest(staging, '0.3.0-preview.1')['files']
    private = tmp_path / 'other' / '.local'
    private.mkdir(parents=True)
    (private / 'private.txt').write_text('must not ship')
    with pytest.raises(ValueError, match='Forbidden'):
        module.write_manifest(private.parent, '0.3.0-preview.1')
