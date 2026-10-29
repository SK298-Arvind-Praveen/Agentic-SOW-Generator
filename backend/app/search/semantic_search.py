"""Semantic ranking for SOW history records."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import boto3


SIMILARITY_THRESHOLD = 0.67
SEMANTIC_INDEX_VERSION = 3
MAX_SEARCH_TEXT_CHARS = 80_000
MAX_EMBED_TEXT_CHARS = 24_000
EMBEDDING_DIMENSIONS = 256
SEMANTIC_CHUNK_CHARS = 6_000
MAX_SEMANTIC_CHUNKS = 8
_embedding_cache: Dict[str, List[float]] = {}
_cache_lock = threading.Lock()


def _normalise(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _version_number(value: Any) -> int:
    match = re.search(r"(\d+)", str(value or ""))
    return int(match.group(1)) if match else 0


def _record_timestamp(record: Dict[str, Any]) -> str:
    return str(record.get("timestamp") or record.get("created_at") or record.get("document_date") or "")


def _lineage_key(record: Dict[str, Any]) -> tuple:
    mode = _normalise(record.get("mode"))
    owner = _normalise(record.get("owner_email"))
    if record.get("project_id"):
        return ("project", owner, _normalise(record.get("project_id")), mode)
    if record.get("source_scope_id"):
        return ("scope", owner, _normalise(record.get("source_scope_id")), mode)
    project = _normalise(record.get("project_name"))
    customer = _normalise(record.get("customer_name") or record.get("company_name"))
    if project:
        return ("names", owner, customer, project, mode)
    return ("document", _normalise(record.get("document_id")))


def latest_versions(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only the latest version of each logical SOW before scoring."""
    latest: Dict[tuple, Dict[str, Any]] = {}
    for record in records:
        key = _lineage_key(record)
        current = latest.get(key)
        rank = (_version_number(record.get("version")), _record_timestamp(record))
        current_rank = (
            _version_number(current.get("version")), _record_timestamp(current)
        ) if current else (-1, "")
        if current is None or rank > current_rank:
            latest[key] = record
    return list(latest.values())


def build_semantic_search_text(content: Any, metadata: Dict[str, Any] | None = None) -> str:
    """Create broad, compact search text while retaining headings from the full SOW."""
    metadata = metadata or {}
    identity = [
        f"Customer: {metadata.get('company_name') or metadata.get('customer_name') or ''}",
        f"Project: {metadata.get('project_title') or metadata.get('project_name') or ''}",
        f"Mode: {metadata.get('mode') or ''}",
        f"Business unit: {metadata.get('business_unit') or ''}",
    ]
    short_values: List[str] = []
    long_values: List[str] = []
    seen = set()

    def add(value: Any) -> None:
        cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
        normalized = cleaned.casefold()
        if not cleaned or normalized in seen:
            return
        seen.add(normalized)
        if len(cleaned) <= 500:
            short_values.append(cleaned)
        else:
            # Long paragraphs must not crowd out headings/modules appearing
            # later in the document. Their concise leading text is enough for
            # semantic context; exact section names are retained separately.
            long_values.append(cleaned[:1200])

    def collect(value: Any, key: str = "") -> None:
        if any(token in key.casefold() for token in ("asset", "image", "base64", "svg", "data_url")):
            return
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                readable_key = re.sub(r"[_-]+", " ", str(child_key)).strip()
                if readable_key and not readable_key.startswith("_"):
                    add(readable_key)
                collect(child_value, str(child_key))
        elif isinstance(value, (list, tuple)):
            for child in value:
                collect(child, key)
        elif isinstance(value, str):
            if len(value) > 1200:
                for segment in re.split(r"(?:\r?\n)+|(?<=[.!?])\s+", value):
                    add(segment)
            else:
                add(value)
        elif isinstance(value, (int, float)):
            add(value)

    collect(content)
    ordered = [value for value in identity if not value.endswith(": ")]
    ordered.extend(short_values)
    ordered.extend(long_values)
    return "\n".join(ordered)[:MAX_SEARCH_TEXT_CHARS]


