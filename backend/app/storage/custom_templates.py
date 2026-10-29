"""Shared persistence for extracted, project-agnostic SOW templates."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config as BotoConfig


class CustomTemplateStore:
    """Store templates in the existing RBAC table under an isolated partition.

    Markdown is intentionally stored with the metadata: extracted templates are
    small, this avoids introducing another bucket/configuration dependency, and
    all app instances see the same presets.
    """

    PARTITION_KEY = "CUSTOM_TEMPLATE"
    SCHEMA_VERSION = 3
    _cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _normalise_sections(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply current semantic dedupe rules to older saved presets too."""
        from app.agents.custom_template_agent import CustomTemplateAgent

        normalised: List[Dict[str, Any]] = []
        for raw in sections or []:
            section = dict(raw)
            base_id = str(
                section.get("base_section_id")
                or CustomTemplateAgent._base_section_match(str(section.get("label") or ""))
                or ""
            )
            if base_id:
                section["base_section_id"] = base_id
                section["id"] = base_id
                section["hidden"] = True
            else:
                section["hidden"] = bool(section.get("hidden", False))
            normalised.append(section)
        return normalised

    def __init__(self, table: Any = None) -> None:
        if table is not None:
            self.table = table
            return
        self.table = boto3.resource(
            "dynamodb",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
            config=BotoConfig(connect_timeout=2, read_timeout=3, retries={"max_attempts": 2}),
        ).Table(os.getenv("DYNAMODB_TABLE_RBAC", "agentic-sow-rbac"))

    @staticmethod
    def _public(item: Dict[str, Any], viewer_email: str = "", is_admin: bool = False) -> Dict[str, Any]:
        result = {
            key: value for key, value in item.items()
            if key not in {"PK", "SK", "markdown", "output_path"}
        }
        # Matched headings still remain in the private template schema so the
        # writer can apply their custom guidance to the canonical base section.
        # They are intentionally absent from the drag source to prevent users
        # seeing duplicate choices such as Scope of Work twice.
        result["sections"] = [
            section for section in CustomTemplateStore._normalise_sections(item.get("sections") or [])
            if not bool(section.get("hidden"))
        ]
        result["can_delete"] = bool(
            is_admin
            or str(result.get("owner_email") or "").casefold() == str(viewer_email or "").casefold()
        )
        return result

    def create_draft(
        self,
        *,
        markdown: str,
        sections: List[Dict[str, Any]],
        owner_email: str,
        author_name: str,
        source_filename: str,
        output_path: str,
        template_id: str = "",
    ) -> Dict[str, Any]:
        template_id = template_id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        item = {
            "PK": self.PARTITION_KEY,
            "SK": template_id,
            "template_id": template_id,
            "name": "",
            "author": author_name or owner_email,
            "owner_email": owner_email.casefold(),
            "source_filename": source_filename,
            "markdown": markdown,
            "sections": sections,
            "saved": False,
            "created_at": now,
            "updated_at": now,
            "output_path": output_path,
            "schema_version": self.SCHEMA_VERSION,
        }
        self._cache[template_id] = dict(item)
        self.table.put_item(Item=item)
        return self._public(item, owner_email)

    def get(self, template_id: str) -> Optional[Dict[str, Any]]:
        if template_id in self._cache:
            item = dict(self._cache[template_id])
            item["sections"] = self._normalise_sections(item.get("sections") or [])
            return item
        response = self.table.get_item(Key={"PK": self.PARTITION_KEY, "SK": template_id})
        item = response.get("Item")
        if item:
            item["sections"] = self._normalise_sections(item.get("sections") or [])
            self._cache[template_id] = dict(item)
        return item

    def list_saved(self, viewer_email: str = "", is_admin: bool = False) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        query_args: Dict[str, Any] = {"KeyConditionExpression": Key("PK").eq(self.PARTITION_KEY)}
        while True:
            response = self.table.query(**query_args)
            items.extend(
                item for item in response.get("Items", [])
                if bool(item.get("saved"))
                and int(item.get("schema_version") or 0) >= self.SCHEMA_VERSION
            )
            if not response.get("LastEvaluatedKey"):
                break
            query_args["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        items.sort(key=lambda item: str(item.get("name") or "").casefold())
        return [self._public(item, viewer_email, is_admin) for item in items]

    def _unique_preset_name(self, requested_name: str, template_id: str) -> str:
        """Return a shared preset name using Windows-style numeric suffixes."""
        existing_names = set()
        query_args: Dict[str, Any] = {"KeyConditionExpression": Key("PK").eq(self.PARTITION_KEY)}
        while True:
            response = self.table.query(**query_args)
            for existing in response.get("Items", []):
                if (
                    bool(existing.get("saved"))
                    and str(existing.get("template_id") or existing.get("SK") or "") != template_id
                ):
                    existing_name = str(existing.get("name") or "").strip()
                    if existing_name:
                        existing_names.add(existing_name.casefold())
            if not response.get("LastEvaluatedKey"):
                break
            query_args["ExclusiveStartKey"] = response["LastEvaluatedKey"]

        if requested_name.casefold() not in existing_names:
            return requested_name

        sequence = 1
        while True:
            suffix = f" ({sequence:02d})"
            base = requested_name[: 80 - len(suffix)].rstrip()
            candidate = f"{base}{suffix}"
            if candidate.casefold() not in existing_names:
                return candidate
            sequence += 1

    def save_preset(self, template_id: str, name: str, owner_email: str) -> Dict[str, Any]:
        name = str(name or "").strip()
        if not name:
            raise ValueError("Template name is required")
        if len(name) > 80:
            raise ValueError("Template name must be 80 characters or fewer")
        item = self.get(template_id)
        if not item:
            raise LookupError("Custom template not found")
        if str(item.get("owner_email") or "").casefold() != owner_email.casefold():
            raise PermissionError("Only the template creator can save this extraction as a preset")
        item["name"] = self._unique_preset_name(name, template_id)
        item["saved"] = True
        item["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._cache[template_id] = dict(item)
        self.table.put_item(Item=item)
        return self._public(item, owner_email)

    def delete(self, template_id: str, requester_email: str, is_admin: bool = False) -> None:
        item = self.get(template_id)
        if not item:
            raise LookupError("Custom template not found")
        owns = str(item.get("owner_email") or "").casefold() == requester_email.casefold()
        if not (is_admin or owns):
            raise PermissionError("Only the template creator or an administrator can delete it")
        self.table.delete_item(Key={"PK": self.PARTITION_KEY, "SK": template_id})
        self._cache.pop(template_id, None)
        output_path = str(item.get("output_path") or "").strip()
        if output_path:
            try:
                Path(output_path).unlink(missing_ok=True)
            except OSError:
                pass
