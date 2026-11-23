"""Bounded hybrid retrieval and read-only model drafts behind the EIE policy."""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Callable, Iterator
from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .eie import authorized, effective_at, evaluate
from .schema import Analysis, AnalyzeRequest, Citation, Evidence

MAX_CANDIDATES = 64
# Input size of the historical prefix-based evaluation arm.
SOURCE_CHARS = 700
TOP_K = 4
EMBEDDING_BATCH = 16
PASSAGE_CHARS = 240
_PASSAGE_OVERLAP = 80
_MAX_AUTHORIZED_CHARS = 256_000
_MAX_PASSAGES = 4_096
_RERANK_PASSAGES = 16
_SENTENCE_BREAK = re.compile(r"(?<=[.!?。！？])(?=\s)|[\r\n]+")
_ACTION_CUE = re.compile(r"\b(?:first|approved instruction|initially)\b|먼저|우선|첫 조치", re.I)


class ModelSource(TypedDict):
    evidence_id: str
    text: str
    action: str
    quote_start: NotRequired[int]

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
    quote: str = Field(min_length=1, max_length=PASSAGE_CHARS)
    quote_start: int | None = Field(default=None, ge=0)


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
    terms = re.findall(r"\w+", text.casefold())
    # Korean word endings differ between a question and instructions.
    for word in re.findall(r"[가-힣]+", text):
        terms.extend("ko:" + word[index:index + 2] for index in range(len(word) - 1))
    return terms


def _sentence_spans(text: str) -> Iterator[tuple[int, int]]:
    if len(text) <= PASSAGE_CHARS:
        yield 0, len(text)
        return
    start = 0
    for boundary in _SENTENCE_BREAK.finditer(text):
        yield start, boundary.start()
        start = boundary.end()
    yield start, len(text)