def record_search_text(record: Dict[str, Any]) -> str:
    stored = str(record.get("semantic_search_text") or "").strip()
    if stored:
        return stored[:MAX_SEARCH_TEXT_CHARS]
    source_names = " ".join(
        str(item.get("filename") or "")
        for item in (record.get("source_documents") or [])
        if isinstance(item, dict)
    )
    selected = " ".join(str(value) for value in (record.get("selected_sow_sections") or []))
    return "\n".join(filter(None, [
        str(record.get("customer_name") or record.get("company_name") or ""),
        str(record.get("project_name") or ""), str(record.get("mode") or ""),
        str(record.get("business_unit") or ""), str(record.get("author_name") or ""),
        source_names, selected, str(record.get("refinement_instructions") or ""),
    ]))[:MAX_SEARCH_TEXT_CHARS]


def semantic_text_hash(text: str) -> str:
    """Stable fingerprint used to detect stale persisted vectors."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_SEARCH_TEXT_CHARS]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def stored_embedding(record: Dict[str, Any], model_id: str = "") -> List[float]:
    """Return a reusable vector only when it belongs to the active model."""
    stored_model = str(record.get("semantic_embedding_model_id") or "")
    if model_id and stored_model != model_id:
        return []
    if model_id:
        try:
            if int(record.get("semantic_index_version") or 0) != SEMANTIC_INDEX_VERSION:
                return []
        except (TypeError, ValueError):
            return []
    values = record.get("semantic_search_embedding")
    if not isinstance(values, (list, tuple)) or not values:
        return []
    try:
        return [float(value) for value in values]
    except (TypeError, ValueError):
        return []


def stored_embeddings(record: Dict[str, Any], model_id: str = "") -> List[List[float]]:
    """Return all current chunk vectors, with legacy single-vector compatibility."""
    if not stored_embedding(record, model_id):
        return []
    vectors = record.get("semantic_search_embeddings")
    if isinstance(vectors, (list, tuple)) and vectors:
        try:
            parsed = [[float(value) for value in vector] for vector in vectors if vector]
            if parsed:
                return parsed
        except (TypeError, ValueError):
            pass
    return [stored_embedding(record, model_id)]


def _semantic_chunks(text: str) -> List[str]:
    """Create evenly distributed section-aware chunks without exceeding index size."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    chunks: List[str] = []
    current: List[str] = []
    current_chars = 0
    for line in lines:
        if current and current_chars + len(line) + 1 > SEMANTIC_CHUNK_CHARS:
            chunks.append("\n".join(current))
            current, current_chars = [], 0
        current.append(line[:SEMANTIC_CHUNK_CHARS])
        current_chars += len(current[-1]) + 1
    if current:
        chunks.append("\n".join(current))
    if len(chunks) <= MAX_SEMANTIC_CHUNKS:
        return chunks
    # Sample across the entire SOW so late deliverables remain searchable.
    indexes = {
        round(position * (len(chunks) - 1) / (MAX_SEMANTIC_CHUNKS - 1))
        for position in range(MAX_SEMANTIC_CHUNKS)
    }
    return [chunks[index] for index in sorted(indexes)]


class BedrockSemanticEmbedder:
    def __init__(self, config: Any) -> None:
        self.model_id = str(
            getattr(config, "SEMANTIC_SEARCH_EMBEDDING_MODEL_ID", "")
            or os.getenv("SEMANTIC_SEARCH_EMBEDDING_MODEL_ID", "")
            or "arn:aws:bedrock:us-east-1:106611079163:"
            "application-inference-profile/ve7wpqurv75w"
        )
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=config.BEDROCK_REGION,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
            config=config.BOTO_CONFIG,
        )

    def embed(self, text: str) -> List[float]:
        text = re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_EMBED_TEXT_CHARS]
        if not text:
            return []
        cache_key = hashlib.sha256(
            f"{self.model_id}\0{EMBEDDING_DIMENSIONS}\0{text}".encode("utf-8")
        ).hexdigest()
        with _cache_lock:
            cached = _embedding_cache.get(cache_key)
        if cached is not None:
            return cached
        response = self.client.invoke_model(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inputText": text,
                "dimensions": EMBEDDING_DIMENSIONS,
                "normalize": True,
            }),
        )
        vector = [float(value) for value in json.loads(response["body"].read()).get("embedding", [])]
        if not vector:
            raise RuntimeError("The embedding model returned an empty vector")
        with _cache_lock:
            if len(_embedding_cache) >= 2048:
                _embedding_cache.clear()
            _embedding_cache[cache_key] = vector
        return vector

    def index_fields(self, text: str) -> Dict[str, Any]:
        """Build the fields persisted with a SOW for future zero-document-I/O searches."""
        searchable = str(text or "")[:MAX_SEARCH_TEXT_CHARS]
        chunks = _semantic_chunks(searchable) or [searchable]
        vectors = [self.embed(chunk) for chunk in chunks]
        return {
            "semantic_search_text": searchable,
            "semantic_search_embedding": vectors[0],
            "semantic_search_embeddings": vectors,
            "semantic_embedding_model_id": self.model_id,
            "semantic_search_text_hash": semantic_text_hash(searchable),
            "semantic_index_version": SEMANTIC_INDEX_VERSION,
        }


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    magnitude = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / magnitude if magnitude else 0.0


