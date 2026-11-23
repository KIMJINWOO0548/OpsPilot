from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
from zipfile import ZipFile, ZIP_DEFLATED
root=Path(__file__).resolve().parents[1]
workspace=root.parents[1]
out=workspace/'outputs/desktop-redesign/opspilot/actual'
app=root/'.local/application-final'
prior=workspace/'outputs/desktop-workflows/competitive/opspilot-windows-caption-x64.zip'
app.mkdir(parents=True)
with ZipFile(prior) as archive:
    manifest=json.loads(archive.read('release-manifest.json'))
    for name,digest in manifest['files'].items():
        data=archive.read(name)
        assert hashlib.sha256(data).hexdigest()==digest,name
        if name.startswith('backend/web/dist/'): continue
        target=app/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
shutil.copytree(root/'web/dist',app/'backend/web/dist')
# Native host and backend are unchanged; verify packaged source matches this candidate.
for path in (root/'src/opspilot_x').rglob('*.py'):
    packaged=app/'backend/python/Lib/site-packages/opspilot_x'/path.relative_to(root/'src/opspilot_x')
    assert path.read_bytes()==packaged.read_bytes(),path
spec=importlib.util.spec_from_file_location('build',root/'scripts/build_desktop.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
manifest=build.write_manifest(app,build.VERSION)
portable=out/'OpsPilot-X-redesign-final-win-x64.zip'
with ZipFile(portable,'x',compression=ZIP_DEFLATED) as archive:
    for path in sorted(app.rglob('*')):
        if path.is_file(): archive.write(path,path.relative_to(app).as_posix())
with ZipFile(portable) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist())==len(manifest['files'])+1
    for name,digest in manifest['files'].items(): assert hashlib.sha256(archive.read(name)).hexdigest()==digest,name
print(json.dumps({'package':str(portable),'files':len(manifest['files']),'sha256':hashlib.sha256(portable.read_bytes()).hexdigest()},indent=2))
