from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, field_validator
import hmac
from . import auth
from .evidence_store import initialize_evidence, authorized_evidence, search_evidence
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from .eie import evaluate
from .comparison import compare_snapshots
from .schema import (Actor, AnalyzeRequest, AnalysisComparison, CompareRequest, Citation,
                     DecisionRequest, ExecuteRequest)


class ProposalGuidance(BaseModel):
    version: Literal[1] = 1
    reason: Literal["NONE", "RECEIPT_AVAILABLE", "OUTCOME_UNKNOWN", "EVIDENCE_UNAVAILABLE", "REVIEW_REQUIRED"]
    actions: list[Literal["VIEW_RECEIPT", "CHECK_RECEIPT", "TAKE_HANDOVER", "REINVESTIGATE"]]
    review_version: int


class ProposalDetail(BaseModel):
    proposal_id: str
    state: str
    review_version: int
    evidence_reviewable: bool
    citations: list[Citation]
    review_context: dict[str, str] | None
    guidance: ProposalGuidance | None = None
    action: str | None = None
    owner_user: str | None = None
    asset_id: str | None = None
    created_at: str | None = None
    decided_by: str | None = None
    assigned_approver: str | None = None
    fingerprint: str | None = None
    receipt_id: str | None = None
    approval_valid: bool | None = None
    handover_allowed: bool | None = None
    review_due_at: str | None = None


def proposal_guidance(state, *, receipt_present, receipt_matches_row, reconciler, handover,
                      evidence_reviewable, approval_is_valid, assigned_elsewhere, review_version):
    actions = []
    reason = "NONE"
    if state == "SUCCEEDED" and receipt_matches_row:
        reason, actions = "RECEIPT_AVAILABLE", ["VIEW_RECEIPT"]
    elif state in ("UNKNOWN_RECONCILE", "SUCCEEDED") or (state == "APPROVED" and receipt_present):
        reason = "OUTCOME_UNKNOWN"
        if reconciler and state in ("UNKNOWN_RECONCILE", "SUCCEEDED"):
            actions.append("CHECK_RECEIPT")
        if handover:
            actions.append("TAKE_HANDOVER")
    elif state in ("PENDING_APPROVAL", "APPROVED", "EXPIRED") and not evidence_reviewable:
        reason, actions = "EVIDENCE_UNAVAILABLE", ["REINVESTIGATE"]
    elif (state == "APPROVED" and not approval_is_valid) or (state == "PENDING_APPROVAL" and assigned_elsewhere):
        reason = "REVIEW_REQUIRED"
        if handover:
            actions.append("TAKE_HANDOVER")
    return ProposalGuidance(reason=reason, actions=actions, review_version=review_version)


class AnalysisInput(AnalyzeRequest):
    actor: Actor | None = None


class ComparisonInput(CompareRequest):
    actor: Actor | None = None


class DecisionInput(DecisionRequest):
    actor: Actor | None = None


class ExecuteInput(ExecuteRequest):
    actor: Actor | None = None


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=1024)


class ProposalRequest(BaseModel):
    request: AnalysisInput
    review_due_at: str | None = None

    @field_validator("review_due_at")
    @classmethod
    def validate_review_due_at(cls, value):
        if value is None:
            return None
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", value) is None:
            raise ValueError("Expected an ISO timestamp with an explicit offset")
        try:
            return queue_timestamp(datetime.fromisoformat(value))
        except (ValueError, OverflowError):
            raise ValueError("Invalid review due timestamp") from None


def queue_timestamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class HandoverInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_hash: str = Field(min_length=64, max_length=64)
    expected_version: int = Field(ge=0, strict=True)
    reason: str = Field(min_length=1, max_length=500)


DRAFT_INTENT_PREFIX = "intent:"


class DraftIntentKey(BaseModel):
    key: str = Field(pattern=r"^intent:[a-f0-9-]{36}$")


def _draft_input(request, review_due_at=None):
    data = request.model_dump(mode="json", exclude={"actor"})
    for field in ("effective_at", "known_as_of"):
        data[field] = getattr(request, field).astimezone(timezone.utc).isoformat()
    if review_due_at is not None:
        data["review_due_at"] = review_due_at
    return data


