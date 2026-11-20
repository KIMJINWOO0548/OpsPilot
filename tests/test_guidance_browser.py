"""Check the built console with actual ASGI detail payloads and controlled delivery order."""
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from opspilot_x.api import create_app
from conftest import login
from test_draft_handover_acceptance import case as case_fixture
from test_draft_handover_acceptance import current_request, decision, new_proposal

# Register the shared pytest fixture in this module without shadowing its import.
case = case_fixture


def test_filtered_approval_keeps_evidence_and_result_in_the_workspace(case, monkeypatch):
    if os.getenv('OPSPILOT_GUIDANCE_BROWSER') != '1':
        pytest.skip('Opt-in Chrome and built local web console')
    pw = pytest.importorskip('playwright.sync_api')
    path, _ = case
    monkeypatch.setenv('OPSPILOT_WEB_DIR', str(Path(__file__).resolve().parents[1] / 'web'))
    with TestClient(create_app(path)) as api, pw.sync_playwright() as runtime:
        login(api, 'engineer-1')
        endpoint, draft = new_proposal(api)
        login(api, 'approver-1')
        browser = runtime.chromium.launch(channel='chrome')
        try:
            page = browser.new_page(viewport={'width': 1186, 'height': 783})

            def dispatch(route):
                request = route.request
                parts = urlsplit(request.url)
                url = parts.path + ('?' + parts.query if parts.query else '')
                headers = {k: v for k, v in request.headers.items() if k in ('content-type', 'x-csrf-token')}
                result = api.request(request.method, url, headers=headers, content=request.post_data_buffer)
                route.fulfill(status=result.status_code, content_type=result.headers.get('content-type'), body=result.content)

            page.route('http://opspilot.test/**', dispatch)
            page.goto('http://opspilot.test/')
            page.get_by_role('button', name='Approval Inbox', exact=False).click()
            queue = page.get_by_role('combobox', name='승인함 필터')
            queue.select_option('pending')
            row = page.locator('.proposal-list tbody tr').get_by_role('button')
            row.focus()
            page.keyboard.press('Enter')
            pw.expect(row).to_have_attribute('aria-current', 'true')
            evidence = page.locator('.approval-evidence')
            pw.expect(evidence).to_contain_text(draft['citations'][0]['source_id'])
            pw.expect(evidence).to_contain_text(f"v{draft['citations'][0]['source_version']}")
            approve = page.get_by_role('button', name='검토 후 승인')
            pw.expect(approve).to_be_in_viewport()
            approve.focus()
            page.keyboard.press('Enter')
            feedback = page.locator('.approval-feedback')
            pw.expect(feedback).to_contain_text('승인 완료')
            pw.expect(feedback).to_be_focused()
            pw.expect(queue).to_have_value('all')
            pw.expect(page.locator('.proposal-id')).to_have_text(endpoint.split('/')[-1])
            assert api.get(endpoint).json()['state'] == 'APPROVED'
            page.set_viewport_size({'width': 760, 'height': 590})
            page.wait_for_function(
                """() => {
                    const layout = document.querySelector('.approval-layout');
                    return getComputedStyle(layout).gridTemplateColumns.split(' ').length === 1
                        && document.documentElement.scrollWidth <= innerWidth;
                }"""
            )
        finally:
            browser.close()


