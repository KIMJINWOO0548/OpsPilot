"""Typed data contracts, intentionally separate from any LLM or framework."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Status = Literal["SUPPORTED", "CONFLICT", "INSUFFICIENT", "STALE"]


class Actor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=80)
    tenant: str = Field(min_length=1, max_length=80)
    team: str = Field(min_length=1, max_length=80)
    role: Literal["viewer", "engineer", "approver"]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    tenant: str
    team: str
    readable_roles: list[str]
    asset_id: str
    claim_key: str
    value: str
    authority: Literal["approved_sop", "incident_note", "telemetry"]
    source_id: str
    source_version: str
    checksum: str
    valid_from: datetime
    valid_to: datetime | None = None
    recorded_at: datetime
    supersedes: list[str] = Field(default_factory=list)
    locator: str
    text: str

    @field_validator("valid_from", "valid_to", "recorded_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("all timestamps must have timezone information")
        return value


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: Actor
    asset_id: str = Field(min_length=1, max_length=80)
    claim_key: str = "inspection_priority"
    effective_at: datetime
    known_as_of: datetime

    @field_validator("effective_at", "known_as_of")
    @classmethod
    def require_tz(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must include an offset or Z")
        return value


class Citation(BaseModel):
    evidence_id: str
    source_id: str
    source_version: str
    locator: str
    checksum: str


class Analysis(BaseModel):
    state: Status
    recommended_action: str | None
    reason: str
    citations: list[Citation]
    effective_at: datetime
    known_as_of: datetime
    # This report contains authorized sources only. Never include hidden source IDs.


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: Actor
    asset_id: str = Field(min_length=1, max_length=80)
    claim_key: str = "inspection_priority"
    effective_at: datetime
    before_known_as_of: datetime
    after_known_as_of: datetime

    @field_validator("effective_at", "before_known_as_of", "after_known_as_of")
    @classmethod
    def require_tz(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include an offset or Z")
        return value

    @model_validator(mode="after")
    def ordered_observations(self):
        if self.before_known_as_of > self.after_known_as_of:
            raise ValueError("before_known_as_of must not be after after_known_as_of")
        return self


class CitationChanges(BaseModel):
    state_changed: bool
    action_changed: bool
    added_citations: list[Citation]
    removed_citations: list[Citation]


class AnalysisComparison(BaseModel):
    before: Analysis
    after: Analysis
    changed: bool
    changes: CitationChanges


class DecisionRequest(BaseModel):
    actor: Actor
    decision: Literal["approve", "reject"]
    expected_hash: str = Field(min_length=64, max_length=64)


class ExecuteRequest(BaseModel):
    actor: Actor
    simulate_response_loss: bool = False
