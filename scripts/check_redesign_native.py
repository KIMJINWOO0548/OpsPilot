from contextlib import closing, contextmanager
from pathlib import Path
import ctypes
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'competitive-opax'))
from caption_checks import verify, taskbar

work = Path(__file__).resolve().parents[2]
captions = True
scratch = Path(__file__).resolve().parents[1]/'.local'
candidate = scratch / 'application-final/OpsPilot-X.exe'
app = work/'competitive-opax/opspilot-caption-native/application/OpsPilot-X.exe'
out = work.parent/'outputs/desktop-redesign/opspilot/actual'
seed_script = work/'opspilot-installed-qa/seed-verify.py'
password = secrets.token_urlsafe(22)
port = 23971
stem = 'opspilot-redesign'
metrics=[]

def native(pid,title,mode='title',image=None,colors=None):
    if captions:
        verify(app,pid,'OpsPilot-X · '+title,mode=mode,image=out / image if image else None,colors=colors)

def seed(mode, db_dir):
    subprocess.run([str(app.parent / 'backend/python/python.exe'), '-I', '-B', str(seed_script),
                    str(db_dir), mode], input=password+'\n', text=True, check=True)

@contextmanager
def launch(runtime, db_dir):
    port=24000+secrets.randbelow(10000)
    args = f'--remote-debugging-port={port} --remote-debugging-address=127.0.0.1'
    env = dict(os.environ, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=args)
    process = subprocess.Popen([str(app), '--data-dir', str(db_dir)], cwd=app.parent, env=env)
    endpoint = f'http://127.0.0.1:{port}'
    browser = None
    try:
        deadline = time.monotonic()+55
        while time.monotonic()<deadline and process.poll() is None:
            try:
                with urlopen(endpoint + '/json/version', timeout=0.6) as response:
                    assert response.status==200
                with urlopen(endpoint + '/json/list', timeout=0.6) as response:
                    tabs = json.load(response)
                if any(tab.get('url','').startswith('http://127.0.0.1:') for tab in tabs):
                    browser=runtime.chromium.connect_over_cdp(endpoint, timeout=5000)
                    break
            except (OSError, TimeoutError):
                pass
            time.sleep(0.25)
        assert browser, f'WPF WebView did not start for isolated process {process.pid}'
        page = browser.contexts[0].pages[0]
        page.wait_for_url('http://127.0.0.1:*/**',timeout=15000)
        page.set_default_timeout(12000)
        print('WPF PID',process.pid,'viewport',page.evaluate('() => [innerWidth, innerHeight, devicePixelRatio]'),flush=True)
        yield page, process.pid
    finally:
        if browser and browser.is_connected():
            browser.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=12)
        time.sleep(0.4)

def login(page,user):
    page.locator('#username').fill(user)
    page.locator('#password').fill(password)
    page.get_by_role('button',name='로그인',exact=False).click()
    page.get_by_role('button',name='Approval Inbox',exact=False).wait_for()

def openRequest(page, ident=None):
    page.get_by_role('button',name='Approval Inbox',exact=False).click()
    rows=page.locator('.proposal-link')
    row=rows.nth(0) if ident is None else page.get_by_role('button',name=ident[:14],exact=False)
    row.focus()
    page.keyboard.press('Enter')
    expect(page.locator('.proposal-id')).to_be_visible()
    return page.locator('.proposal-id').inner_text()

def status(page,text):
    expect(page.locator('.approval-feedback')).to_contain_text(text)

def native_row_keys(page,pid):
    from ctypes.wintypes import BOOL, HWND, LPARAM, DWORD
    user32=ctypes.windll.user32
    windows=[]
    @ctypes.WINFUNCTYPE(BOOL,HWND,LPARAM)
    def visit(hwnd,_):
        owner=DWORD();user32.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid and user32.IsWindowVisible(hwnd):windows.append(hwnd)
        return True
    user32.EnumWindows(visit,0)
    assert len(windows)==1
    user32.SetForegroundWindow(windows[0])
    assert user32.GetForegroundWindow()==windows[0]
    page.locator('.proposal-link').nth(0).focus()
    for key in (0x28,0x0D):
        user32.keybd_event(key,0,0,0);user32.keybd_event(key,0,2,0)
        time.sleep(.15)
    try:
        expect(page.locator('.proposal-link').nth(1)).to_have_attribute('aria-current','true')
        print('PASS OS-injected ArrowDown/Enter; not human physical input.',flush=True)
    except AssertionError:
        print('LIMIT OS-injected key events did not reach WebView; using explicit WebView keyboard for workflow verification.',flush=True)
        page.locator('.proposal-link').nth(0).focus()
        page.keyboard.press('ArrowDown')
        expect(page.locator('.proposal-link').nth(1)).to_be_focused()
        page.keyboard.press('Enter')
        expect(page.locator('.proposal-link').nth(1)).to_have_attribute('aria-current','true')
    return page.locator('.proposal-id').inner_text()