def _calibrate_titan_score(raw_cosine: float) -> float:
    """Map Titan query-to-document cosine's compressed useful range to 0..1."""
    raw = max(0.0, min(1.0, raw_cosine))
    if raw <= 0.03:
        return 0.0
    if raw <= 0.15:
        return ((raw - 0.03) / 0.12) * 0.50
    return 0.50 + ((raw - 0.15) / 0.85) * 0.50


def _lexical_score(record: Dict[str, Any], text: str, query: str) -> tuple[float, str]:
    """Guarantee intuitive exact matches while semantic ranking handles concepts."""
    normalized_query = _normalise(query)
    if not normalized_query:
        return 0.0, "empty_query"
    identity = _normalise(" ".join(str(record.get(field) or "") for field in (
        "project_name", "customer_name", "company_name", "mode", "business_unit",
    )))
    normalized_text = _normalise(text)
    if normalized_query in identity:
        return 1.0, "exact_title_or_metadata"
    if normalized_query in normalized_text:
        return 0.98, "exact_document_phrase"
    query_tokens = set(re.findall(r"[a-z0-9]+", normalized_query))
    if not query_tokens:
        return 0.0, "no_search_tokens"
    text_tokens = set(re.findall(r"[a-z0-9]+", normalized_text))
    overlap = len(query_tokens & text_tokens) / len(query_tokens)
    if overlap == 1.0:
        return 0.90, "all_query_terms"
    if overlap:
        return overlap * 0.70, "partial_query_terms"
    return 0.0, "semantic_only"


def semantic_search_records(
    records: Iterable[Dict[str, Any]],
    query: str,
    embed: Callable[[str], List[float]],
    threshold: float = SIMILARITY_THRESHOLD,
    model_id: str = "",
    diagnostics: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    query_vector = embed(query)
    results: List[Dict[str, Any]] = []
    for record in latest_versions(records):
        text = record_search_text(record)
        if not text:
            continue
        vectors = stored_embeddings(record, model_id) or [embed(text)]
        raw_semantic_score = max((_cosine(query_vector, vector) for vector in vectors), default=0.0)
        semantic_score = _calibrate_titan_score(raw_semantic_score)
        lexical_score, match_reason = _lexical_score(record, text, query)
        score = max(semantic_score, lexical_score)
        if diagnostics is not None:
            diagnostics.append({
                "document_id": record.get("document_id"),
                "project_name": record.get("project_name"),
                "version": record.get("version"),
                "semantic_score": round(semantic_score * 100, 2),
                "raw_semantic_score": round(raw_semantic_score * 100, 2),
                "lexical_score": round(lexical_score * 100, 2),
                "final_score": round(score * 100, 2),
                "reason": match_reason,
                "indexed_chars": len(text),
                "chunks": len(vectors),
                "matched": score >= threshold,
            })
        if score >= threshold:
            result = dict(record)
            result["similarity_score"] = round(score * 100, 2)
            results.append(result)
    results.sort(
        key=lambda item: (
            float(item["similarity_score"]),
            _version_number(item.get("version")),
            _record_timestamp(item),
        ),
        reverse=True,
    )
    return results