def test_overdue_queue_keyboard_and_revocation(case, monkeypatch):
    from contextlib import closing
    import sqlite3

    if os.getenv('OPSPILOT_GUIDANCE_BROWSER') != '1':
        pytest.skip('Opt-in Chrome and built local web console')
    pw = pytest.importorskip('playwright.sync_api')
    path, _ = case
    monkeypatch.setenv('OPSPILOT_WEB_DIR', str(Path(__file__).resolve().parents[1] / 'web'))
    with TestClient(create_app(path)) as api, pw.sync_playwright() as runtime:
        login(api, 'engineer-1')
        request = current_request()
        create = api.post('/api/v1/proposals', json={'request': request, 'review_due_at': '2025-12-01T13:30:00Z'})
        assert create.status_code == 201, create.text
        overdue = create.json()['proposal_id']
        _, no_due = new_proposal(api)
        login(api, 'approver-1')
        browser = runtime.chromium.launch(channel='chrome')
        try:
            page = browser.new_page()
            stale_audit = []
            pending_endpoint = f'/api/v1/proposals/{overdue}/audit'

            def dispatch(route):
                part = urlsplit(route.request.url)
                url = part.path + ('?' + part.query if part.query else '')
                response = api.get(url)
                args = dict(status=response.status_code, content_type=response.headers.get('content-type'), body=response.content)
                if url == pending_endpoint:
                    stale_audit.append((route, args))
                else:
                    route.fulfill(**args)

            page.route('http://opspilot.test/**', dispatch)
            page.goto('http://opspilot.test/')
            page.get_by_role('button', name='Approval Inbox', exact=False).click()
            selector = page.get_by_role('combobox', name='승인함 필터')
            pw.expect(selector).to_be_enabled()
            selector.focus()
            page.keyboard.press('ArrowDown')
            pw.expect(selector).to_have_value('overdue')
            rows = page.locator('.proposal-list tbody tr')
            pw.expect(rows).to_have_count(1)
            pw.expect(rows.first).to_contain_text(overdue[:14])
            pw.expect(rows.first).to_contain_text('검토 기한')

            selector.select_option('unscheduled')
            pw.expect(rows).to_have_count(1)
            pw.expect(rows.first).to_contain_text(no_due['proposal_id'][:14])
            pw.expect(rows.first).to_contain_text('검토 기한 미지정')
            selector.select_option('overdue')
            pw.expect(rows.first).to_contain_text(overdue[:14])
            with page.expect_request(lambda req: urlsplit(req.url).path == pending_endpoint):
                rows.first.get_by_role('button').click()
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("DELETE FROM evidence_acl WHERE role='approver'")
            page.get_by_role('button', name='새로고침', exact=False).click()
            pw.expect(page.locator('.proposal-list')).to_contain_text('조건에 맞는 승인 대기 요청이 없습니다')
            assert len(stale_audit) == 1
            route, args = stale_audit.pop()
            route.fulfill(**args)
            pw.expect(page.locator('.proposal-id')).to_have_count(0)
            pw.expect(page.locator('.proposal-list')).not_to_contain_text('A-103')
        finally:
            browser.close()


def test_approval_guidance_keyboard_and_stale_reads(case, monkeypatch):
    if os.getenv('OPSPILOT_GUIDANCE_BROWSER') != '1':
        pytest.skip('Opt-in Chrome and built local web console')
    pw = pytest.importorskip('playwright.sync_api')
    path, _ = case
    web = Path(__file__).resolve().parents[1] / 'web'
    monkeypatch.setenv('OPSPILOT_WEB_DIR', str(web))
    with TestClient(create_app(path)) as api:
        assert api.get('/health').json()['ui_ready']
        login(api, 'engineer-1')
        old, draft = new_proposal(api)
        new, _ = new_proposal(api)
        login(api, 'approver-1')
        assert decision(api, old, draft['fingerprint']).status_code == 200
        old_receipt = api.post(old + '/execute', json={'simulate_response_loss': True})
        assert old_receipt.json()['state'] == 'UNKNOWN_RECONCILE'
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(channel='chrome')
            try:
                page = browser.new_page()
                held = []
                hold = False
                actions = []
                def dispatch(route):
                    req = route.request
                    path = urlsplit(req.url).path
                    headers = {k:v for k,v in req.headers.items() if k in ('content-type','x-csrf-token')}
                    response = api.request(req.method, path, headers=headers, content=req.post_data_buffer)
                    args = dict(status=response.status_code, content_type=response.headers.get('content-type'), body=response.content)
                    if req.method == 'POST':
                        actions.append(path)
                    if hold and path == old:
                        held.append((route,args))
                    else:
                        route.fulfill(**args)
                page.route('http://opspilot.test/**', dispatch)
                page.goto('http://opspilot.test/')
                page.get_by_role('button', name='Approval Inbox', exact=False).click()
                def select(proposal):
                    row = page.locator('.proposal-list tr').filter(has_text=proposal.split('/')[-1][:14])
                    row.get_by_role('button').click()
                select(old)
                reconcile = page.get_by_role('button', name='영수증 확인으로 복구', exact=False)
                pw.expect(reconcile).to_be_enabled()
                reconcile.focus()
                page.keyboard.press('Enter')
                pw.expect(page.locator('.receipt .hash')).to_be_visible()
                assert actions == [old + '/reconcile']
                hold = True
                with page.expect_request(lambda req: urlsplit(req.url).path == old):
                    select(old)
                select(new)
                pw.expect(page.locator('.proposal-id')).to_have_text(new.split('/')[-1])
                assert len(held) == 1
                route,args = held.pop()
                route.fulfill(**args)
                pw.expect(page.locator('.proposal-id')).to_have_text(new.split('/')[-1])
                with page.expect_request(lambda req: urlsplit(req.url).path == old):
                    select(old)
                page.get_by_role('button', name='로그아웃').click()
                pw.expect(page.locator('#username')).to_be_visible()
                assert len(held) == 1
                route,args = held.pop()
                route.fulfill(**args)
                pw.expect(page.locator('.proposal-detail')).to_have_count(0)
                assert not any(url.endswith('/execute') for url in actions)
            finally:
                browser.close()

