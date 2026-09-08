"""Project-scoped source-document storage and token-saving text diffs."""

from __future__ import annotations

import difflib
import hashlib
import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3

from app.document.doc_reader import read_document


def project_source_scope(metadata: Dict[str, Any]) -> str:
    """Return a stable, non-PII S3 scope; prefer immutable project identity."""
    stored_scope = str(metadata.get("source_scope_id") or "").strip()
    if re.fullmatch(r"[a-f0-9]{32}", stored_scope):
        return stored_scope
    project_id = str(metadata.get("project_id") or "").strip()
    if project_id:
        identity = f"project:{project_id}"
    else:
        identity = "|".join([
            str(metadata.get("owner_email") or "").casefold().strip(),
            str(metadata.get("company_name") or metadata.get("customer_name") or "").casefold().strip(),
            str(metadata.get("project_title") or metadata.get("project_name") or "").casefold().strip(),
        ])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def content_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_text_diff(previous: str, current: str, filename: str) -> tuple[str, str]:
    """Return (context, status), sending only a compact diff for small changes."""
    old = str(previous or "").splitlines()
    new = str(current or "").splitlines()
    if old == new:
        return "", "unchanged"
    delta = list(difflib.unified_diff(
        old,
        new,
        fromfile=f"previous/{filename}",
        tofile=f"uploaded/{filename}",
        n=2,
        lineterm="",
    ))
    diff_text = "\n".join(delta)
    # A replacement document is clearer and usually smaller as full content;
    # small amendments remain a true delta and save model context.
    if not old or len(diff_text) > max(4000, int(len(current) * 0.65)):
        return f"FULL NEW SOURCE DOCUMENT: {filename}\n{current}", "new_or_replaced"
    return f"SOURCE DOCUMENT CHANGES ONLY: {filename}\n{diff_text}", "changed"


class SourceDocumentStore:
    """Persist source originals, extracted text, and revision metadata in S3."""

    PREFIX = "source-documents"

    def __init__(self, client=None, bucket: Optional[str] = None):
        self.bucket = bucket or os.getenv("S3_BUCKET_NAME", "agentic-sow-files")
        self.client = client or boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename or "source-document").name
        return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "source-document"

    def _prefix(self, scope_id: str) -> str:
        return f"{self.PREFIX}/{scope_id}/"

    def list_documents(self, scope_id: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        continuation = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": self._prefix(scope_id)}
            if continuation:
                kwargs["ContinuationToken"] = continuation
            response = self.client.list_objects_v2(**kwargs)
            for item in response.get("Contents", []):
                key = str(item.get("Key") or "")
                if not key.endswith("/metadata.json"):
                    continue
                try:
                    body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
                    metadata = json.loads(body.decode("utf-8"))
                    if isinstance(metadata, dict):
                        rows.append(metadata)
                except Exception:
                    continue
            if not response.get("IsTruncated"):
                break
            continuation = response.get("NextContinuationToken")
        return sorted(rows, key=lambda row: str(row.get("uploaded_at") or ""), reverse=True)

    def _read_extracted(self, metadata: Dict[str, Any]) -> str:
        key = metadata.get("text_key")
        if not key:
            return ""
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return body.decode("utf-8", errors="replace")

    def ingest(
        self,
        scope_id: str,
        file_path: str | Path,
        original_filename: str,
        extracted_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        file_path = Path(file_path)
        safe_name = self._safe_filename(original_filename)
        digest = content_sha256(file_path)
        existing = self.list_documents(scope_id)
        exact = next((row for row in existing if row.get("content_hash") == digest), None)
        if exact:
            return {
                **exact,
                "comparison": "unchanged",
                "context": "",
                "reused": True,
            }

        current_text = extracted_text if extracted_text is not None else read_document(str(file_path))
        same_name = [
            row for row in existing
            if str(row.get("filename") or "").casefold() == safe_name.casefold()
        ]
        previous = same_name[0] if same_name else None
        previous_text = self._read_extracted(previous) if previous else ""
        context, comparison = source_text_diff(previous_text, current_text, safe_name)
        revision = 1 + max([int(row.get("revision") or 0) for row in same_name] or [0])
        source_id = digest[:20]
        root = f"{self._prefix(scope_id)}{safe_name}/{digest}"
        original_key = f"{root}/original{file_path.suffix.casefold()}"
        text_key = f"{root}/extracted.txt"
        metadata_key = f"{root}/metadata.json"
        uploaded_at = datetime.now(timezone.utc).isoformat()
        record = {
            "source_id": source_id,
            "filename": safe_name,
            "content_hash": digest,
            "revision": revision,
            "uploaded_at": uploaded_at,
            "comparison": comparison,
            "previous_source_id": previous.get("source_id") if previous else None,
            "extracted_characters": len(current_text),
            "original_key": original_key,
            "text_key": text_key,
            "metadata_key": metadata_key,
        }
        content_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        self.client.upload_file(
            str(file_path), self.bucket, original_key, ExtraArgs={"ContentType": content_type}
        )
        self.client.put_object(
            Bucket=self.bucket,
            Key=text_key,
            Body=current_text.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        self.client.put_object(
            Bucket=self.bucket,
            Key=metadata_key,
            Body=json.dumps(record, separators=(",", ":")).encode("utf-8"),
            ContentType="application/json",
        )
        return {**record, "context": context, "reused": False}

    def download(self, scope_id: str, source_id: str) -> tuple[bytes, Dict[str, Any]]:
        record = next(
            (row for row in self.list_documents(scope_id) if row.get("source_id") == source_id),
            None,
        )
        if not record:
            raise FileNotFoundError("Supporting document not found")
        body = self.client.get_object(Bucket=self.bucket, Key=record["original_key"])["Body"].read()
        return body, record


def public_source_metadata(record: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "source_id", "filename", "content_hash", "revision", "uploaded_at",
        "comparison", "previous_source_id", "extracted_characters", "reused",
    }
    return {key: value for key, value in record.items() if key in allowed and value is not None}