def _passages(evidence: Evidence) -> Iterator[ModelSource]:
    seen = set()
    for start, end in _sentence_spans(evidence.text):
        while start < end:
            stop = min(start + PASSAGE_CHARS, end)
            raw = evidence.text[start:stop]
            quote = raw.strip()
            if quote and quote not in seen:
                seen.add(quote)
                yield {
                    "evidence_id": evidence.evidence_id, "text": quote, "action": evidence.value,
                    "quote_start": start + len(raw) - len(raw.lstrip()),
                }
            if stop == end:
                break
            start = stop - _PASSAGE_OVERLAP


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
        generate: Callable[[str, list[ModelSource]], dict],
        *,
        observe_embedding: Callable[[tuple[str, ...]], None] | None = None,
    ):
        self.embed = embed
        self.generate = generate
        self._observe_embedding = observe_embedding

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
        canonical = {citation.evidence_id: citation for citation in analysis.citations}
        # EIE evaluated the full applicable set, including records affecting supersession.
        # Its current authoritative SOPs are the sources eligible for a draft citation.
        current = [
            record for record in _current_evidence(request, candidates)
            if record.evidence_id in canonical and record.authority == "approved_sop"
        ]
        if (len(current) > MAX_CANDIDATES
                or sum(len(record.text) for record in current) > _MAX_AUTHORIZED_CHARS):
            return HybridAnalysis(analysis=analysis, model_status="CONTEXT_LIMIT")
        if len(current) != len(canonical) or any(
            canonical[record.evidence_id].checksum != record.checksum
            or hashlib.sha256(record.text.encode("utf8")).hexdigest() != record.checksum
            for record in current
        ):
            return HybridAnalysis(analysis=analysis, model_status="MODEL_REVIEW_REQUIRED")

        sources = []
        for record in current:
            for passage in _passages(record):
                if len(sources) == _MAX_PASSAGES:
                    return HybridAnalysis(analysis=analysis, model_status="CONTEXT_LIMIT")
                sources.append(passage)
        if not sources:
            return HybridAnalysis(analysis=analysis, model_status="MODEL_REVIEW_REQUIRED")
        try:
            selected = self._rank(query, sources)[:TOP_K]
            output = self.generate(query, selected)
        except ModelUnavailable:
            return HybridAnalysis(analysis=analysis, model_status="MODEL_UNAVAILABLE")

        try:
            draft = self._validate(output, selected, analysis, canonical)
        except (ValidationError, ValueError):
            return HybridAnalysis(analysis=analysis, model_status="MODEL_REVIEW_REQUIRED")
        return HybridAnalysis(analysis=analysis, model_status="DRAFT_READY", draft=draft)

    def _rank(self, query: str, sources: list[ModelSource]) -> list[ModelSource]:
        texts = [source["text"] for source in sources]
        lexical = _bm25(query, texts)
        tie_breakers = [
            (not _ACTION_CUE.search(source["text"][:80]), source["evidence_id"], source["quote_start"])
            for source in sources
        ]
        # Lexical search covers every exact passage. Embed only the bounded shortlist.
        order = sorted(range(len(sources)), key=lambda index: (-lexical[index], *tie_breakers[index]))
        order = order[:_RERANK_PASSAGES]
        sources = [sources[index] for index in order]
        tie_breakers = [tie_breakers[index] for index in order]
        lexical = [lexical[index] for index in order]
        search_instruction = "Instruct: Given a maintenance question, retrieve relevant policy evidence"
        embedding_inputs: list[tuple[str, str | None]] = [
            (f"{search_instruction}\nQuery: {query}", None)
        ]
        embedding_inputs.extend((source["text"], source["evidence_id"]) for source in sources)
        vectors = []
        for start in range(0, len(embedding_inputs), EMBEDDING_BATCH):
            batch = embedding_inputs[start:start + EMBEDDING_BATCH]
            if self._observe_embedding is not None:
                self._observe_embedding(tuple(source_id for _, source_id in batch if source_id is not None))
            result = self.embed([text for text, _ in batch])
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
        scores = [0.0] * len(sources)
        # Reciprocal rank fusion uses comparable ranks for the two different score scales.
        # Zero lexical scores are absent from that ranking.
        for signals, include_zero in ((semantic, True), (lexical, False)):
            order = sorted(
                range(len(sources)),
                key=lambda index: (-signals[index], *tie_breakers[index]),
            )
            for rank, index in enumerate(order, start=1):
                if include_zero or signals[index] > 0:
                    scores[index] += 1 / (60 + rank)
        return [
            sources[index] for index in sorted(
                range(len(sources)),
                key=lambda index: (-scores[index], *tie_breakers[index]),
            )
        ]

    @staticmethod
    def _validate(
        output: dict,
        sources: list[ModelSource],
        analysis: Analysis,
        canonical: dict[str, Citation],
    ) -> HybridDraft:
        proposed = _ModelOutput.model_validate(output)
        if proposed.action != analysis.recommended_action:
            raise ValueError("Draft action differs from the EIE determination")
        citations = []
        used = set()
        for item in proposed.citations:
            if item.evidence_id in used or item.evidence_id not in canonical or not item.quote.strip():
                raise ValueError("Unexpected citation")
            offsets = set()
            for source in sources:
                if source["evidence_id"] != item.evidence_id:
                    continue
                passage_start = source["quote_start"]
                text = source["text"]
                if item.quote_start is not None:
                    position = item.quote_start - passage_start
                    if position >= 0 and text.startswith(item.quote, position):
                        offsets.add(item.quote_start)
                else:
                    position = text.find(item.quote)
                    while position >= 0:
                        offsets.add(passage_start + position)
                        position = text.find(item.quote, position + 1)
            if len(offsets) != 1:
                raise ValueError("Quote does not match a unique source location")
            used.add(item.evidence_id)
            citations.append(DraftCitation(
                **canonical[item.evidence_id].model_dump(), quote=item.quote, quote_start=offsets.pop()
            ))
        return HybridDraft(action=proposed.action, citations=citations)