def test_redacted_detail_discards_older_audit_and_list(case, monkeypatch):
    from contextlib import closing
    import sqlite3
    if os.getenv('OPSPILOT_GUIDANCE_BROWSER') != '1':
        pytest.skip('Opt-in Chrome and built local web console')
    pw = pytest.importorskip('playwright.sync_api')
    path, _ = case
    monkeypatch.setenv('OPSPILOT_WEB_DIR', str(Path(__file__).resolve().parents[1] / 'web'))
    with TestClient(create_app(path)) as api, pw.sync_playwright() as runtime:
        login(api, 'engineer-1')
        endpoint, draft = new_proposal(api)
        login(api, 'approver-1')
        assert decision(api, endpoint, draft['fingerprint']).status_code == 200
        listing = '/api/v1/proposals'
        old = {url:api.get(url).json() for url in (listing, endpoint+'/audit')}
        approved = next(event for event in old[endpoint+'/audit']['items'] if event['kind']=='APPROVED')
        original = approved['approved_documents'][0]
        asset = old[listing]['items'][0]['asset_id']
        pending = {}
        wait_for_stale = False
        browser = runtime.chromium.launch(channel='chrome')
        try:
            page = browser.new_page()
            def dispatch(route):
                req = route.request
                url = urlsplit(req.url).path
                if wait_for_stale and url in old:
                    pending[url] = route
                else:
                    resp = api.get(url)
                    route.fulfill(status=resp.status_code, content_type=resp.headers.get('content-type'), body=resp.content)
            page.route('http://opspilot.test/**', dispatch)
            page.goto('http://opspilot.test/')
            page.get_by_role('button', name='Approval Inbox', exact=False).click()
            page.locator('.proposal-link').click()
            pw.expect(page.locator('.audit-list')).to_contain_text(original['evidence_id'])
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("DELETE FROM evidence_acl WHERE evidence_id=? AND role='approver'", (original['evidence_id'],))
            wait_for_stale = True
            with page.expect_response(lambda r:urlsplit(r.url).path == endpoint) as fresh:
                page.get_by_role('button', name='상태 조회', exact=False).click()
            assert 'asset_id' not in fresh.value.json()
            page.wait_for_function("document.querySelector('.proposal-detail .proposal-id') === null")
            pw.expect(page.locator('.proposal-list')).not_to_contain_text(asset)
            assert set(pending) == set(old)
            pending[endpoint+'/audit'].fulfill(json=old[endpoint+'/audit'])
            pw.expect(page.locator('.proposal-detail .proposal-id')).to_be_visible()
            pending[listing].fulfill(json=old[listing])
            pw.expect(page.locator('.message.loading')).to_have_count(0)
            assert original['evidence_id'] not in page.locator('.approval-layout').text_content()
            assert original['text'] not in page.locator('.approval-layout').text_content()
            assert asset not in page.locator('.proposal-list').text_content()
            assert 'engineer-1' not in page.locator('.approval-layout').text_content()
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("INSERT INTO evidence_acl VALUES (?, 'approver')", (original['evidence_id'],))
            wait_for_stale = False
            page.get_by_role('button', name='상태 조회', exact=False).click()
            pw.expect(page.locator('.audit-list')).to_contain_text(original['evidence_id'])
            pw.expect(page.locator('.proposal-link')).to_contain_text(asset)
        finally:
            browser.close()