def _serialize(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(request: AnalyzeRequest, result) -> str:
    payload = {
        "request": request.model_dump(mode="json"),
        "action": result.recommended_action,
        "state": result.state,
        "citations": [c.model_dump() for c in result.citations],
    }
    return hashlib.sha256(_serialize(payload).encode()).hexdigest()


def create_app(db_path: str | Path | None = None) -> FastAPI:
    path = str(db_path or os.getenv("OPSPILOT_DB", "./opspilot_demo.sqlite3"))
    app = FastAPI(title="OpsPilot-X", version="0.2.0")
    auth.initialize(path)
    initialize_evidence(path)
    secure_cookie = os.getenv("OPSPILOT_SECURE_COOKIE", "false").lower() == "true"
    web = Path(os.getenv("OPSPILOT_WEB_DIR", str(Path(__file__).resolve().parents[2] / "web")))
    if (web / "dist" / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web / "dist" / "assets"), name="assets")

    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            expected = str(request.base_url).rstrip("/")
            if (origin and origin != expected) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-origin request denied"}, status_code=403)
            if request.url.path == "/api/v1/auth/login":
                chunks, size = [], 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 8192:
                        return JSONResponse({"detail": "Login body too large"}, status_code=413)
                    chunks.append(chunk)
                request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers["Cache-Control"] = "no-store"
        return response

    def authenticated(request, user):
        if user is None:
            raise HTTPException(401, "Authentication required")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not hmac.compare_digest(request.headers.get("x-csrf-token", "").encode(), user["csrf_token"].encode()):
                raise HTTPException(403, "CSRF token required")
        return Actor(**{k: user[k] for k in ("user_id", "role", "tenant", "team")})

    def principal(request: Request):
        return authenticated(request, auth.session(path, request.cookies.get(auth.COOKIE)))

    def live_actor(db, request, previous):
        actor = authenticated(request, auth.session_in(db, request.cookies.get(auth.COOKIE)))
        if actor != previous:
            raise HTTPException(403, "Account scope or role changed; retry the request")
        return actor

    @app.post("/api/v1/auth/login")
    def login(body: LoginInput, request: Request, response: Response):
        result = auth.login(path, body.username, body.password, request.client.host if request.client else "unknown")
        if result is None:
            raise HTTPException(401, "Invalid credentials or login temporarily unavailable")
        token, user = result
        old = request.cookies.get(auth.COOKIE)
        if old:
            auth.logout(path, old)
        response.set_cookie(auth.COOKIE, token, httponly=True, secure=secure_cookie,
                            samesite="strict", max_age=auth.SESSION_SECONDS, path="/")
        return user

    @app.get("/api/v1/auth/me")
    def me(request: Request, actor: Actor = Depends(principal)):
        return auth.session(path, request.cookies.get(auth.COOKIE))

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, response: Response, actor: Actor = Depends(principal)):
        auth.logout(path, request.cookies[auth.COOKIE])
        response.delete_cookie(auth.COOKIE, path="/", httponly=True, secure=secure_cookie, samesite="strict")
        return {"ok": True}

    def evaluate_authorized(request, *, evidence_connection=None):
        return evaluate(request, seed=authorized_evidence(path, request.actor, asset_id=request.asset_id,
                                                         known_as_of=request.known_as_of,
                                                         connection=evidence_connection))


    @contextmanager
    def connection():
        with closing(sqlite3.connect(path, timeout=8.0, isolation_level=None)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=8000")
            conn.execute("PRAGMA foreign_keys=ON")
            with conn:
                yield conn

    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS proposals(
            id TEXT PRIMARY KEY,
            request_json TEXT NOT NULL,
            action TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            owner_user TEXT NOT NULL,
            tenant TEXT NOT NULL,
            team TEXT NOT NULL,
            state TEXT NOT NULL,
            decided_by TEXT,
            created_at TEXT NOT NULL,
            review_due_at TEXT
        );
        CREATE TABLE IF NOT EXISTS work_orders(
            idempotency_key TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL UNIQUE,
            receipt_id TEXT NOT NULL UNIQUE,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(proposal_id) REFERENCES proposals(id)
        );
        CREATE TABLE IF NOT EXISTS audit(
            event_id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            actor TEXT NOT NULL,
            logged_at TEXT NOT NULL,
            FOREIGN KEY(proposal_id) REFERENCES proposals(id)
        );
        CREATE TABLE IF NOT EXISTS draft_requests(
            tenant TEXT NOT NULL, team TEXT NOT NULL, owner_user TEXT NOT NULL,
            request_key TEXT NOT NULL, input_hash TEXT NOT NULL,
            proposal_id TEXT NOT NULL UNIQUE REFERENCES proposals(id),
            PRIMARY KEY(tenant,team,owner_user,request_key)
        );
        CREATE TABLE IF NOT EXISTS draft_intents(
            tenant TEXT NOT NULL, team TEXT NOT NULL, owner_user TEXT NOT NULL,
            request_key TEXT NOT NULL UNIQUE, request_json TEXT NOT NULL,
            PRIMARY KEY(tenant,team,owner_user)
        );
        CREATE TABLE IF NOT EXISTS proposal_review(
            proposal_id TEXT PRIMARY KEY REFERENCES proposals(id),
            version INTEGER NOT NULL, assignee TEXT, approved_generation INTEGER
        );
        CREATE TABLE IF NOT EXISTS audit_details(
            event_id TEXT PRIMARY KEY REFERENCES audit(event_id), data TEXT NOT NULL
        );
        """)
        db.execute("BEGIN IMMEDIATE")
        if "review_due_at" not in {row["name"] for row in db.execute("PRAGMA table_info(proposals)")}:
            db.execute("ALTER TABLE proposals ADD COLUMN review_due_at TEXT")
        db.commit()

    def clock():
        return datetime.now(timezone.utc).isoformat()

    def _latest_evidence_changed(request: AnalyzeRequest, snapshot, db=None) -> bool:
        now = datetime.now(timezone.utc)
        actual = evaluate_authorized(request.model_copy(update={"effective_at": now, "known_as_of": now}),
                                     evidence_connection=db)
        signature = lambda x: (
            x.state, x.recommended_action,
            [(c.evidence_id, c.source_version, c.checksum) for c in x.citations],
        )
        return signature(snapshot) != signature(actual)

    def row_or_404(db, proposal_id: str):
        row = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Unknown proposal")
        return row

    def eligible_approver(row, actor):
        return (actor.role == "approver" and actor.tenant == row["tenant"]
                and actor.team == row["team"] and actor.user_id != row["owner_user"])

    def authorized_approver(row, actor: Actor):
        if not eligible_approver(row, actor):
            raise HTTPException(403, "Approver role and separation of duty required")

    def log(db, prop_id, kind, actor, details=None):
        event_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO audit VALUES (?,?,?,?,?)",
            (event_id, prop_id, kind, actor, clock()),
        )
        if details is not None:
            db.execute("INSERT INTO audit_details VALUES (?,?)", (event_id, _serialize(details)))

    def review_state(db, proposal_id):
        row = db.execute("SELECT version, assignee, approved_generation FROM proposal_review "
                         "WHERE proposal_id=?", (proposal_id,)).fetchone()
        return tuple(row) if row else (0, None, None)

    def save_review(db, proposal_id, version, assignee, generation):
        db.execute("INSERT INTO proposal_review VALUES (?,?,?,?) ON CONFLICT(proposal_id) "
                   "DO UPDATE SET version=excluded.version, assignee=excluded.assignee, "
                   "approved_generation=excluded.approved_generation",
                   (proposal_id, version, assignee, generation))

    def eligible_generation(db, row, user_id):
        user = db.execute("SELECT session_version FROM users WHERE user_id=? AND tenant=? "
                          "AND team=? AND role='approver' AND disabled=0",
                          (user_id, row["tenant"], row["team"])).fetchone()
        return user[0] if user is not None and user_id != row["owner_user"] else None

    def approval_valid(db, row, generation):
        current = eligible_generation(db, row, row["decided_by"])
        # Legacy approvals predate the stored generation; never accept them after a revocation.
        return current is not None and current == (0 if generation is None else generation)

    def evidence_snapshot(db, row, actor):
        stored = AnalyzeRequest.model_validate_json(row["request_json"])
        request = stored.model_copy(update={"actor": actor})
        snapshot = evaluate_authorized(request, evidence_connection=db)
        matches = row["action"] == snapshot.recommended_action and _fingerprint(stored, snapshot) == row["fingerprint"]
        return stored, request, snapshot, matches

    def require_current_evidence(db, row, actor):
        _, request, snapshot, matches = evidence_snapshot(db, row, actor)
        if not matches or _latest_evidence_changed(request, snapshot, db):
            db.execute("UPDATE proposals SET state='EXPIRED' WHERE id=?", (row["id"],))
            log(db, row["id"], "EVIDENCE_CHANGED", actor.user_id)
            db.commit()
            raise HTTPException(409, "Evidence changed; proposal expired")
        return snapshot

    def operation_key(proposal_id):
        return hashlib.sha256(f"work-order:{proposal_id}:v1".encode()).hexdigest()

    def operation_receipt(db, proposal_id):
        return db.execute("SELECT * FROM work_orders WHERE idempotency_key=? OR proposal_id=?",
                          (operation_key(proposal_id), proposal_id)).fetchone()

    def receipt_matches(receipt, row):
        return (receipt["idempotency_key"] == operation_key(row["id"])
                and receipt["proposal_id"] == row["id"]
                and receipt["action"] == row["action"]
                and bool(receipt["receipt_id"].strip()))

    def receipt_unavailable(db, row, actor):
        # Missing or inconsistent evidence cannot establish that an earlier operation had no effect.
        if row["state"] != "UNKNOWN_RECONCILE":
            db.execute("UPDATE proposals SET state='UNKNOWN_RECONCILE' WHERE id=?", (row["id"],))
            log(db, row["id"], "RECEIPT_UNAVAILABLE", actor.user_id)
            db.commit()
        return {"state": "UNKNOWN_RECONCILE", "receipt_id": None}

    def draft_scope(actor):
        if actor.role != "engineer":
            raise HTTPException(403, "Engineer role required to draft work order")
        return (actor.tenant, actor.team, actor.user_id)

    def draft_intent(db, scope):
        row = db.execute("SELECT request_key,request_json FROM draft_intents WHERE "
                         "tenant=? AND team=? AND owner_user=?", scope).fetchone()
        return (row["request_key"], json.loads(row["request_json"])) if row else None

    def draft_response(intent):
        if intent is None:
            return {"attempt": None}
        key, stored = intent
        request = dict(stored)
        due = request.pop("review_due_at", None)
        attempt = {"key": key, "request": request}
        if due is not None:
            attempt["review_due_at"] = due
        return {"attempt": attempt}

    @app.get("/api/v1/draft-intent")
    def read_draft_intent(http: Request, actor: Actor = Depends(principal)):
        with connection() as db:
            db.execute("BEGIN")
            scope = draft_scope(live_actor(db, http, actor))
            return draft_response(draft_intent(db, scope))

    @app.post("/api/v1/draft-intent")
    def stage_draft_intent(payload: ProposalRequest, http: Request, actor: Actor = Depends(principal)):
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            scope = draft_scope(live_actor(db, http, actor))
            attempt = draft_intent(db, scope)
            if attempt is None:
                attempt = (DRAFT_INTENT_PREFIX + str(uuid.uuid4()), _draft_input(payload.request, payload.review_due_at))
                db.execute("INSERT INTO draft_intents VALUES (?,?,?,?,?)",
                           (*scope, attempt[0], _serialize(attempt[1])))
            db.commit()
            return draft_response(attempt)

    @app.post("/api/v1/draft-intent/clear")
    def clear_draft_intent(body: DraftIntentKey, http: Request, actor: Actor = Depends(principal)):
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            scope = draft_scope(live_actor(db, http, actor))
            db.execute("DELETE FROM draft_intents WHERE tenant=? AND team=? AND owner_user=? "
                       "AND request_key=?", (*scope, body.key))
            db.commit()
        return {"ok": True}

    @app.get("/")
    def home():
        if (web / "dist" / "index.html").is_file():
            return FileResponse(web / "dist" / "index.html")
        return {"ui_ready": False, "detail": "Build the frontend: cd web && npm ci && npm run build"}

    @app.get("/health")
    def health():
        return {"ok": True, "mode": "local-demo-only", "benchmark_verified": False,
                "production_ready": False, "authentication": "server-session", "auth_required": True,
                "ui_ready": (web / "dist" / "index.html").is_file(),
                "remaining_gates": ["G0/G1 research acceptance", "OIDC", "Postgres/outbox", "external security review"]}

    @app.get("/api/v1/demo/scenarios")
    def scenarios(actor: Actor = Depends(principal)):
        return {
            "assets": sorted({item.asset_id for item in authorized_evidence(path, actor, known_as_of=datetime.now(timezone.utc))}),
            "scenarios": ["current-v2", "historical-as-of", "retroactive-correction",
                          "conflicting-sops", "acl-denial", "injection-as-data",
                          "response-loss-reconciliation"],
        }

    @app.post("/api/v1/analysis")
    def analyze(request: AnalysisInput, actor: Actor = Depends(principal)):
        return evaluate_authorized(request.model_copy(update={"actor": actor}))

    @app.post("/api/v1/analysis/compare", response_model=AnalysisComparison)
    def compare(request: ComparisonInput, actor: Actor = Depends(principal)):
        common = {"actor": actor, "asset_id": request.asset_id,
                  "claim_key": request.claim_key, "effective_at": request.effective_at}
        with connection() as db:
            # Both authorized/known-as-of queries see one current ACL/document snapshot.
            # Enforce read-only access; comparison cannot alter a proposal or mock order.
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            before = evaluate_authorized(
                AnalyzeRequest(**common, known_as_of=request.before_known_as_of),
                evidence_connection=db,
            )
            after = evaluate_authorized(
                AnalyzeRequest(**common, known_as_of=request.after_known_as_of),
                evidence_connection=db,
            )
            return compare_snapshots(before, after)

    @app.post("/api/v1/proposals", status_code=201)
    def create_proposal(
        payload: ProposalRequest, http: Request, actor: Actor = Depends(principal),
        request_key: str | None = Header(default=None, alias="Idempotency-Key",
                                         pattern=r"^[A-Za-z0-9._:-]{1,128}$"),
    ):
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = live_actor(db, http, actor)
            owner_scope = draft_scope(actor)
            request = payload.request.model_copy(update={"actor": actor})
            if request_key is not None:
                normalized = _draft_input(request, payload.review_due_at)
                input_hash = hashlib.sha256(_serialize(normalized).encode()).hexdigest()
                scope = (*owner_scope, request_key)
                prior = db.execute("SELECT input_hash,proposal_id FROM draft_requests WHERE "
                                   "tenant=? AND team=? AND owner_user=? AND request_key=?", scope).fetchone()
                if prior:
                    if prior["input_hash"] != input_hash:
                        raise HTTPException(409, "Draft request key was already used for different input")
                    row = row_or_404(db, prior["proposal_id"])
                    readable(row, actor)
                    _, _, snapshot, matches = evidence_snapshot(db, row, actor)
                    return {"proposal_id": row["id"], "state": row["state"], "action": row["action"],
                            "fingerprint": row["fingerprint"], "citations": snapshot.citations if matches else []}
                if request_key.startswith(DRAFT_INTENT_PREFIX):
                    intent = draft_intent(db, owner_scope)
                    if intent is None or intent[0] != request_key:
                        raise HTTPException(409, "Draft intent is no longer active")
                    if intent[1] != normalized:
                        raise HTTPException(409, "Draft request key was staged for different input")
            # Historical analysis cannot authorize a new present-time write.
            now = datetime.now(timezone.utc)
            if any(not 0 <= (now - value).total_seconds() <= 3600
                   for value in (request.effective_at, request.known_as_of)):
                raise HTTPException(422, "Historical analysis is read-only; use current timestamps")
            result = evaluate_authorized(request, evidence_connection=db)
            if result.state != "SUPPORTED":
                raise HTTPException(422, f"Cannot propose for state {result.state}")
            prop_id = str(uuid.uuid4())
            fingerprint = _fingerprint(request, result)
            db.execute(
                "INSERT INTO proposals (id,request_json,action,fingerprint,owner_user,tenant,team,state,decided_by,created_at,review_due_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (prop_id, request.model_dump_json(), result.recommended_action, fingerprint,
                 actor.user_id, actor.tenant, actor.team, "PENDING_APPROVAL", None, clock(), payload.review_due_at),
            )
            if request_key is not None:
                db.execute("INSERT INTO draft_requests VALUES (?,?,?,?,?,?)", (*scope, input_hash, prop_id))
            log(db, prop_id, "CREATED", actor.user_id)
            db.commit()
        return {"proposal_id": prop_id, "state": "PENDING_APPROVAL", "action": result.recommended_action,
                "fingerprint": fingerprint, "citations": result.citations}

    @app.get("/api/v1/proposals/{proposal_id}", response_model=ProposalDetail, response_model_exclude_unset=True)
    def proposal(proposal_id: str, http: Request, actor: Actor = Depends(principal)):
        with connection() as db:
            db.execute("BEGIN")
            actor = live_actor(db, http, actor)
            row = row_or_404(db, proposal_id)
            readable(row, actor)
            receipt = operation_receipt(db, proposal_id)
            stored, request, snapshot, matches = evidence_snapshot(db, row, actor)
            version, assignee, generation = review_state(db, proposal_id)
            reviewable = matches and not _latest_evidence_changed(request, snapshot, db)
            state = row["state"]
            valid = state == "APPROVED" and approval_valid(db, row, generation)
            eligible = eligible_approver(row, actor)
            assigned = assignee or row["decided_by"]
            handover = (eligible and assigned != actor.user_id and state in ("PENDING_APPROVAL", "APPROVED", "UNKNOWN_RECONCILE")
                        and (state == "UNKNOWN_RECONCILE" or receipt is not None or reviewable))
            receipt_ok = receipt is not None and receipt_matches(receipt, row)
            guidance = proposal_guidance(state, receipt_present=receipt is not None, receipt_matches_row=receipt_ok,
                reconciler=eligible and assigned == actor.user_id, handover=handover, evidence_reviewable=reviewable,
                approval_is_valid=valid, assigned_elsewhere=assignee is not None and assignee != actor.user_id, review_version=version)
            result = dict(proposal_id=proposal_id, state=state, review_version=version, guidance=guidance.model_dump(),
                          evidence_reviewable=reviewable, review_context=None, citations=[])
            if state == "SUCCEEDED" and receipt_ok:
                result["receipt_id"] = receipt["receipt_id"]
            if not matches:
                if "TAKE_HANDOVER" in guidance.actions:
                    result.update(fingerprint=row["fingerprint"], handover_allowed=True)
                return result
            result.update(action=row["action"], owner_user=row["owner_user"], asset_id=stored.asset_id,
                created_at=row["created_at"], decided_by=row["decided_by"], assigned_approver=assignee,
                approval_valid=valid, handover_allowed=handover, fingerprint=row["fingerprint"],
                citations=snapshot.citations, receipt_id=receipt["receipt_id"] if state == "SUCCEEDED" and receipt_ok else None)
            if row["review_due_at"] is not None:
                result["review_due_at"] = row["review_due_at"]
            if reviewable:
                result["review_context"] = stored.model_dump(mode="json", include={"claim_key", "effective_at", "known_as_of"})
            return result

    @app.post("/api/v1/proposals/{proposal_id}/decision")
    def decide(proposal_id: str, body: DecisionInput, http: Request, actor: Actor = Depends(principal)):
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = live_actor(db, http, actor)
            row = row_or_404(db, proposal_id)
            readable(row, actor)
            authorized_approver(row, actor)
            version, assignee, _ = review_state(db, proposal_id)
            if body.expected_hash != row["fingerprint"]:
                raise HTTPException(409, "Approval snapshot mismatch")
            if ((assignee is not None or body.decision == "cancel" or body.expected_version is not None)
                    and body.expected_version != version):
                raise HTTPException(409, "Review version changed; refresh the proposal")
            if body.decision == "cancel":
                if row["decided_by"] != actor.user_id:
                    raise HTTPException(403, "Original approving actor required")
                if row["state"] != "APPROVED" or operation_receipt(db, proposal_id):
                    raise HTTPException(409, "Only unexecuted approvals can be canceled")
                new_state = "CANCELLED"
            else:
                if row["state"] != "PENDING_APPROVAL":
                    raise HTTPException(409, "Proposal already decided")
                if assignee is not None and assignee != actor.user_id:
                    raise HTTPException(403, "Assigned approver required")
                snapshot = require_current_evidence(db, row, actor)
                new_state = "APPROVED" if body.decision == "approve" else "REJECTED"
            generation = eligible_generation(db, row, actor.user_id) if new_state == "APPROVED" else None
            db.execute("UPDATE proposals SET state=?, decided_by=? WHERE id=?",
                       (new_state, actor.user_id, proposal_id))
            save_review(db, proposal_id, version + 1, assignee, generation)
            details = {"fingerprint": row["fingerprint"],
                       "citations": [citation.model_dump() for citation in snapshot.citations]} if new_state == "APPROVED" else None
            log(db, proposal_id, new_state, actor.user_id, details)
            db.commit()
            return {"proposal_id": proposal_id, "state": new_state}

    @app.post("/api/v1/proposals/{proposal_id}/handover")
    def handover(proposal_id: str, body: HandoverInput, http: Request, actor: Actor = Depends(principal)):
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = live_actor(db, http, actor)
            row = row_or_404(db, proposal_id)
            readable(row, actor)
            authorized_approver(row, actor)
            version, assignee, generation = review_state(db, proposal_id)
            if body.expected_version != version or body.expected_hash != row["fingerprint"]:
                raise HTTPException(409, "Review snapshot changed; refresh the proposal")
            state = row["state"]
            previous = assignee or row["decided_by"]
            if state not in ("PENDING_APPROVAL", "APPROVED", "UNKNOWN_RECONCILE") or previous == actor.user_id:
                raise HTTPException(409, "Proposal cannot be handed over")
            if state == "UNKNOWN_RECONCILE" or operation_receipt(db, proposal_id):
                new_state = "UNKNOWN_RECONCILE"
            else:
                # A different reviewer without evidence access must not expire another user's draft.
                _, review_request, snapshot, matches = evidence_snapshot(db, row, actor)
                if not matches or _latest_evidence_changed(review_request, snapshot, db):
                    raise HTTPException(409, "Evidence changed or is not reviewable; create a new draft")
                new_state = "PENDING_APPROVAL"
            db.execute("UPDATE proposals SET state=?, decided_by=? WHERE id=?",
                       (new_state, row["decided_by"] if new_state == "UNKNOWN_RECONCILE" else None, proposal_id))
            save_review(db, proposal_id, version + 1, actor.user_id,
                        generation if new_state == "UNKNOWN_RECONCILE" else None)
            log(db, proposal_id, "HANDOVER", actor.user_id, {
                "from_approver": previous, "to_approver": actor.user_id, "reason": body.reason,
                "version": version + 1, "fingerprint": row["fingerprint"],
                "from_state": state, "to_state": new_state,
            })
            db.commit()
            return {"proposal_id": proposal_id, "state": new_state, "review_version": version + 1,
                    "assigned_approver": actor.user_id}

    @app.post("/api/v1/proposals/{proposal_id}/execute")
    def execute(proposal_id: str, body: ExecuteInput, http: Request, actor: Actor = Depends(principal)):
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = live_actor(db, http, actor)
            row = row_or_404(db, proposal_id)
            readable(row, actor)
            authorized_approver(row, actor)
            if row["state"] not in ("APPROVED", "SUCCEEDED", "UNKNOWN_RECONCILE"):
                raise HTTPException(409, "Unapproved or terminal proposal")
            _, assignee, generation = review_state(db, proposal_id)
            if row["decided_by"] != actor.user_id or (assignee is not None and assignee != actor.user_id):
                raise HTTPException(403, "Original approving actor required")
            if row["state"] == "UNKNOWN_RECONCILE":
                return receipt_unavailable(db, row, actor)
            receipt = operation_receipt(db, proposal_id)
            if receipt is not None and not receipt_matches(receipt, row):
                return receipt_unavailable(db, row, actor)
            if receipt is None:
                if row["state"] != "APPROVED":
                    return receipt_unavailable(db, row, actor)
                if not approval_valid(db, row, generation):
                    raise HTTPException(409, "Approval no longer valid; handover and reapproval required")
                require_current_evidence(db, row, actor)
                key = operation_key(proposal_id)
                db.execute("INSERT INTO work_orders VALUES (?,?,?,?,?)",
                           (key, proposal_id, str(uuid.uuid4()), row["action"], clock()))
                receipt = db.execute("SELECT receipt_id FROM work_orders WHERE idempotency_key=?",
                                     (key,)).fetchone()
            if body.simulate_response_loss and row["state"] != "SUCCEEDED":
                # Simulates remote-side committed change with lost success response.
                # Reconciler MUST read receipt; must NOT create a new external request.
                db.execute("UPDATE proposals SET state='UNKNOWN_RECONCILE' WHERE id=?",
                           (proposal_id,))
                log(db, proposal_id, "RESPONSE_LOST", actor.user_id)
                db.commit()
                return {"state": "UNKNOWN_RECONCILE", "receipt_id": None}
            db.execute("UPDATE proposals SET state='SUCCEEDED' WHERE id=?", (proposal_id,))
            log(db, proposal_id, "SUCCEEDED", actor.user_id)
            db.commit()
            return {"state": "SUCCEEDED", "receipt_id": receipt["receipt_id"]}

    @app.post("/api/v1/proposals/{proposal_id}/reconcile")
    def reconcile(proposal_id: str, body: ExecuteInput, http: Request, actor: Actor = Depends(principal)):
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = live_actor(db, http, actor)
            row = row_or_404(db, proposal_id)
            readable(row, actor)
            authorized_approver(row, actor)
            _, assignee, _ = review_state(db, proposal_id)
            if (assignee or row["decided_by"]) != actor.user_id:
                raise HTTPException(403, "Assigned or original approving actor required")
            if row["state"] not in ("UNKNOWN_RECONCILE", "SUCCEEDED"):
                raise HTTPException(409, "Not in reconcilable state")
            receipt = db.execute("SELECT * FROM work_orders WHERE proposal_id=?",
                                 (proposal_id,)).fetchone()
            if receipt and receipt_matches(receipt, row):
                db.execute("UPDATE proposals SET state='SUCCEEDED' WHERE id=?", (proposal_id,))
                log(db, proposal_id, "RECONCILED", actor.user_id)
                db.commit()
                return {"state": "SUCCEEDED", "receipt_id": receipt["receipt_id"]}
            return receipt_unavailable(db, row, actor)

    def readable(row, actor):
        if (actor.tenant != row["tenant"] or actor.team != row["team"]
                or (actor.user_id != row["owner_user"] and actor.role != "approver")):
            raise HTTPException(404, "Unknown proposal")

    @app.get("/api/v1/proposals")
    def proposals(http: Request, actor: Actor = Depends(principal),
                  review_queue: Literal["overdue", "unscheduled"] | None = None):
        if len(http.query_params.getlist("review_queue")) > 1:
            raise HTTPException(422, "Choose one review queue")
        as_of = queue_timestamp(datetime.now(timezone.utc)) if review_queue else None
        with connection() as db:
            db.execute("BEGIN")
            actor = live_actor(db, http, actor)
            query = "SELECT * FROM proposals WHERE tenant=? AND team=? AND (owner_user=? OR ?='approver')"
            params = (actor.tenant, actor.team, actor.user_id, actor.role)
            if review_queue == "overdue":
                query += " AND state='PENDING_APPROVAL' AND review_due_at<? ORDER BY review_due_at,id"
                params += (as_of,)
            elif review_queue == "unscheduled":
                query += " AND state='PENDING_APPROVAL' AND review_due_at IS NULL ORDER BY created_at DESC,id"
            else:
                query += " ORDER BY created_at DESC"
            items = []
            for row in db.execute(query, params):
                item = {"proposal_id": row["id"], "state": row["state"]}
                stored, _, _, matches = evidence_snapshot(db, row, actor)
                if review_queue and not matches:
                    continue
                if matches:
                    item.update(action=row["action"], created_at=row["created_at"], owner_user=row["owner_user"],
                                decided_by=row["decided_by"], asset_id=stored.asset_id, fingerprint=row["fingerprint"])
                    if review_queue:
                        item["review_due_at"] = row["review_due_at"]
                items.append(item)
            return {"items": items, "as_of": as_of} if review_queue else {"items": items}

    @app.get("/api/v1/proposals/{proposal_id}/audit")
    def audit(proposal_id: str, http: Request, actor: Actor = Depends(principal)):
        with connection() as db:
            db.execute("BEGIN")
            actor = live_actor(db, http, actor)
            proposal_row = row_or_404(db, proposal_id)
            readable(proposal_row, actor)
            if not evidence_snapshot(db, proposal_row, actor)[3]:
                return {"items": []}
            visible = {source.evidence_id: source for source in authorized_evidence(path, actor, connection=db)}
            rows = db.execute("SELECT kind,actor,logged_at,data FROM audit "
                              "LEFT JOIN audit_details USING(event_id) WHERE proposal_id=? "
                              "ORDER BY logged_at,audit.rowid", (proposal_id,))
            items = []
            for row in rows:
                item = dict(row)
                data = item.pop("data")
                if data is not None:
                    item["details"] = json.loads(data)
                    citations = item["details"].pop("citations", [])
                    if item["kind"] == "APPROVED":
                        item["approved_documents"] = []
                        for citation in citations:
                            source = visible.get(citation["evidence_id"])
                            if (source is not None and source.source_version == citation["source_version"]
                                    and source.checksum == citation["checksum"]
                                    and hashlib.sha256(source.text.encode()).hexdigest() == citation["checksum"]):
                                item["approved_documents"].append({**citation, "text": source.text})
                items.append(item)
            return {"items": items}

    @app.get("/api/v1/evidence")
    def evidence(q: str = Query("", max_length=1000), asset_id: str | None = Query(None, max_length=80), effective_at: datetime | None = None,
                 known_as_of: datetime | None = None, actor: Actor = Depends(principal)):
        if any(value is not None and value.tzinfo is None for value in (effective_at, known_as_of)):
            raise HTTPException(422, "Timestamps must include timezone")
        return {"items": search_evidence(path, actor, query=q, asset_id=asset_id,
                                         effective_at=effective_at, known_as_of=known_as_of)}

    return app


app = create_app()
