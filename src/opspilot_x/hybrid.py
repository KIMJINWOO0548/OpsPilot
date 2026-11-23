"""Bounded hybrid retrieval and read-only model drafts behind the EIE policy."""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .eie import authorized, effective_at, evaluate
from .schema import Analysis, AnalyzeRequest, Citation, Evidence

MAX_CANDIDATES = 64
SOURCE_CHARS = 700
TOP_K = 4
EMBEDDING_BATCH = 16

ModelStatus = Literal[
    "DRAFT_READY",
    "POLICY_BLOCKED",
    "MODEL_UNAVAILABLE",
    "MODEL_REVIEW_REQUIRED",
    "CONTEXT_LIMIT",
]


class ModelUnavailable(RuntimeError):
    """The configured local model could not serve the request."""


class _ProposedCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    evidence_id: str = Field(min_length=1, max_length=120)
    quote: str = Field(min_length=1, max_length=240)


class _ModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: str = Field(min_length=1, max_length=160)
    citations: list[_ProposedCitation] = Field(min_length=1, max_length=TOP_K)


class DraftCitation(Citation):
    quote: str
    quote_start: int


class HybridDraft(BaseModel):
    action: str
    citations: list[DraftCitation]


class HybridAnalysis(BaseModel):
    analysis: Analysis
    model_status: ModelStatus
    draft: HybridDraft | None = None


def _current_evidence(request: AnalyzeRequest, candidates: list[Evidence]) -> list[Evidence]:
    current = [
        record for record in candidates
        if authorized(record, request.actor)
        and record.asset_id == request.asset_id
        and record.claim_key == request.claim_key
        and record.recorded_at <= request.known_as_of
        and effective_at(record, request.effective_at)
    ]
    superseded = {evidence_id for record in current for evidence_id in record.supersedes}
    return [record for record in current if record.evidence_id not in superseded]