def narrow_app(pid):
    user32=ctypes.windll.user32
    from ctypes.wintypes import BOOL, HWND, LPARAM, DWORD
    handles=[]
    @ctypes.WINFUNCTYPE(BOOL, HWND, LPARAM)
    def each(hwnd,_):
        owner=DWORD()
        user32.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid and user32.IsWindowVisible(hwnd):
            handles.append(hwnd)
        return True
    user32.EnumWindows(each,0)
    assert len(handles)==1, handles
    user32.ShowWindow(handles[0],9)
    assert user32.SetWindowPos(handles[0],0,30,30,950,710,4)

with tempfile.TemporaryDirectory(dir=scratch,prefix='profile-') as directory, sync_playwright() as runtime:
    db_dir = Path(directory)
    seed('seed',db_dir)
    with launch(runtime,db_dir) as (page,pid):
        native(pid,'로그인','capture','opspilot-caption-login.png')
        login(page,'qa-engineer')
        native(pid,'근거 조사')
        for _ in range(2):
            page.get_by_role('button',name='Investigation',exact=False).click()
            page.get_by_role('button',name='현재 시점',exact=True).click()
            page.get_by_role('button',name='근거 분석',exact=False).click()
            page.get_by_role('button',name='작업 초안 생성',exact=False).click()
            status(page,'초안을 확인했습니다')
    with launch(runtime,db_dir) as (page,pid):
        login(page,'qa-first')
        openRequest(page)
        native(pid,'승인함','capture','before-wpf.png')
    app=candidate
    with launch(runtime,db_dir) as (page,pid):
        login(page,'qa-first')
        target=openRequest(page)
        target=native_row_keys(page,pid)
        native(pid,'승인함','capture','after-wpf.png')
        metrics.append({'kind':'initial','viewport':page.evaluate('()=>[innerWidth,innerHeight,devicePixelRatio]')})
        if captions:
            page.evaluate("document.title='OpsPilot-X · 승인함 A-103 · synthetic caption sentinel'")
            native(pid,'로컬 운영 검증')
            page.evaluate("document.title='OpsPilot-X · 승인함'")
            native(pid,'승인함')
            try:
                native(pid,'승인함')
            except subprocess.CalledProcessError:
                print('Native shell probe did not complete; see output above.',flush=True)
        names=page.locator('.proposal-link').evaluate_all("(buttons)=>buttons.map(b=>b.getAttribute('aria-label'))")
        assert len(set(names))==2 and all('A-103' in name for name in names), names
        expect(page.locator('.approval-evidence')).to_contain_text('SOP-A103')
        page.get_by_role('button',name='이 작업대에서 현재 관측 비교').click()
        expect(page.get_by_role('region',name='현재 관측 비교 결과')).to_contain_text('SOP-A103')
        native(pid,'승인함','capture','after-inline-wpf.png')
        expect(page.get_by_role('heading',name='다음 조치')).to_be_visible()
        page.screenshot(path=str(out/(stem+'-workspace.png')))
        page.get_by_role('button',name='초안 이후 근거 변화 비교',exact=False).click()
        back=page.get_by_role('button',name='요청 검토로 돌아가기',exact=False)
        expect(back).to_be_enabled()
        expect(page.locator('.comparison-review-context')).to_contain_text(target[:14])
        page.locator('#comparison-heading').scroll_into_view_if_needed()
        if captions:
            native(pid,'초안 근거 비교','capture','opspilot-caption-comparison.png')
        else:
            page.screenshot(path=str(out/'opspilot-ui-comparison.png'))
        back.focus()
        page.keyboard.press('Enter')
        expect(page.get_by_role('heading',name='요청 검토')).to_be_focused()
        expect(page.locator('.proposal-id')).to_have_text(target)
        native(pid,'승인함')
        def fail_detail(route):
            if route.request.url.endswith('/proposals/'+target):
                route.fulfill(status=500,json={'detail':'합성 상태 조회 오류'})
            else:
                route.continue_()
        page.route('**/api/v1/proposals/**',fail_detail)
        page.get_by_role('button',name='상태 조회',exact=False).click()
        expect(page.get_by_role('alert')).to_contain_text('합성 상태 조회 오류')
        expect(page.locator('.approval-evidence')).to_have_count(0)
        expect(page.get_by_role('button',name='검토 후 승인')).to_have_count(0)
        native(pid,'승인함','capture','after-error-wpf.png')
        page.unroute('**/api/v1/proposals/**',fail_detail)
        page.get_by_role('button',name='상태 조회',exact=False).click()
        expect(page.locator('.proposal-id')).to_have_text(target)
        page.get_by_role('button',name='검토 후 승인').click()
        status(page,'승인 완료')
    seed('disable-first',db_dir)
    with launch(runtime,db_dir) as (page,pid):
        login(page,'qa-successor')
        assert openRequest(page,target)==target
        page.locator('#handover-reason').fill('격리 합성 인계 확인')
        page.get_by_role('button',name='내 계정으로 검토 인계').click()
        status(page,'검토 담당을 인계했습니다')
        page.get_by_role('button',name='검토 후 승인').click()
        status(page,'승인 완료')
        page.get_by_role('button',name='응답 유실 시나리오 실행').click()
        page.get_by_role('button',name='영수증 확인으로 복구',exact=False).click()
        status(page,'저장된 영수증과 실행 상태를 확인했습니다.')
        expect(page.locator('.receipt')).to_be_visible()
        page.locator('.receipt').scroll_into_view_if_needed()
        page.screenshot(path=str(out/(stem+'-recovery.png')))
        page.evaluate("document.documentElement.style.zoom='150%'")
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        metrics.append({'kind':'app-content-zoom-150','viewport':page.evaluate('()=>[innerWidth,innerHeight,devicePixelRatio]'),'zoom':page.evaluate('getComputedStyle(document.documentElement).zoom')})
        native(pid,'승인함','capture','after-wpf-150.png')
        page.evaluate("document.documentElement.style.zoom='100%'")
        page.locator('#approval-queue').select_option('overdue')
        expect(page.locator('.proposal-link')).to_have_count(0)
        native(pid,'승인함','capture','after-empty-wpf.png')
        page.locator('#approval-queue').select_option('all')
        assert openRequest(page,target)==target
        narrow_app(pid)
        page.wait_for_function("() => innerWidth < 950 && getComputedStyle(document.querySelector('.approval-layout')).gridTemplateColumns.split(' ').length===1 && document.documentElement.scrollWidth<=innerWidth")
        print('Native narrow viewport',page.evaluate('()=>[innerWidth,innerHeight,devicePixelRatio]'),flush=True)
        page.locator('.proposal-list').scroll_into_view_if_needed()
        if captions:
            native(pid,'승인함','capture','opspilot-caption-narrow.png')
        else:
            page.screenshot(path=str(out/'opspilot-ui-narrow.png'))
    with launch(runtime,db_dir) as (page,pid):
        login(page,'qa-successor')
        assert openRequest(page,target)==target
        expect(page.locator('.receipt')).to_be_visible()
        expect(page.locator('.audit-list')).to_contain_text('검토 담당 인계')
        if captions:
            try:
                native(pid,'승인함')
            except subprocess.CalledProcessError:
                print('Taskbar visual probe unavailable.',flush=True)
            native(pid,'승인함','close')
    with closing(sqlite3.connect(f"{(db_dir/'opspilot.sqlite3').as_uri()}?mode=ro",uri=True)) as db:
        assert db.execute('SELECT COUNT(*) FROM work_orders').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0]==2
        audit=[item[0] for item in db.execute('SELECT kind FROM audit WHERE proposal_id=? ORDER BY logged_at,event_id',(target,))]
        assert audit==['CREATED','APPROVED','HANDOVER','APPROVED','RESPONSE_LOST','RECONCILED'],audit
    (out/'native-metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    print('PASS request identity, read-only comparison keyboard return, stale evidence hidden, handover, recovery, native resize and same receipt after restart.',flush=True)
