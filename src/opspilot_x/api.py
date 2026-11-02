from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
import hmac
from . import auth
from .evidence_store import initialize_evidence, authorized_evidence, search_evidence
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .eie import evaluate
from .schema import Actor, AnalyzeRequest, DecisionRequest, ExecuteRequest


class AnalysisInput(AnalyzeRequest):
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

    def principal(request: Request):
        user = auth.session(path, request.cookies.get(auth.COOKIE))
        if user is None:
            raise HTTPException(401, "Authentication required")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not hmac.compare_digest(request.headers.get("x-csrf-token", "").encode(), user["csrf_token"].encode()):
                raise HTTPException(403, "CSRF token required")
        return Actor(**{k: user[k] for k in ("user_id", "role", "tenant", "team")})

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

    def evaluate_authorized(request):
        return evaluate(request, seed=authorized_evidence(path, request.actor, asset_id=request.asset_id,
                                                         known_as_of=request.known_as_of))


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
            created_at TEXT NOT NULL
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
        """)

    def clock():
        return datetime.now(timezone.utc).isoformat()

    def _latest_evidence_changed(request: AnalyzeRequest, snapshot) -> bool:
        now = datetime.now(timezone.utc)
        actual = evaluate_authorized(request.model_copy(update={"effective_at": now, "known_as_of": now}))
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

    def authorized_approver(row, actor: Actor):
        if (
            actor.role != "approver"
            or actor.tenant != row["tenant"]
            or actor.team != row["team"]
            or actor.user_id == row["owner_user"]
        ):
            raise HTTPException(403, "Approver role and separation of duty required")

    def log(db, prop_id, kind, actor):
        db.execute(
            "INSERT INTO audit VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), prop_id, kind, actor, clock()),
        )

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

    @app.post("/api/v1/proposals", status_code=201)
    def create_proposal(payload: ProposalRequest, actor: Actor = Depends(principal)):
        payload.request = payload.request.model_copy(update={"actor": actor})
        result = evaluate_authorized(payload.request)
        if result.state != "SUPPORTED":
            raise HTTPException(422, f"Cannot propose for state {result.state}")
        if payload.request.actor.role != "engineer":
            raise HTTPException(403, "Engineer role required to draft work order")
        # Historical analysis cannot authorize a present-time write.
        now = datetime.now(timezone.utc)
        known_age = (now - payload.request.known_as_of).total_seconds()
        effective_age = (now - payload.request.effective_at).total_seconds()
        if not (0 <= known_age <= 3600 and 0 <= effective_age <= 3600):
            raise HTTPException(422, "Historical analysis is read-only; use current timestamps")
        prop_id = str(uuid.uuid4())
        fingerprint = _fingerprint(payload.request, result)
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?,?)",
                (prop_id, payload.request.model_dump_json(), result.recommended_action,
                 fingerprint, payload.request.actor.user_id, payload.request.actor.tenant,
                 payload.request.actor.team, "PENDING_APPROVAL", None, clock()),
            )
            log(db, prop_id, "CREATED", payload.request.actor.user_id)
            db.commit()
        return {"proposal_id": prop_id, "state": "PENDING_APPROVAL", "action": result.recommended_action,
                "fingerprint": fingerprint, "citations": result.citations}

    @app.get("/api/v1/proposals/{proposal_id}")
    def proposal(proposal_id: str, actor: Actor = Depends(principal)):
        with connection() as db:
            row = row_or_404(db, proposal_id)
            readable(row, actor)
            receipt = db.execute(
                "SELECT receipt_id FROM work_orders WHERE proposal_id=?", (proposal_id,)
            ).fetchone()
            stored_request = AnalyzeRequest.model_validate_json(row["request_json"])
            snapshot = evaluate_authorized(stored_request.model_copy(update={"actor": actor}))
            citations = snapshot.citations if _fingerprint(stored_request, snapshot) == row["fingerprint"] else []
            return {"proposal_id": row["id"], "state": row["state"], "action": row["action"],
                    "owner_user": row["owner_user"], "asset_id": stored_request.asset_id,
                    "created_at": row["created_at"], "decided_by": row["decided_by"], "citations": citations,
                    "fingerprint": row["fingerprint"],
                    "receipt_id": receipt["receipt_id"] if receipt else None}

    @app.post("/api/v1/proposals/{proposal_id}/decision")
    def decide(proposal_id: str, body: DecisionInput, actor: Actor = Depends(principal)):
        body = body.model_copy(update={"actor": actor})
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = row_or_404(db, proposal_id)
            readable(row, actor)
            authorized_approver(row, body.actor)
            if row["state"] != "PENDING_APPROVAL":
                raise HTTPException(409, "Proposal already decided")
            if body.expected_hash != row["fingerprint"]:
                raise HTTPException(409, "Approval snapshot mismatch")
            request = AnalyzeRequest.model_validate_json(row["request_json"])
            # Apply caller ACL before retrieval; retain the original request for fingerprint checks.
            review_request = request.model_copy(update={"actor": actor})
            live = evaluate_authorized(review_request)
            if (row["action"] != live.recommended_action
                    or _fingerprint(request, live) != row["fingerprint"]
                    or _latest_evidence_changed(review_request, live)):
                db.execute("UPDATE proposals SET state='EXPIRED' WHERE id=?", (proposal_id,))
                log(db, proposal_id, "EVIDENCE_CHANGED", body.actor.user_id)
                db.commit()
                raise HTTPException(409, "Evidence changed; proposal expired")
            new_state = "APPROVED" if body.decision == "approve" else "REJECTED"
            db.execute("UPDATE proposals SET state=?, decided_by=? WHERE id=?",
                       (new_state, body.actor.user_id, proposal_id))
            log(db, proposal_id, new_state, body.actor.user_id)
            db.commit()
            return {"proposal_id": proposal_id, "state": new_state}

    @app.post("/api/v1/proposals/{proposal_id}/execute")
    def execute(proposal_id: str, body: ExecuteInput, actor: Actor = Depends(principal)):
        body = body.model_copy(update={"actor": actor})
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = row_or_404(db, proposal_id)
            readable(row, actor)
            authorized_approver(row, body.actor)
            if row["state"] not in ("APPROVED", "SUCCEEDED", "UNKNOWN_RECONCILE"):
                raise HTTPException(409, "Unapproved or terminal proposal")
            if row["decided_by"] != body.actor.user_id:
                raise HTTPException(403, "Original approving actor required")
            key = hashlib.sha256(f"work-order:{proposal_id}:v1".encode()).hexdigest()
            receipt = db.execute("SELECT receipt_id FROM work_orders WHERE idempotency_key=?",
                                 (key,)).fetchone()
            if receipt is None:
                request = AnalyzeRequest.model_validate_json(row["request_json"])
                review_request = request.model_copy(update={"actor": actor})
                live = evaluate_authorized(review_request)
                if (row["action"] != live.recommended_action
                    or _fingerprint(request, live) != row["fingerprint"]
                    or _latest_evidence_changed(review_request, live)):
                    db.execute("UPDATE proposals SET state='EXPIRED' WHERE id=?", (proposal_id,))
                    log(db, proposal_id, "EVIDENCE_CHANGED", body.actor.user_id)
                    db.commit()
                    raise HTTPException(409, "Evidence changed; proposal expired")
                db.execute("INSERT INTO work_orders VALUES (?,?,?,?,?)",
                           (key, proposal_id, str(uuid.uuid4()), row["action"], clock()))
                receipt = db.execute("SELECT receipt_id FROM work_orders WHERE idempotency_key=?",
                                     (key,)).fetchone()
            if body.simulate_response_loss and row["state"] != "SUCCEEDED":
                # Simulates remote-side committed change with lost success response.
                # Reconciler MUST read receipt; must NOT create a new external request.
                db.execute("UPDATE proposals SET state='UNKNOWN_RECONCILE' WHERE id=?",
                           (proposal_id,))
                log(db, proposal_id, "RESPONSE_LOST", body.actor.user_id)
                db.commit()
                return {"state": "UNKNOWN_RECONCILE", "receipt_id": None}
            db.execute("UPDATE proposals SET state='SUCCEEDED' WHERE id=?", (proposal_id,))
            log(db, proposal_id, "SUCCEEDED", body.actor.user_id)
            db.commit()
            return {"state": "SUCCEEDED", "receipt_id": receipt["receipt_id"]}

    @app.post("/api/v1/proposals/{proposal_id}/reconcile")
    def reconcile(proposal_id: str, body: ExecuteInput, actor: Actor = Depends(principal)):
        body = body.model_copy(update={"actor": actor})
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = row_or_404(db, proposal_id)
            readable(row, actor)
            authorized_approver(row, body.actor)
            if row["decided_by"] != body.actor.user_id:
                raise HTTPException(403, "Original approving actor required")
            if row["state"] not in ("UNKNOWN_RECONCILE", "SUCCEEDED"):
                raise HTTPException(409, "Not in reconcilable state")
            receipt = db.execute("SELECT receipt_id FROM work_orders WHERE proposal_id=?",
                                 (proposal_id,)).fetchone()
            if receipt:
                db.execute("UPDATE proposals SET state='SUCCEEDED' WHERE id=?", (proposal_id,))
                log(db, proposal_id, "RECONCILED", body.actor.user_id)
                db.commit()
                return {"state": "SUCCEEDED", "receipt_id": receipt["receipt_id"]}
            return {"state": "UNKNOWN_RECONCILE", "receipt_id": None}

    def readable(row, actor):
        if (actor.tenant != row["tenant"] or actor.team != row["team"]
                or (actor.user_id != row["owner_user"] and actor.role != "approver")):
            raise HTTPException(404, "Unknown proposal")

    @app.get("/api/v1/proposals")
    def proposals(actor: Actor = Depends(principal)):
        with connection() as db:
            rows = db.execute("SELECT * FROM proposals WHERE tenant=? AND team=? AND (owner_user=? OR ?='approver') ORDER BY created_at DESC", (actor.tenant, actor.team, actor.user_id, actor.role)).fetchall()
            return {"items": [{"proposal_id": r["id"], "state": r["state"], "action": r["action"],
                               "created_at": r["created_at"], "owner_user": r["owner_user"],
                               "decided_by": r["decided_by"], "asset_id": json.loads(r["request_json"])["asset_id"],
                               "fingerprint": r["fingerprint"]} for r in rows]}

    @app.get("/api/v1/proposals/{proposal_id}/audit")
    def audit(proposal_id: str, actor: Actor = Depends(principal)):
        with connection() as db:
            readable(row_or_404(db, proposal_id), actor)
            return {"items": [dict(row) for row in db.execute("SELECT kind,actor,logged_at FROM audit WHERE proposal_id=? ORDER BY logged_at", (proposal_id,))]}

    @app.get("/api/v1/evidence")
    def evidence(q: str = Query("", max_length=1000), asset_id: str | None = Query(None, max_length=80), effective_at: datetime | None = None,
                 known_as_of: datetime | None = None, actor: Actor = Depends(principal)):
        if any(value is not None and value.tzinfo is None for value in (effective_at, known_as_of)):
            raise HTTPException(422, "Timestamps must include timezone")
        return {"items": search_evidence(path, actor, query=q, asset_id=asset_id,
                                         effective_at=effective_at, known_as_of=known_as_of)}

    return app


app = create_app()