def _terms(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def _bm25(query: str, texts: list[str]) -> list[float]:
    words = [Counter(_terms(value)) for value in texts]
    sizes = [sum(counts.values()) for counts in words]
    average_size = sum(sizes) / len(sizes) or 1
    query_terms = set(_terms(query))
    frequency = {term: sum(term in counts for counts in words) for term in query_terms}
    inverse_frequency = {
        term: math.log1p((len(words) - hits + 0.5) / (hits + 0.5))
        for term, hits in frequency.items()
    }
    k1, b = 1.2, 0.75
    return [
        sum(
            inverse_frequency[term] * counts[term] * (k1 + 1)
            / (counts[term] + k1 * (1 - b + b * size / average_size))
            for term in sorted(query_terms.intersection(counts))
        )
        for size, counts in zip(sizes, words, strict=True)
    ]


def _unit_vector(values: list[float], dimensions: int) -> list[float]:
    if (not isinstance(values, list) or len(values) != dimensions
            or not 1 <= dimensions <= 8192):
        raise ModelUnavailable("Unexpected embedding dimensions")
    if any(type(value) not in (int, float) or abs(value) > 1e100
           or not math.isfinite(value) for value in values):
        raise ModelUnavailable("Invalid embedding value")
    norm = math.hypot(*values)
    if not norm:
        raise ModelUnavailable("Zero embedding")
    return [value / norm for value in values]


class HybridRag:
    def __init__(
        self,
        embed: Callable[[list[str]], list[list[float]]],
        generate: Callable[[str, list[dict[str, str]]], dict],
    ):
        self.embed = embed
        self.generate = generate

    def analyze(
        self, request: AnalyzeRequest, candidates: list[Evidence], query: str
    ) -> HybridAnalysis:
        query = query.strip()
        if not query or len(query) > 1000:
            raise ValueError("Query must contain 1 to 1000 characters")
        analysis = evaluate(request, candidates)
        if analysis.state != "SUPPORTED":
            return HybridAnalysis(analysis=analysis, model_status="POLICY_BLOCKED")
        if not analysis.recommended_action:
            return HybridAnalysis(analysis=analysis, model_status="MODEL_REVIEW_REQUIRED")
        current = _current_evidence(request, candidates)
        if len(current) > MAX_CANDIDATES:
            return HybridAnalysis(analysis=analysis, model_status="CONTEXT_LIMIT")
        if any(hashlib.sha256(record.text.encode("utf8")).hexdigest() != record.checksum
               for record in current):
            return HybridAnalysis(analysis=analysis, model_status="MODEL_REVIEW_REQUIRED")

        canonical = {citation.evidence_id: citation for citation in analysis.citations}
        sources = [
            {
                "evidence_id": record.evidence_id,
                "text": record.text[:SOURCE_CHARS],
                "action": record.value if record.evidence_id in canonical else "",
            }
            for record in current
        ]
        try:
            ranked = self._rank(query, sources)
            selected = ranked[:TOP_K]
            if not any(source["action"] for source in selected):
                selected[-1] = next(source for source in ranked if source["action"])
            output = self.generate(query, selected)
        except ModelUnavailable:
            return HybridAnalysis(analysis=analysis, model_status="MODEL_UNAVAILABLE")

        try:
            draft = self._validate(output, selected, analysis, canonical)
        except (ValidationError, ValueError):
            return HybridAnalysis(analysis=analysis, model_status="MODEL_REVIEW_REQUIRED")
        return HybridAnalysis(analysis=analysis, model_status="DRAFT_READY", draft=draft)

    def _rank(self, query: str, sources: list[dict[str, str]]) -> list[dict[str, str]]:
        texts = [source["text"] for source in sources]
        # Empty evidence text carries no retrieval signal, so use its authorized action
        # as the display/index fallback. A returned quote still has to come from text.
        search_instruction = "Instruct: Given a maintenance question, retrieve relevant policy evidence"
        embedding_texts = [f"{search_instruction}\nQuery: {query}"] + [
            text or source["action"] or "[empty evidence]"
            for text, source in zip(texts, sources, strict=True)
        ]
        vectors = []
        for start in range(0, len(embedding_texts), EMBEDDING_BATCH):
            batch = embedding_texts[start:start + EMBEDDING_BATCH]
            result = self.embed(batch)
            if not isinstance(result, list) or len(result) != len(batch):
                raise ModelUnavailable("Unexpected embedding count")
            vectors.extend(result)
        dimensions = len(vectors[0]) if isinstance(vectors[0], list) else 0
        query_vector = _unit_vector(vectors[0], dimensions)
        semantic = [
            sum(q * x for q, x in zip(
                query_vector, _unit_vector(vector, dimensions), strict=True
            ))
            for vector in vectors[1:]
        ]
        lexical = _bm25(query, texts)
        scores = [0.0] * len(sources)
        # Reciprocal rank fusion uses comparable ranks for the two different score scales.
        # Zero lexical scores are absent from that ranking.
        for signals, include_zero in ((semantic, True), (lexical, False)):
            order = sorted(
                range(len(sources)),
                key=lambda index: (-signals[index], sources[index]["evidence_id"]),
            )
            for rank, index in enumerate(order, start=1):
                if include_zero or signals[index] > 0:
                    scores[index] += 1 / (60 + rank)
        return [
            sources[index] for index in sorted(
                range(len(sources)),
                key=lambda index: (-scores[index], sources[index]["evidence_id"]),
            )
        ]

    @staticmethod
    def _validate(
        output: dict,
        sources: list[dict[str, str]],
        analysis: Analysis,
        canonical: dict[str, Citation],
    ) -> HybridDraft:
        proposed = _ModelOutput.model_validate(output)
        if proposed.action != analysis.recommended_action:
            raise ValueError("Draft action differs from the EIE determination")
        presented = {source["evidence_id"]: source["text"] for source in sources}
        citations = []
        used = set()
        for item in proposed.citations:
            if (item.evidence_id in used or item.evidence_id not in canonical
                    or item.evidence_id not in presented or not item.quote.strip()):
                raise ValueError("Unexpected citation")
            offset = presented[item.evidence_id].find(item.quote)
            if offset < 0:
                raise ValueError("Quote does not match the evidence")
            used.add(item.evidence_id)
            citations.append(DraftCitation(
                **canonical[item.evidence_id].model_dump(), quote=item.quote, quote_start=offset
            ))
        return HybridDraft(action=proposed.action, citations=citations)
