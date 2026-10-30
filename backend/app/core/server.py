"""
Async Flask API Server for AWS SOW Generator
Port: 9000
✅ ASYNC: Background task processing
✅ FIXED: No connection timeout issues
✅ QUEUE: Task queue management
✅ STATUS: Real-time progress tracking
✅ FIXED: Race condition in task creation
✅ NEW: Active tasks visible in history APIs
✅ UPDATED: Fixed timestamp sorting, memory leaks, task lookup fallback
✅ ENHANCED: History APIs now return full task details (matching /api/task/<id>)
✅ NEW: Drive link included in ALL history API responses (history, recent-pocs, recent-prod, recent-poc_to_prod)
"""

import os
import sys
import io
import json
import re
import subprocess
import tempfile
import threading
import uuid
import time
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue

# Force unbuffered output so every print() appears immediately in the terminal.
# PYTHONUNBUFFERED covers the C-level buffer; reconfigure covers the Python wrapper.
os.environ.setdefault('PYTHONUNBUFFERED', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

# Add backend root so `from app.xxx import ...` works.
# Do NOT add app/core/ itself — that would register server.py as 'app' and
# shadow the app/ package, breaking all app.* imports at runtime.
_backend_root = str(Path(__file__).resolve().parents[2])  # backend/
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from flask import Flask, render_template, request, jsonify, send_file, Response, g
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError

from app.core.graph import create_graph, create_preview_graph, create_fast_preview_graph
from app.core.config import Config
from app.core.bedrock_llm import BedrockLLM
from app.storage.upload import upload_generated_document
from app.storage.upload1 import parse_s3_location, upload_to_s3
from app.storage.source_documents import (
    SourceDocumentStore,
    project_source_scope,
    public_source_metadata,
)
from app.storage.custom_templates import CustomTemplateStore
from app.agents.custom_template_agent import CustomTemplateAgent
from app.db.dynamodb_handler_optimized import (
    DynamoDBHandlerOptimized,
    save_to_dynamodb_optimized as save_to_dynamodb,
    DynamoDBHandlerOptimized as DynamoDBHandler,
)
from app.document.document_builder import DocumentBuilder
from app.document.doc_reader import (
    SUPPORTED_DOCUMENT_EXTENSIONS,
    extract_supporting_documents_with_diagnostics,
    read_document,
)
from app.diagram.service import (
    ASSET_KEY as ARCHITECTURE_ASSETS_KEY,
    LEGACY_ASSET_KEY as ARCHITECTURE_ASSET_KEY,
    update_asset as update_architecture_asset,
)
from app.pricing import AwsPricingService, render_aws_pricing_section
from app.search.semantic_search import (
    BedrockSemanticEmbedder,
    SIMILARITY_THRESHOLD,
    build_semantic_search_text,
    latest_versions,
    semantic_search_records,
    stored_embedding,
)
from app.preview.preview_handler import (
    create_preview_id, store_preview_data, get_preview_data,
    update_preview_data, delete_preview_data, extract_content_structure,
    preview_lock, preview_storage, get_storage_stats_safe
)
from app.agents.content_editor import SmartContentEditor
from app.api.account_handler import AccountHandler
from app.core.access_control import (
    BUSINESS_UNITS,
    DEFAULT_SECTION_CATALOGUE,
    Identity,
    RBACStore,
    AuthServiceUnavailable,
    current_identity,
    filter_visible_items,
    issue_password_reset_token,
    issue_token,
    issue_verification_token,
    item_is_visible,
    normalise_business_unit,
    scoped_business_unit,
    slugify_section_id,
    send_verification_email,
    send_password_reset_email,
    verify_password_reset_token,
    verify_token,
    verify_verification_token,
)
from itsdangerous import BadSignature, SignatureExpired

load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")

# ── Logging ──────────────────────────────────────────────────────────────────
import logging

# Stream handler writing to stdout (visible in every terminal)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S'
))

# Flask app logger
logging.getLogger('flask.app').setLevel(logging.DEBUG)
logging.getLogger('flask.app').addHandler(_handler)
logging.getLogger('flask.app').propagate = False

# Werkzeug request logger (prints GET /api/xxx 200 lines)
_wz = logging.getLogger('werkzeug')
_wz.setLevel(logging.INFO)
_wz.addHandler(_handler)
_wz.propagate = False

# Root logger fallback
logging.basicConfig(level=logging.INFO, handlers=[_handler], force=True)
# ─────────────────────────────────────────────────────────────────────────────

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure upload folder
UPLOAD_FOLDER = Path(os.getcwd()) / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max

rbac_store = RBACStore()
custom_template_extractions = {}
custom_template_extraction_lock = threading.Lock()
semantic_index_lock = threading.Lock()
semantic_index_ready = threading.Event()
semantic_index_worker_local = threading.local()
semantic_index_state = {
    "status": "idle", "total": 0, "indexed": 0, "remaining": 0, "errors": 0,
}
preview_auto_draft_threads = set()
preview_auto_draft_lock = threading.Lock()


def _process_custom_template_extraction(
    extraction_id: str,
    temp_path: Path,
    safe_name: str,
    owner_email: str,
    author_name: str,
) -> None:
    """Run the template agent outside the request/Render timeout window."""
    try:
        print(
            f"[CUSTOM TEMPLATE {extraction_id[:8]}] Started background extraction "
            f"for {safe_name}", flush=True,
        )
        print(
            f"[CUSTOM TEMPLATE {extraction_id[:8]}] Reading uploaded document", flush=True,
        )
        source_text = read_document(str(temp_path))
        print(
            f"[CUSTOM TEMPLATE {extraction_id[:8]}] Read {len(source_text):,} characters; "
            "starting template agent", flush=True,
        )
        top_level_headings = CustomTemplateAgent.discover_top_level_headings(
            str(temp_path), source_text
        )
        extracted = CustomTemplateAgent(Config()).extract(
            source_text, safe_name, top_level_headings=top_level_headings
        )
        matched_count = sum(
            1 for section in extracted["sections"] if section.get("base_section_id")
        )
        unique_count = len(extracted["sections"]) - matched_count
        print(
            f"[CUSTOM TEMPLATE {extraction_id[:8]}] Agent returned "
            f"{len(extracted['sections'])} reusable heading(s): "
            f"{matched_count} matched existing sections, {unique_count} unique",
            flush=True,
        )
        for section in extracted["sections"]:
            if section.get("base_section_id"):
                section["id"] = str(section["base_section_id"])
                section["hidden"] = True
            else:
                suffix = str(section["id"]).removeprefix("custom_")
                section["id"] = f"custom_{extraction_id[:8]}_{suffix}"[:64].rstrip('_')
        output_dir = Config().OUTPUT_DIR / "custom-templates"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{extraction_id}.md"
        output_path.write_text(extracted["markdown"], encoding="utf-8")
        print(
            f"[CUSTOM TEMPLATE {extraction_id[:8]}] Wrote inspectable Markdown: "
            f"{output_path}", flush=True,
        )
        print(
            f"[CUSTOM TEMPLATE {extraction_id[:8]}] Persisting sanitized template metadata",
            flush=True,
        )
        template = CustomTemplateStore().create_draft(
            template_id=extraction_id,
            markdown=extracted["markdown"],
            sections=extracted["sections"],
            owner_email=owner_email,
            author_name=author_name,
            source_filename=safe_name,
            output_path=str(output_path),
        )
        with custom_template_extraction_lock:
            custom_template_extractions[extraction_id].update({
                "status": "ready", "template": template, "completed_at": datetime.now().isoformat(),
            })
        print(
            f"[CUSTOM TEMPLATE {extraction_id[:8]}] READY — "
            f"{unique_count} unique custom section(s) available for drag and drop",
            flush=True,
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("Custom template extraction failed")
        print(
            f"[CUSTOM TEMPLATE {extraction_id[:8]}] FAILED — {exc}", flush=True,
        )
        with custom_template_extraction_lock:
            custom_template_extractions[extraction_id].update({
                "status": "failed", "error": str(exc), "completed_at": datetime.now().isoformat(),
            })
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _pricing_audit_record(result):
    """Keep a compact, DynamoDB-safe pricing provenance record."""
    if not isinstance(result, dict) or result.get("status") in {None, "not_selected"}:
        return None
    record = {
        "status": str(result.get("status") or "unknown"),
        "estimate_id": str(result.get("estimate_id") or ""),
        "estimate_url": str(result.get("estimate_url") or ""),
        "currency": str(result.get("currency") or "USD"),
        "monthly_cost": (
            "" if result.get("monthly_cost") is None else str(result.get("monthly_cost"))
        ),
        "region": str(result.get("region") or ""),
        "generated_at": str(result.get("generated_at") or ""),
        "calculator_version": str(result.get("calculator_version") or ""),
        "stale": bool(result.get("stale", False)),
    }
    return {key: value for key, value in record.items() if value not in {"", None}}


@app.errorhandler(AuthServiceUnavailable)
def authentication_service_unavailable(error):
    # Fail closed without claiming the password/session is invalid. Clients
    # retain their token and can retry after the identity store recovers.
    return jsonify({
        "success": False,
        "code": "AUTH_SERVICE_UNAVAILABLE",
        "error": "Sign-in service is temporarily unavailable. Please try again shortly. If this continues, contact your administrator.",
    }), 503, {"Retry-After": "5"}


@app.before_request
def enforce_api_authentication():
    """Authenticate every API request; authorization is enforced by each resource route."""
    public_paths = {
        "/api/auth/login", "/api/auth/signup", "/api/auth/verify",
        "/api/auth/resend-verification", "/api/auth/forgot-password",
        "/api/auth/reset-password", "/health",
    }
    if request.method == "OPTIONS" or request.path in public_paths:
        return None
    if not request.path.startswith("/api/"):
        return None
    if app.config.get("TESTING") and not request.headers.get("Authorization"):
        g.current_identity = Identity("test-admin@shellkode.com", "Test Admin", "ADMIN")
        return None
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return jsonify({"success": False, "error": "Authentication required"}), 401
    try:
        token_identity = verify_token(header[7:].strip())
        g.current_identity = rbac_store.active_identity(token_identity.email)
        if not g.current_identity:
            return jsonify({"success": False, "error": "Account is inactive or no longer exists"}), 401
    except SignatureExpired:
        return jsonify({"success": False, "error": "Session expired"}), 401
    except (BadSignature, KeyError, ValueError):
        return jsonify({"success": False, "error": "Invalid session"}), 401
    if g.current_identity.is_user and (
        request.path.startswith("/api/accounts") or request.path.startswith("/api/projects")
    ):
        return jsonify({"success": False, "error": "Accounts dashboard access is not available for the User role"}), 403
    return None


def _requested_business_unit() -> str | None:
    value = request.args.get("business_unit")
    if not value and request.is_json:
        value = (request.get_json(silent=True) or {}).get("business_unit")
    if not value:
        value = request.form.get("business_unit")
    return scoped_business_unit(current_identity(), value)


def _requested_business_unit_filter():
    """Return one requested BU or every BU granted by a multi-role identity."""
    selected = _requested_business_unit()
    if selected or current_identity().is_admin or current_identity().is_user:
        return selected
    return current_identity().business_units


def _require_admin_response():
    if not current_identity().is_admin:
        return jsonify({"success": False, "error": "Administrator access required"}), 403
    return None


@app.errorhandler(ValueError)
def invalid_request_value(error):
    return jsonify({"success": False, "error": str(error)}), 400


def _business_unit_for_new_record():
    """Use the existing primary assignment when no UI selection is supplied.

    Explicit selections still undergo access validation. Unassigned admins
    remain unassigned rather than silently assigning records to another team.
    """
    business_unit = _requested_business_unit()
    return business_unit or current_identity().business_unit, None


def _ownership_metadata(business_unit=None):
    """Return immutable ownership fields derived from the authenticated identity."""
    identity = current_identity()
    return {
        "business_unit": business_unit if business_unit is not None else identity.business_unit,
        "owner_email": identity.email,
        "owner_name": identity.name,
    }


def _resource_denied(item):
    if not item:
        return jsonify({"success": False, "error": "Resource not found"}), 404
    if not item_is_visible(item, current_identity(), request.args.get("business_unit")):
        return jsonify({"success": False, "error": "You do not have access to this business unit"}), 403
    return None


def _preview_denied(preview_data):
    return _resource_denied((preview_data or {}).get("metadata") if preview_data else None)


def _visible_documents(items):
    """Scope both persisted documents and active-task wrapper objects."""
    requested = request.args.get("business_unit")
    visible = []
    for item in items or []:
        candidate = item.get("document", item)
        if item_is_visible(candidate, current_identity(), requested):
            visible.append(item)
    return visible


def _document_record(document_id):
    handler = DynamoDBHandler()
    record = handler.get_document_by_id(str(document_id or "").strip())
    denied = _resource_denied(record)
    return record, denied


def _read_s3_document(s3_url: str) -> tuple[str, str]:
    """Download a persisted SOW to a temporary file and extract its text."""
    bucket, key = parse_s3_location(s3_url)
    response = get_s3_client().get_object(Bucket=bucket, Key=key)
    suffix = Path(key).suffix.lower() or ".docx"
    fd, temp_path = tempfile.mkstemp(prefix="sow-refinement-base-", suffix=suffix)
    os.close(fd)
    try:
        with open(temp_path, "wb") as stream:
            stream.write(response["Body"].read())
        return read_document(temp_path), temp_path
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def _semantic_index_metadata(content, metadata):
    """Create and persist a vector when the SOW is written, never during search."""
    searchable = build_semantic_search_text(content, metadata)
    base = {"semantic_search_text": searchable}
    try:
        return BedrockSemanticEmbedder(Config()).index_fields(searchable)
    except Exception as exc:
        # Saving the completed SOW is more important than indexing it. The
        # background backfill will retry without making the user regenerate.
        semantic_index_ready.clear()
        with semantic_index_lock:
            semantic_index_state["status"] = "idle"
        print(f"[SEMANTIC INDEX] Write-time indexing deferred: {exc}", flush=True)
        return base


def _backfill_semantic_record(record):
    """Index one historical latest-version record and persist the result."""
    embedder = getattr(semantic_index_worker_local, "embedder", None)
    handler = getattr(semantic_index_worker_local, "handler", None)
    if embedder is None or handler is None:
        embedder = BedrockSemanticEmbedder(Config())
        handler = DynamoDBHandler()
        semantic_index_worker_local.embedder = embedder
        semantic_index_worker_local.handler = handler
    text = str(record.get("semantic_search_text") or "").strip()
    try:
        old_index_format = int(record.get("semantic_index_version") or 0) < 3
    except (TypeError, ValueError):
        old_index_format = True
    temp_path = None
    try:
        if (not text or old_index_format) and record.get("s3_url"):
            extracted, temp_path = _read_s3_document(str(record["s3_url"]))
            text = build_semantic_search_text(extracted, record)
        if not text:
            text = build_semantic_search_text({}, record)
        fields = embedder.index_fields(text)
        handler.update_semantic_index(record, fields)
        return True
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _run_semantic_index_backfill():
    """One-time parallel migration for records created before vector indexing."""
    errors = 0
    try:
        handler = DynamoDBHandler()
        embedder = BedrockSemanticEmbedder(Config())
        records = latest_versions(handler.list_all_documents(
            limit=1000, include_semantic_text=True,
        ))
        pending = [
            record for record in records
            if not stored_embedding(record, embedder.model_id)
        ]
        with semantic_index_lock:
            semantic_index_state.update({
                "status": "running", "total": len(records),
                "indexed": len(records) - len(pending), "remaining": len(pending),
                "errors": 0,
            })
        if pending:
            workers = min(max(int(os.getenv("SEMANTIC_INDEX_WORKERS", "8")), 2), 12)
            print(
                f"[SEMANTIC INDEX] Backfilling {len(pending)} latest SOW(s) "
                f"with {workers} workers", flush=True,
            )
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_backfill_semantic_record, record): record
                    for record in pending
                }
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        errors += 1
                        record = futures[future]
                        print(
                            f"[SEMANTIC INDEX] Could not index "
                            f"{record.get('document_id')}: {exc}", flush=True,
                        )
                    finally:
                        with semantic_index_lock:
                            semantic_index_state["indexed"] += 1
                            semantic_index_state["remaining"] = max(
                                0, semantic_index_state["remaining"] - 1
                            )
                            semantic_index_state["errors"] = errors
        with semantic_index_lock:
            semantic_index_state["status"] = "ready" if not errors else "partial"
        print(
            f"[SEMANTIC INDEX] Backfill complete; latest={len(records)}; errors={errors}",
            flush=True,
        )
    except Exception as exc:
        with semantic_index_lock:
            semantic_index_state.update({"status": "failed", "errors": errors + 1})
        print(f"[SEMANTIC INDEX] Backfill failed: {exc}", flush=True)
    finally:
        semantic_index_ready.set()


def _start_semantic_index_backfill(force=False):
    """Start the persistent migration once without blocking a web request."""
    with semantic_index_lock:
        if semantic_index_state["status"] == "running":
            return dict(semantic_index_state)
        if semantic_index_state["status"] == "ready" and not force:
            return dict(semantic_index_state)
        semantic_index_state["status"] = "running"
        semantic_index_ready.clear()
        threading.Thread(
            target=_run_semantic_index_backfill,
            name="semantic-index-backfill",
            daemon=True,
        ).start()
        return dict(semantic_index_state)


@app.route('/api/auth/login', methods=['POST'])
def login_user():
    data = request.get_json(silent=True) or {}
    identity = rbac_store.authenticate(str(data.get("email", "")), str(data.get("password", "")))
    if not identity:
        stored = rbac_store.get_user(str(data.get("email", "")))
        if stored and stored.get("status") == "pending_verification":
            return jsonify({
                "success": False,
                "error": "Verify your email address before signing in",
                "verification_required": True,
            }), 403
        return jsonify({"success": False, "error": "Invalid email or password"}), 401
    return jsonify({
        "success": True,
        "token": issue_token(identity),
        "user": identity.public_dict(),
        "business_units": list(BUSINESS_UNITS),
    })


@app.route('/api/auth/signup', methods=['POST'])
def signup_user():
    data = request.get_json(silent=True) or {}
    if str(data.get("password", "")) != str(data.get("confirm_password", "")):
        return jsonify({"success": False, "error": "Passwords do not match"}), 400
    try:
        user, nonce = rbac_store.register_user(
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            email=data.get("email", ""),
            employee_id=data.get("employee_id", ""),
            business_unit=data.get("business_unit", ""),
            password=data.get("password", ""),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        logging.getLogger(__name__).exception("Signup account storage failed")
        return jsonify({"success": False, "error": "Account registration could not be completed"}), 500
    try:
        token = issue_verification_token(user["email"], nonce)
        send_verification_email(user["email"], token)
        logging.getLogger(__name__).info("Verification email sent to %s", user["email"])
        return jsonify({
            "success": True,
            "message": "Account created. Check your email to verify your account.",
            "verification_attempted": True,
        }), 201
    except Exception:
        logging.getLogger(__name__).exception("Signup verification email failed")
        return jsonify({
            "success": False,
            "error": "The account was created, but the verification email could not be sent. Use resend verification.",
            "verification_required": True,
            "verification_attempted": True,
        }), 503


@app.route('/api/auth/verify', methods=['POST'])
def verify_signup():
    data = request.get_json(silent=True) or {}
    try:
        email, nonce = verify_verification_token(str(data.get("token", "")))
        user = rbac_store.verify_registration(email, nonce)
        return jsonify({"success": True, "message": "Account verified. You can now sign in.", "user": user})
    except SignatureExpired:
        return jsonify({"success": False, "error": "Verification link has expired"}), 400
    except (BadSignature, KeyError, ValueError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Verification link is invalid"
        return jsonify({"success": False, "error": message}), 400


@app.route('/api/auth/resend-verification', methods=['POST'])
def resend_signup_verification():
    data = request.get_json(silent=True) or {}
    try:
        email = RBACStore._normalise_shellkode_email(data.get("email", ""))
        nonce = rbac_store.renew_verification(email)
        send_verification_email(email, issue_verification_token(email, nonce))
        return jsonify({"success": True, "message": "Verification email sent."})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception:
        logging.getLogger(__name__).exception("Resending verification email failed")
        return jsonify({"success": False, "error": "Verification email could not be sent"}), 503


@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    """Send a reset link without revealing whether the supplied account exists."""
    data = request.get_json(silent=True) or {}
    generic = "If an active account exists for that address, a password reset link has been sent."
    try:
        challenge = rbac_store.begin_password_reset(str(data.get("email", "")))
        if challenge:
            email, nonce = challenge
            send_password_reset_email(email, issue_password_reset_token(email, nonce))
            logging.getLogger(__name__).info("Password reset email sent to %s", email)
    except Exception:
        # The public response remains identical to prevent account discovery.
        logging.getLogger(__name__).exception("Password reset request could not be delivered")
    return jsonify({"success": True, "message": generic}), 200


@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json(silent=True) or {}
    password = str(data.get("password", ""))
    if password != str(data.get("confirm_password", "")):
        return jsonify({"success": False, "error": "Passwords do not match"}), 400
    try:
        email, nonce = verify_password_reset_token(str(data.get("token", "")))
        rbac_store.reset_password(email, nonce, password)
        return jsonify({"success": True, "message": "Password updated. You can now sign in."})
    except SignatureExpired:
        return jsonify({"success": False, "error": "Password reset link has expired"}), 400
    except (BadSignature, KeyError, ValueError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Password reset link is invalid"
        return jsonify({"success": False, "error": message}), 400


@app.route('/api/auth/change-password-request', methods=['POST'])
def request_authenticated_password_change():
    """Email a reset link to the authenticated account only."""
    identity = current_identity()
    try:
        challenge = rbac_store.begin_password_reset(identity.email)
        if not challenge:
            return jsonify({"success": False, "error": "Account is not eligible for a password change"}), 400
        email, nonce = challenge
        send_password_reset_email(email, issue_password_reset_token(email, nonce))
        logging.getLogger(__name__).info("Password change email sent to %s", email)
        return jsonify({"success": True, "message": "Password reset link sent to your email."})
    except Exception:
        logging.getLogger(__name__).exception("Authenticated password change email failed")
        return jsonify({"success": False, "error": "Password reset email could not be sent"}), 503


@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    return jsonify({
        "success": True,
        "user": current_identity().public_dict(),
        "business_units": list(BUSINESS_UNITS),
    })


@app.route('/api/admin/users', methods=['GET', 'POST'])
def manage_users():
    denied = _require_admin_response()
    if denied:
        return denied
    try:
        if request.method == 'GET':
            return jsonify({
                "success": True,
                "users": rbac_store.list_users(),
                "business_units": list(BUSINESS_UNITS),
            })
        data = request.get_json(silent=True) or {}
        user = rbac_store.create_user(
            email=data.get("email", ""),
            name=data.get("name", ""),
            role=data.get("role", "USER"),
            roles=data.get("roles"),
            business_unit=data.get("business_unit"),
            password=data.get("password", ""),
            created_by=current_identity().email,
            employee_id=data.get("employee_id", ""),
        )
        return jsonify({"success": True, "user": user}), 201
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logging.getLogger(__name__).exception("User management failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route('/api/admin/users/<path:email>', methods=['PUT', 'DELETE'])
def manage_user(email):
    denied = _require_admin_response()
    if denied:
        return denied
    email = str(email).casefold().strip()
    if request.method == 'DELETE' and email == current_identity().email.casefold():
        return jsonify({"success": False, "error": "You cannot delete your own administrator account"}), 400
    try:
        if request.method == 'DELETE':
            rbac_store.delete_user(email)
            return jsonify({"success": True})
        updates = request.get_json(silent=True) or {}
        if email == current_identity().email.casefold():
            requested_roles = [
                str(role).upper() for role in updates.get("roles", [updates.get("role", "ADMIN")])
            ]
            requested_status = str(updates.get("status", "active")).casefold()
            if "ADMIN" not in requested_roles or requested_status != "active":
                return jsonify({
                    "success": False,
                    "error": "You cannot remove your own administrator access or deactivate your account",
                }), 400
        user = rbac_store.update_user(email, updates, current_identity().email)
        return jsonify({"success": True, "user": user})
    except LookupError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logging.getLogger(__name__).exception("User management failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route('/api/sow-sections', methods=['GET', 'POST'])
def manage_sow_sections():
    if request.method == 'GET':
        return jsonify({"success": True, "sections": rbac_store.list_sections()})
    denied = _require_admin_response()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    label = str(data.get("label", "")).strip()
    if not label:
        return jsonify({"success": False, "error": "label is required"}), 400
    sections = rbac_store.list_sections()
    section_id = slugify_section_id(str(data.get("id") or label))
    if section_id in {"deliverables", "scope_at_a_glance", "deliverable_scope_at_a_glance"} or label.casefold() == "deliverables":
        return jsonify({
            "success": False,
            "error": "Deliverables are generated within Scope of Work and cannot be added as a separate section",
        }), 400
    if any(item.get("id") == section_id for item in sections):
        return jsonify({"success": False, "error": "A section with this id already exists"}), 409
    modes = data.get("modes") or ["poc", "production", "poc-to-production"]
    section = {
        "id": section_id,
        "label": label,
        "modes": modes,
        "prompt": str(data.get("prompt", "")).strip() or f"Write a concise, source-grounded {label} section.",
        "custom": True,
    }
    sections.append(section)
    rbac_store.save_sections(sections, current_identity().email)
    return jsonify({"success": True, "section": section, "sections": sections}), 201


@app.route('/api/sow-sections/<section_id>', methods=['PUT', 'DELETE'])
def update_sow_section(section_id):
    denied = _require_admin_response()
    if denied:
        return denied
    sections = rbac_store.list_sections()
    index = next((i for i, item in enumerate(sections) if item.get("id") == section_id), None)
    if index is None:
        return jsonify({"success": False, "error": "Section not found"}), 404
    if request.method == 'DELETE':
        sections.pop(index)
    else:
        data = request.get_json(silent=True) or {}
        sections[index] = {
            **sections[index],
            "label": str(data.get("label", sections[index].get("label", ""))).strip(),
            "modes": data.get("modes", sections[index].get("modes", [])),
            "prompt": str(data.get("prompt", sections[index].get("prompt", ""))).strip(),
        }
    rbac_store.save_sections(sections, current_identity().email)
    return jsonify({"success": True, "sections": sections})


@app.route('/api/custom-templates', methods=['GET'])
def list_custom_templates():
    """List shared presets; every authenticated user may use every preset."""
    identity = current_identity()
    try:
        templates = CustomTemplateStore().list_saved(identity.email, identity.is_admin)
        return jsonify({"success": True, "templates": templates})
    except Exception as exc:
        logging.getLogger(__name__).exception("Could not list custom templates")
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route('/api/custom-templates/extract', methods=['POST'])
def extract_custom_template():
    """Extract one uploaded SOW into sanitised, reusable Markdown guidance."""
    files = [item for item in request.files.getlist('template_file') if item and item.filename]
    if len(files) != 1:
        return jsonify({"success": False, "error": "Upload exactly one template document"}), 400
    upload = files[0]
    extension = Path(upload.filename).suffix.lower()
    if extension not in {'.doc', '.docx', '.pdf'}:
        return jsonify({
            "success": False,
            "error": "Custom templates must be a DOC, DOCX, or PDF file",
        }), 415
    extraction_id = uuid.uuid4().hex
    temp_path = None
    try:
        safe_name = secure_filename(upload.filename)
        print(
            f"[CUSTOM TEMPLATE {extraction_id[:8]}] Upload received: {safe_name} "
            f"({request.content_length or 0:,} request bytes)", flush=True,
        )
        temp_path = Path(app.config['UPLOAD_FOLDER']) / f"template_{extraction_id}_{safe_name}"
        upload.save(temp_path)
        identity = current_identity()
        with custom_template_extraction_lock:
            custom_template_extractions[extraction_id] = {
                "extraction_id": extraction_id,
                "status": "processing",
                "owner_email": identity.email,
                "source_filename": safe_name,
                "created_at": datetime.now().isoformat(),
            }
        threading.Thread(
            target=_process_custom_template_extraction,
            args=(extraction_id, temp_path, safe_name, identity.email, identity.name),
            daemon=True,
        ).start()
        print(
            f"[CUSTOM TEMPLATE {extraction_id[:8]}] Queued background extraction",
            flush=True,
        )
        return jsonify({
            "success": True, "extraction_id": extraction_id, "status": "processing",
        }), 202
    except Exception as exc:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        logging.getLogger(__name__).exception("Custom template extraction failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route('/api/custom-templates/extractions/<extraction_id>', methods=['GET'])
def custom_template_extraction_status(extraction_id):
    with custom_template_extraction_lock:
        extraction = dict(custom_template_extractions.get(extraction_id) or {})
    if not extraction:
        # A ready result remains recoverable from Dynamo after a server restart.
        try:
            template = CustomTemplateStore().get(extraction_id)
        except Exception:
            template = None
        if template:
            extraction = {
                "extraction_id": extraction_id,
                "status": "ready",
                "owner_email": template.get("owner_email"),
                "template": CustomTemplateStore._public(
                    template, current_identity().email, current_identity().is_admin
                ),
            }
        else:
            return jsonify({"success": False, "error": "Template extraction not found"}), 404
    identity = current_identity()
    if not identity.is_admin and str(extraction.get("owner_email") or "").casefold() != identity.email.casefold():
        return jsonify({"success": False, "error": "You do not have access to this extraction"}), 403
    return jsonify({
        "success": extraction.get("status") != "failed",
        "extraction_id": extraction_id,
        "status": extraction.get("status"),
        "template": extraction.get("template"),
        "error": extraction.get("error"),
    })


@app.route('/api/custom-templates/<template_id>/save', methods=['POST'])
def save_custom_template(template_id):
    try:
        template = CustomTemplateStore().save_preset(
            template_id,
            (request.get_json(silent=True) or {}).get("name", ""),
            current_identity().email,
        )
        return jsonify({"success": True, "template": template})
    except LookupError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@app.route('/api/custom-templates/<template_id>', methods=['GET', 'DELETE'])
def custom_template_detail(template_id):
    store = CustomTemplateStore()
    identity = current_identity()
    try:
        item = store.get(template_id)
        if not item:
            raise LookupError("Custom template not found")
        if request.method == 'GET':
            return jsonify({
                "success": True,
                "template": store._public(item, identity.email, identity.is_admin),
            })
        store.delete(template_id, identity.email, identity.is_admin)
        with custom_template_extraction_lock:
            custom_template_extractions.pop(template_id, None)
        return jsonify({"success": True})
    except LookupError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403

# Folder mapping for cloud storage
FOLDER_MAPPING = {
    "POC": "poc",
    "PROD": "production",
    "POC_TO_PROD": "poc_to_prod"
}

# ============================================================================
# TASK QUEUE MANAGEMENT
# ============================================================================

# Global task storage
tasks = {}
task_lock = threading.Lock()

class TaskStatus:
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

def create_task(task_id, mode, metadata):
    """Create a new task"""
    with task_lock:
        tasks[task_id] = {
            "task_id": task_id,
            "status": TaskStatus.QUEUED,
            "mode": mode,
            "metadata": metadata,
            "progress": 0,
            "current_step": "Initializing...",
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "result": None,
            "error": None
        }
        print(f"[DEBUG] Task {task_id} created. Total tasks: {len(tasks)}")
        return tasks[task_id]

def update_task(task_id, **kwargs):
    """Update task status with validation"""
    with task_lock:
        if task_id not in tasks:
            print(f"[DEBUG] WARNING: Attempted to update non-existent task {task_id}")
            return False
        
        # Validate progress value
        if 'progress' in kwargs:
            progress = kwargs['progress']
            if not (0 <= progress <= 100):
                print(f"[WARNING] Invalid progress value: {progress}, clamping to 0-100")
                kwargs['progress'] = max(0, min(100, progress))
        
        # Validate status transitions
        if 'status' in kwargs:
            current_status = tasks[task_id]['status']
            new_status = kwargs['status']
            
            # Define valid transitions
            valid_transitions = {
                TaskStatus.QUEUED: [TaskStatus.PROCESSING, TaskStatus.FAILED],
                TaskStatus.PROCESSING: [TaskStatus.COMPLETED, TaskStatus.FAILED],
                TaskStatus.COMPLETED: [],  # Terminal state
                TaskStatus.FAILED: []  # Terminal state
            }
            
            if new_status not in valid_transitions.get(current_status, []):
                print(f"[WARNING] Invalid status transition: {current_status} -> {new_status}")
                return False
        
        tasks[task_id].update(kwargs)
        task = tasks[task_id]
        print(
            f"[TASK {task_id}] {task.get('status')} | "
            f"{int(task.get('progress', 0) or 0):3d}% | "
            f"{task.get('current_step', '')}",
            flush=True,
        )
        return True

def get_task(task_id):
    """Get task by ID"""
    with task_lock:
        task = tasks.get(task_id)
        if task:
            print(f"[DEBUG] Retrieved task {task_id}: status={task.get('status')}")
        return task

def cleanup_old_tasks():
    """
    ✅ FIX #3: Enhanced cleanup - removes both completed and stuck tasks
    Background task to clean up:
    - Completed/failed tasks older than 1 hour
    - Stuck tasks (queued/processing) older than 30 minutes
    """
    while True:
        time.sleep(300)  # Run every 5 minutes

        try:
            with task_lock:
                current_time = datetime.now()
                tasks_to_remove = []

                for task_id, task in list(tasks.items()):
                    created_at = datetime.fromisoformat(task['created_at'])
                    age_seconds = (current_time - created_at).total_seconds()
                    task_status = task.get('status')

                    # Clean up completed/failed tasks after 1 hour
                    if task_status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                        if age_seconds > 3600:  # 1 hour
                            tasks_to_remove.append((task_id, task_status, age_seconds))
                    
                    # ✅ NEW: Clean up stuck tasks after 30 minutes
                    elif task_status in [TaskStatus.QUEUED, TaskStatus.PROCESSING]:
                        if age_seconds > 1800:  # 30 minutes
                            print(f"[CLEANUP] Found stuck task: {task_id} (status: {task_status}, age: {age_seconds:.0f}s)")
                            tasks_to_remove.append((task_id, f"stuck-{task_status}", age_seconds))

                for task_id, reason, age in tasks_to_remove:
                    del tasks[task_id]
                    print(f"[CLEANUP] Removed task {task_id} (reason: {reason}, age: {age:.0f}s)")

                if tasks_to_remove:
                    print(f"[CLEANUP] Cleaned up {len(tasks_to_remove)} tasks. Remaining: {len(tasks)}")

        except Exception as e:
            print(f"[CLEANUP] Error: {e}")
            import traceback
            traceback.print_exc()

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_tasks, daemon=True)
cleanup_thread.start()
print("[STARTUP] Task cleanup thread started")

# ============================================================================
# ACTIVE TASKS TO DOCUMENTS CONVERSION
# ============================================================================

def get_active_tasks_as_documents(mode_filter=None):
    """
    ✅ ENHANCED: Convert active in-memory tasks to match task status API structure
    Returns list of task objects with full document details
    
    Args:
        mode_filter: Optional mode filter (POC, PROD, POC_TO_PROD)
        
    Returns:
        list: List of task objects matching /api/task/<id> response structure
    """
    with task_lock:
        active_docs = []
        
        for task_id, task in tasks.items():
            # Only include tasks that are actively running (not completed/failed)
            if task.get('status') in [TaskStatus.QUEUED, TaskStatus.PROCESSING]:
                task_mode = task.get('mode')
                
                # Apply mode filter if specified
                if mode_filter and task_mode != mode_filter:
                    continue
                
                metadata = task.get('metadata', {})
                
                # ✅ Create task object matching /api/task/<id> structure
                task_obj = {
                    "success": True,
                    "source": "memory",
                    "is_processing": True,  # Flag to identify as active task
                    "note": "Task in progress",
                    
                    # Task details (matching /api/task/<id> response)
                    "task": {
                        "task_id": task_id,
                        "status": task.get('status'),
                        "mode": task_mode,
                        "progress": task.get('progress', 0),
                        "current_step": task.get('current_step', 'Initializing...'),
                        "created_at": task.get('created_at'),
                        "metadata": {
                            "company_name": metadata.get('company_name', 'Unknown'),
                            "project_name": metadata.get('project_name', 'Generating...'),
                        "author_name": metadata.get('author_name', 'Unknown'),
                        "business_unit": metadata.get('business_unit'),
                        "owner_email": metadata.get('owner_email'),
                        "owner_name": metadata.get('owner_name'),
                        }
                    },
                    
                    # Partial document details (will be populated on completion)
                    "document": {
                        "document_id": task_id,
                        "task_id": task_id,
                        "project_name": metadata.get('project_name', 'Generating...'),
                        "project_name_lower": metadata.get('project_name', 'generating...').lower(),
                        "customer_name": metadata.get('company_name', 'Unknown'),
                        "customer_name_lower": metadata.get('company_name', 'unknown').lower(),
                        "author_name": metadata.get('author_name', 'Unknown'),
                        "author_name_lower": metadata.get('author_name', 'unknown').lower(),
                        "document_date": datetime.now().strftime("%d %B %Y"),
                        "mode": task_mode,
                        "timestamp": task.get('created_at'),
                        "s3_url": None,  # Will be populated on completion
                        "drive_link": None,  # ✅ Will be populated on completion
                        "file_size": None,  # Will be populated on completion
                        "business_unit": metadata.get('business_unit'),
                        "owner_email": metadata.get('owner_email'),
                        "owner_name": metadata.get('owner_name'),
                    }
                }
                
                active_docs.append(task_obj)
        
        if active_docs:
            print(f"[MERGE] Found {len(active_docs)} active tasks (filter: {mode_filter or 'all'})")
        
        return active_docs


def convert_db_document_to_task_format(document):
    """
    ✅ ENHANCED: Convert DynamoDB document to match task status API structure with drive_link
    
    Args:
        document: Document from DynamoDB
        
    Returns:
        dict: Formatted object matching /api/task/<id> structure
    """
    # Ensure document includes drive_link field
    doc_copy = document.copy()
    
    # ✅ Add drive_link if it exists in the document (check multiple possible field names)
    if 'drive_link' not in doc_copy:
        if 'google_drive_link' in doc_copy:
            doc_copy['drive_link'] = doc_copy['google_drive_link']
        elif 'gdrive_link' in doc_copy:
            doc_copy['drive_link'] = doc_copy['gdrive_link']
    
    return {
        "success": True,
        "source": "database",
        "is_processing": False,
        "note": "Task completed and cleaned from memory",
        
        "task": {
            "task_id": doc_copy.get('task_id', doc_copy.get('document_id')),
            "status": doc_copy.get('status', 'completed'),
            "mode": doc_copy.get('mode'),
            "progress": 100,
            "current_step": "Draft saved" if doc_copy.get('status') == 'draft' else "Completed",
            "metadata": {
                "company_name": doc_copy.get('customer_name', 'Unknown'),
                "project_name": doc_copy.get('project_name', 'Unknown'),
                "author_name": doc_copy.get('author_name', 'Unknown'),
                "business_unit": doc_copy.get('business_unit'),
                "owner_email": doc_copy.get('owner_email'),
                "owner_name": doc_copy.get('owner_name'),
            }
        },
        
        "document": doc_copy  # ✅ Includes drive_link if present
    }


def merge_with_active_tasks(db_documents, mode_filter=None, limit=50):
    """
    ✅ ENHANCED: Merge completed documents from DB with active in-memory tasks
    Both sources now return the same structure as /api/task/<id> with drive_link
    
    Args:
        db_documents: List of documents from DynamoDB
        mode_filter: Optional mode filter (POC, PROD, POC_TO_PROD)
        limit: Maximum number of results to return
    
    Returns:
        Merged and sorted list of task objects (matching /api/task/<id> structure)
    """
    def safe_timestamp(doc):
        """Safely extract timestamp for sorting"""
        # Try to get timestamp from document object first
        doc_data = doc.get('document', {})
        ts = doc_data.get('timestamp') or doc.get('timestamp', '')
        
        if not ts:
            return datetime.min  # Push invalid timestamps to bottom
        
        try:
            # Handle ISO format strings
            if isinstance(ts, str):
                # Remove 'Z' and parse
                ts_clean = ts.replace('Z', '+00:00')
                return datetime.fromisoformat(ts_clean)
            # If already datetime object
            elif isinstance(ts, datetime):
                return ts
            else:
                return datetime.min
        except (ValueError, AttributeError) as e:
            print(f"[WARNING] Invalid timestamp format: {ts} - {e}")
            return datetime.min
    
    # Convert DB documents to task format (now includes drive_link)
    formatted_db_docs = []
    for doc in (db_documents or []):
        formatted_db_docs.append(convert_db_document_to_task_format(doc))
    
    # Get active tasks (already in correct format)
    active_tasks = get_active_tasks_as_documents(mode_filter)
    
    # Merge both lists
    persisted_tasks = {d.get('document', {}).get('task_id') for d in formatted_db_docs}
    persisted_ids = {d.get('document', {}).get('document_id') for d in formatted_db_docs}
    active_tasks = [d for d in active_tasks
                    if d.get('task', {}).get('task_id') not in persisted_tasks
                    and d.get('document', {}).get('document_id') not in persisted_ids]
    all_documents = formatted_db_docs + active_tasks
    
    # ✅ Sort by timestamp with safe extraction (most recent first)
    try:
        all_documents.sort(key=safe_timestamp, reverse=True)
    except Exception as e:
        print(f"[ERROR] Sorting failed: {e}")
        # Fallback: keep original order
    
    # Apply limit
    result = all_documents[:limit]
    
    if active_tasks or formatted_db_docs:
        print(f"[MERGE] Results: {len(formatted_db_docs)} DB docs + {len(active_tasks)} active = {len(result)} total (limited to {limit})")
    
    return result

# ============================================================================
# S3 HELPER FUNCTIONS
# ============================================================================

def get_s3_client():
    """Initialize S3 client with explicit credentials from environment"""
    try:
        config = Config()
        return boto3.client(
            service_name='s3',
            region_name=config.AWS_REGION,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
            config=config.BOTO_CONFIG
        )
    except Exception as e:
        print(f"Error initializing S3 client: {e}")
        return None


def _delete_draft_record(record):
    """Remove a persisted draft and both of its S3 artifacts."""
    if not record:
        return
    handler = DynamoDBHandler()
    for url_field in ("s3_url", "draft_preview_s3_url"):
        location = str(record.get(url_field) or "").strip()
        if not location:
            continue
        try:
            bucket, key = parse_s3_location(location)
            get_s3_client().delete_object(Bucket=bucket, Key=key)
        except Exception as exc:
            print(f"[DRAFT] Could not remove {url_field}: {exc}", flush=True)
    handler.delete_document(
        str(record.get("document_id") or ""), str(record.get("timestamp") or "")
    )
    try:
        AccountHandler().delete_sow(str(record.get("document_id") or ""))
    except Exception as exc:
        print(f"[DRAFT] Could not unlink project draft: {exc}", flush=True)


def _cleanup_replaced_draft_artifacts(record, s3_url, snapshot_url=None):
    """Only clean old files after replacement metadata has committed."""
    for location in (record.get("s3_url"), record.get("draft_preview_s3_url")):
        if not location or location in {s3_url, snapshot_url}:
            continue
        try:
            bucket, key = parse_s3_location(location)
            get_s3_client().delete_object(Bucket=bucket, Key=key)
        except Exception as exc:
            print(f"[DRAFT] Replaced artifact cleanup deferred: {exc}", flush=True)


def _save_preview_as_draft(preview_id, automatic=False, revision_candidate=None):
    """Persist a ready preview as an ordinary version marked draft."""
    existing = DynamoDBHandler().query_by_task_id(preview_id)
    with preview_lock:
        live = preview_storage.get(preview_id)
        draft_id = (live or {}).get("metadata", {}).get("draft_document_id")
    # A slow DynamoDB request must not block every status poll behind this lock.
    if draft_id:
        existing = DynamoDBHandler().get_document_by_id(draft_id)
    if existing and (automatic or not live) and revision_candidate is None:
        denied = None if automatic else _resource_denied(existing)
        if denied:
            return {"success": False, "error": "You do not have access to this document"}
        if automatic and live and existing.get("status") == "draft":
            with preview_lock:
                live.setdefault("metadata", {}).update({
                    "draft_document_id": existing["document_id"],
                    "version": existing.get("version"),
                    "draft_original_s3_url": existing.get("s3_url"),
                    "draft_preview_s3_url": existing.get("draft_preview_s3_url"),
                })
                if live.get("status") in {"draft_pending", "ready"}:
                    live.update(status="ready", progress=100, current_step="Preview ready; draft saved")
        return {
            "success": True,
            "document_id": existing.get("document_id"),
            "s3_url": existing.get("s3_url"),
            "status": existing.get("status") or "draft",
            "cached": True,
        }

    with preview_lock:
        preview = preview_storage.get(preview_id)
        if not preview:
            return {"success": False, "error": "Preview not found"}
        if preview.get("status") == "draft_saving":
            return {"success": False, "processing": True, "status": "draft_saving"}
        allowed = {"ready", "draft_pending"} if revision_candidate is None else {"architecture_regenerating"}
        if preview.get("status") not in allowed:
            return {"success": False, "error": "Only a completed preview can be saved as draft"}
        if revision_candidate is not None and (
                preview.get('edit_count', 0) != revision_candidate.get('edit_count', 1) - 1
                or (preview.get('architecture_job') or {}).get('id') != revision_candidate.get('_architecture_job_id')):
            return {'success': False, 'error': 'Preview changed during regeneration; revision was not applied'}
        preview["status"] = "draft_saving"
        preview["current_step"] = "Saving draft"
        snapshot = copy.deepcopy(revision_candidate if revision_candidate is not None else preview)

    upload_file = None
    snapshot_location = None
    s3_url = None
    db_persisted = False
    try:
        metadata = dict(snapshot.get("metadata") or {})
        content = snapshot.get("content") or {}
        mode = str(snapshot.get("mode") or "POC")
        token_usage = snapshot.get("token_usage") or {}
        total_tokens = int(snapshot.get("total_tokens") or token_usage.get("total_tokens") or 0)
        old_draft_id = str(metadata.get("draft_document_id") or "").strip()

        final_state = {
            "metadata": metadata, "mode": mode, "poc_content": content,
            "validated_requirements": {}, "analyzed_requirements": {},
            "source_file": None,
            "output_path": None, "json_path": None, "errors": [], "current_step": "build",
        }
        from app.core.nodes import pdf_build_node
        final_state = pdf_build_node(final_state)
        if final_state.get("errors"):
            raise RuntimeError(f"Draft document build failed: {final_state['errors']}")
        upload_file = final_state.get("output_path")
        if not upload_file or not Path(upload_file).exists():
            raise RuntimeError("Draft document build produced no file")

        # Drafts need durable S3 storage, not publication to the final Drive folder.
        drive_result = None
        s3_result = upload_to_s3(upload_file, mode=FOLDER_MAPPING.get(mode, mode))
        if not s3_result:
            raise RuntimeError("Draft could not be uploaded to S3")
        s3_url = s3_result.get("https_url") or s3_result.get("s3_url") or s3_result.get("url")
        if not s3_url:
            raise RuntimeError("Draft upload returned no S3 location")

        s3_client = get_s3_client()
        bucket = str(s3_result.get("bucket") or parse_s3_location(s3_url)[0])
        snapshot_key = f"draft-previews/{preview_id}-{uuid.uuid4().hex}.json"
        durable_snapshot = {
            "preview_id": preview_id, "mode": mode, "metadata": metadata,
            "content": content, "final_state": snapshot.get("final_state") or {},
            "token_usage": token_usage, "total_tokens": total_tokens,
            "edit_count": snapshot.get('edit_count', 0),
            "architecture_changes": snapshot.get('architecture_changes', []),
            "saved_at": datetime.now().isoformat(),
        }
        s3_client.put_object(
            Bucket=bucket,
            Key=snapshot_key,
            Body=json.dumps(durable_snapshot, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        snapshot_location = f"s3://{bucket}/{snapshot_key}"
        drive_link = (drive_result or {}).get("link") or (drive_result or {}).get("url")
        db_result = save_to_dynamodb(
            metadata={
                "company_name": metadata.get("company_name"),
                "author_name": metadata.get("author_name"),
                "project_name": metadata.get("project_title"),
                "document_date": metadata.get("document_date"),
                "mode": mode,
                "business_unit": metadata.get("business_unit"),
                "owner_email": metadata.get("owner_email"),
                "owner_name": metadata.get("owner_name"),
                "total_tokens": total_tokens,
                "token_usage": token_usage,
                "status": "draft",
                "draft_preview_s3_url": snapshot_location,
                "preview_id": preview_id,
                "aws_pricing": _pricing_audit_record(
                    (snapshot.get("final_state") or {}).get("pricing_result")
                ),
                "source_documents": metadata.get("source_documents", []),
                "source_scope_id": metadata.get("source_scope_id"),
                "parent_document_id": metadata.get("parent_document_id"),
                "refinement_instructions": metadata.get("refinement_instructions"),
                "selected_sow_sections": metadata.get("selected_sow_sections", []),
                "timeline_format": metadata.get("timeline_format", "table"),
                **_semantic_index_metadata(content, metadata),
            },
            s3_url=s3_url,
            s3_result=s3_result,
            drive_link=drive_link,
            table_name=os.getenv("DYNAMODB_TABLE_POC_DOCUMENTS", "agentic-poc"),
            region=os.getenv("AWS_REGION", "us-east-1"),
            task_id=preview_id,
            account_id=metadata.get("account_id"),
            project_id=metadata.get("project_id"),
            existing_document_id=(existing or {}).get("document_id"),
        )
        if not db_result or not db_result.get("success") or not db_result.get("document_id"):
            raise RuntimeError((db_result or {}).get("error") or "Draft metadata could not be saved")
        db_persisted = True
        if existing:
            _cleanup_replaced_draft_artifacts(existing, s3_url, snapshot_location)

        document_id = db_result["document_id"]
        with preview_lock:
            live = preview_storage.get(preview_id)
            if live:
                live.setdefault("metadata", {}).update({
                    "draft_document_id": document_id,
                    "version": db_result.get("version"),
                    "draft_original_s3_url": s3_url,
                    "draft_preview_s3_url": snapshot_location,
                })
        if metadata.get("project_id"):
            try:
                AccountHandler().link_sow_to_project(metadata["project_id"], document_id, {
                "mode": mode, "customer_name": metadata.get("company_name"),
                "project_name": metadata.get("project_title"),
                "author_name": metadata.get("author_name"), "drive_link": drive_link,
                "s3_url": s3_url, "sow_db_id": document_id,
                "document_date": metadata.get("document_date"),
                "created_at": datetime.now().isoformat(), "status": "draft",
                "business_unit": metadata.get("business_unit"),
                "owner_email": metadata.get("owner_email"),
                "owner_name": metadata.get("owner_name"), "total_tokens": total_tokens,
                })
            except Exception as exc:
                # The authoritative draft has committed. A secondary dashboard
                # link must not report failure or leave the live preview stale.
                print(f'[DRAFT] Project link refresh deferred: {exc}', flush=True)

        if old_draft_id and old_draft_id != document_id:
            try:
                old_record = DynamoDBHandler().get_document_by_id(old_draft_id)
                if old_record and str(old_record.get("status") or "").lower() == "draft":
                    _delete_draft_record(old_record)
            except Exception as exc:
                print(f'[DRAFT] Superseded draft cleanup deferred: {exc}', flush=True)

        if automatic:
            with preview_lock:
                live = preview_storage.get(preview_id)
                if live:
                    if revision_candidate is not None:
                        live.setdefault('metadata', {}).update(revision_candidate.get('metadata') or {})
                        for field in ('content', 'final_state', 'edit_count', 'token_usage', 'total_tokens', 'architecture_changes'):
                            if field in revision_candidate:
                                live[field] = revision_candidate[field]
                        live['last_modified'] = datetime.now().isoformat()
                    live.setdefault("metadata", {}).update({
                        "draft_document_id": document_id,
                        "version": db_result.get('version'),
                        "draft_original_s3_url": s3_url,
                        "draft_preview_s3_url": snapshot_location,
                    })
                    live.update(status="ready", progress=100, current_step="Preview ready; draft saved", draft_error=None)
                    if isinstance(live.get('final_state'), dict):
                        live['final_state']['metadata'] = copy.deepcopy(live['metadata'])
                    live["autosaved_draft"] = True
            return {"success": True, "document_id": document_id, "status": "draft", "automatic": True}
        delete_preview_data(preview_id)
        from app.core.nodes import clear_token_usage
        clear_token_usage(preview_id)
        # Draft previews need not have a task entry. Durable record lookup is
        # the recovery path after deletion or a server restart.
        if get_task(preview_id):
            update_task(preview_id, status=TaskStatus.COMPLETED, progress=100,
                        current_step="Saved as draft", completed_at=datetime.now().isoformat(),
                        result={"document_id": document_id, "s3_url": s3_url,
                                "drive_link": drive_link, "is_draft": True})
        print(
            f"[DRAFT] {'Automatically s' if automatic else 'S'}aved {preview_id} "
            f"as document {document_id}", flush=True,
        )
        return {
            "success": True, "document_id": document_id, "s3_url": s3_url,
            "drive_link": drive_link, "status": "draft", "automatic": automatic,
        }
    except Exception as exc:
        # Avoid leaving unreferenced S3 objects if persistence failed before a
        # DynamoDB record was committed. Once committed, retries use task-id
        # idempotency and the files must remain intact.
        if not db_persisted:
            for location in (snapshot_location, s3_url):
                if not location:
                    continue
                try:
                    bucket, key = parse_s3_location(location)
                    get_s3_client().delete_object(Bucket=bucket, Key=key)
                except Exception as cleanup_exc:
                    print(f"[DRAFT] Orphan cleanup skipped: {cleanup_exc}", flush=True)
        with preview_lock:
            if preview_id in preview_storage:
                preview_storage[preview_id]["status"] = "ready"
                preview_storage[preview_id]["progress"] = 100
                preview_storage[preview_id]["current_step"] = "Preview generation complete"
                preview_storage[preview_id]["draft_error"] = str(exc)
                preview_storage[preview_id]["last_activity_at"] = time.time()
        print(f"[DRAFT] Could not save {preview_id}: {exc}", flush=True)
        return {"success": False, "error": str(exc)}
    finally:
        if upload_file:
            try:
                Path(upload_file).unlink(missing_ok=True)
            except OSError:
                pass


def _schedule_preview_auto_draft(preview_id):
    """Retry durable autosave independently of browser activity or login state."""
    with preview_auto_draft_lock:
        if preview_id in preview_auto_draft_threads:
            return
        preview_auto_draft_threads.add(preview_id)

    def monitor():
        try:
            while True:
                time.sleep(15)
                with preview_lock:
                    preview = preview_storage.get(preview_id)
                    if not preview:
                        return
                    status = str(preview.get("status") or "")
                    if status == "failed":
                        return
                    if not preview.get("auto_draft_enabled", True):
                        return
                if status in {"ready", "draft_pending"}:
                    result = _save_preview_as_draft(preview_id, automatic=True)
                    if result.get("success"):
                        return
        finally:
            with preview_auto_draft_lock:
                preview_auto_draft_threads.discard(preview_id)

    threading.Thread(target=monitor, name=f"auto-draft-{preview_id[-8:]}", daemon=True).start()

# ============================================================================
# DOCUMENT PROCESSING HELPERS (PDF OUTPUT)
# ============================================================================
# Note: DOCX to PDF conversion functions removed - DocumentBuilder now outputs PDF directly

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def ensure_output_folders():
    """Ensure output folders exist"""
    output_folder = Path(os.getcwd()) / "generated_documents"
    output_folder.mkdir(parents=True, exist_ok=True)

    poc_folder = output_folder / "POC"
    prod_folder = output_folder / "Production"
    poc_to_prod_folder = output_folder / "POC_to_Production"
    archive_folder = output_folder / "Archive"

    poc_folder.mkdir(parents=True, exist_ok=True)
    prod_folder.mkdir(parents=True, exist_ok=True)
    poc_to_prod_folder.mkdir(parents=True, exist_ok=True)
    archive_folder.mkdir(parents=True, exist_ok=True)

    return {
        "base": output_folder,
        "poc": poc_folder,
        "production": prod_folder,
        "poc_to_prod": poc_to_prod_folder,
        "archive": archive_folder
    }


def get_output_folder(mode, folders):
    """Get appropriate folder based on mode"""
    if mode == "POC":
        return folders["poc"]
    elif mode == "PROD":
        return folders["production"]
    elif mode == "POC_TO_PROD":
        return folders["poc_to_prod"]
    else:
        return folders["base"]


def extract_text_from_document(file_path: str) -> str:
    """Extract text from document using enhanced doc_reader"""
    try:
        print(f"📖 Reading document: {Path(file_path).name}")
        content = read_document(file_path)
        if content and len(content.strip()) > 50:
            print(f"✓ Successfully extracted {len(content)} characters")
            return content
        else:
            print(f"⚠️  Extracted content is very small ({len(content)} chars)")
            return content
    except Exception as e:
        print(f"❌ Error reading document: {e}")
        return None


def extract_metadata_with_llm(text_content: str) -> dict:
    """Extract metadata from document text using LLM"""
    try:
        config = Config()
        bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=config.BEDROCK_REGION,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
            config=config.BOTO_CONFIG
        )

        # Pre-extract author from DOCX properties if available
        docx_author = None
        author_match = re.search(r'^DOCUMENT_AUTHOR:\s*(.+)$', text_content, re.MULTILINE)
        if author_match:
            docx_author = author_match.group(1).strip()
            if docx_author and docx_author.lower() not in ['python-docx', 'python', 'unknown', 'author', 'admin', 'user', '']:
                print(f"   ✅ Found author from document properties: {docx_author}")
            else:
                docx_author = None

        prompt = f"""Extract metadata from this document cover page. Return ONLY a valid JSON object.

FIELD DEFINITIONS:
- company_name: The CLIENT/CUSTOMER company (who is receiving the service, NOT the vendor like Shellkode)
- author_name: The PERSON who wrote/authored the document (look at cover page bottom area, "Prepared by", or "Author" labels)
- author_org: The VENDOR/SERVICE PROVIDER (e.g., Shellkode)
- project_title: The project name EXACTLY as written on the cover page (2-5 words, no prefixes like "POC" or "AI-Powered")
- objective: The main objective/goal (1 sentence)
- document_date: Date in DD Month YYYY format

EXTRACTION RULES:
0. HIGHEST PRIORITY: If you see "DOCUMENT_AUTHOR: <name>" at the start of the text, use that as author_name. If you see "DOCUMENT_TITLE: <title>", use that as project_title. These are the most reliable source.
1. The cover page (first page) has the layout: vendor logo at top, client company in middle, project title below client, author at bottom
2. Extract the project title VERBATIM from the document - do not embellish or add words
3. The author_name is a PERSON (first name or first+last), not a company or role title
4. company_name is the CLIENT, not the vendor (Shellkode is usually the vendor)

Document text (first 3000 chars):
{text_content[:3000]}

Return ONLY valid JSON, no markdown:
{{"company_name": "...", "author_name": "...", "author_org": "...", "project_title": "...", "objective": "...", "document_date": "..."}}
"""

        response_text = BedrockLLM(config, bedrock).generate(
            prompt,
            task="fast",
            max_tokens=500,
            temperature=0.1,
            call_name="Metadata Extraction (App)",
            fallback_model_id=config.ANALYSIS_MODEL_ID,
        ).text

        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
        if json_match:
            try:
                extracted = json.loads(json_match.group())
                extracted['company_name'] = extracted.get('company_name') or "Unknown Company"
                # Use DOCX properties author if LLM didn't find one
                llm_author = extracted.get('author_name', '').strip()
                if llm_author and llm_author.lower() not in ['unknown', 'unknown author', '']:
                    extracted['author_name'] = llm_author
                elif docx_author:
                    extracted['author_name'] = docx_author
                    print(f"   ✅ Using author from DOCX properties: {docx_author}")
                else:
                    extracted['author_name'] = "Unknown Author"
                extracted['author_org'] = extracted.get('author_org') or "Unknown Organization"
                extracted['project_title'] = extracted.get('project_title') or "Unknown Project"
                extracted['objective'] = extracted.get('objective') or "Project Implementation"
                extracted['document_date'] = extracted.get('document_date') or datetime.now().strftime("%d %B %Y")
                extracted['version'] = "1.0"
                extracted['start_date'] = None
                extracted['end_date'] = None
                extracted['timezone'] = "IST"

                # Clean project title - remove LLM embellishments
                if extracted['project_title'] and extracted['project_title'] != "Unknown Project":
                    title = extracted['project_title']
                    # Remove common LLM-added prefixes
                    llm_prefixes = [
                        r'^Intelligent\s+', r'^AI-Powered\s+', r'^AI\s+',
                        r'^Smart\s+', r'^Advanced\s+', r'^Automated\s+',
                        r'^Comprehensive\s+', r'^Integrated\s+',
                        r'^Real-time\s+', r'^Cloud-Based\s+', r'^Enterprise\s+',
                    ]
                    for prefix in llm_prefixes:
                        cleaned = re.sub(prefix, '', title, flags=re.IGNORECASE)
                        if cleaned != title and len(cleaned.strip()) > 3:
                            print(f"   🧹 Cleaned title prefix: '{title}' → '{cleaned.strip()}'")
                            title = cleaned.strip()
                            break
                    extracted['project_title'] = title

                return extracted
            except json.JSONDecodeError:
                return None
        return None
    except Exception as e:
        print(f"❌ LLM extraction error: {e}")
        return None


def extract_metadata_from_document(file_path: str) -> dict:
    """Extract metadata from any document type (PDF/DOCX)"""
    try:
        text_content = extract_text_from_document(file_path)
        if not text_content:
            return None

        print(f"\n📋 Extracting metadata using LLM...")
        extracted = extract_metadata_with_llm(text_content)

        if extracted:
            print(f"✅ Metadata Extraction Complete:")
            print(f"   Company: {extracted.get('company_name')}")
            print(f"   Project: {extracted.get('project_title')}")
            return extracted
        return None
    except Exception as e:
        print(f"❌ Error extracting metadata: {e}")
        return None


def save_document_info(pdf_path, docx_path, metadata, mode, folders, drive_result=None, s3_result=None):
    """Save document information to manifest"""
    try:
        info = {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "company_name": metadata.get("company_name", "Unknown"),
            "author_name": metadata.get("author_name", "Unknown"),
            "uploads": {
                "drive": drive_result['link'] if drive_result else None,
                "s3": s3_result.get('https_url') if s3_result else None
            }
        }

        info_file = Path(os.getcwd()) / "generated_documents" / "document_manifest.json"
        manifest = []

        if info_file.exists():
            try:
                with open(info_file, 'r') as f:
                    manifest = json.load(f)
            except:
                manifest = []

        manifest.append(info)
        with open(info_file, 'w') as f:
            json.dump(manifest, f, indent=2)

        print(f"✓ Document info saved")
        return True
    except Exception as e:
        print(f"⚠ Warning: Could not save document info: {e}")
        return False


# ============================================================================
# BACKGROUND TASK PROCESSOR
# ============================================================================

def process_document_generation(task_id, task_data):
    """Background worker for document generation"""
    uploaded_file_path = task_data.get('uploaded_file_path')
    usage_context_token = None
    print(f"[TASK {task_id}] Background generation started", flush=True)

    try:
        from app.core.nodes import start_token_usage
        usage_context_token = start_token_usage(task_id)
        update_task(task_id, status=TaskStatus.PROCESSING, progress=5, current_step="Validating inputs")

        mode = task_data['mode']
        company_name = task_data.get('company_name')
        author_name = task_data.get('author_name')
        project_name = task_data.get('project_name')
        objective = task_data.get('objective')
        document_date = task_data.get('document_date')
        version = task_data.get('version', '1.0')
        source_file = task_data.get('source_file')

        author_org = "Shellkode"
        author_org_description = "Shellkode specializes in developing advanced data and AI solutions for businesses."

        metadata = {
            "company_name": company_name or "To be extracted from document",
            "author_name": author_name or "To be extracted from document",
            "author_org": author_org,
            "author_org_description": author_org_description,
            "document_date": document_date,
            "version": version,
            "start_date": task_data.get("start_date") or "",
            "end_date": task_data.get("end_date") or "",
            "timezone": "IST",
            "project_title": project_name or "To be extracted from document",
            "selected_sow_sections": task_data.get("selected_sow_sections", []),
            "custom_template_id": task_data.get("custom_template_id"),
            "custom_template_name": task_data.get("custom_template_name"),
            "business_unit": task_data.get("business_unit"),
            "owner_email": task_data.get("owner_email"),
            "owner_name": task_data.get("owner_name"),
        }

        update_task(task_id, progress=10, current_step="Extracting metadata")

        # Extract metadata if needed
        extracted_metadata = None
        if mode == "POC_TO_PROD" and source_file:
            print("\n[TASK] Extracting Metadata from Document")
            extracted_metadata = extract_metadata_from_document(source_file)
            if extracted_metadata:
                # Only use LLM-extracted values for fields the user didn't provide
                placeholder_values = ['to be extracted from document', None, '']

                if not company_name or company_name.lower() in [v for v in placeholder_values if v]:
                    company_name = extracted_metadata.get("company_name", company_name)
                if not project_name or project_name.lower() in [v for v in placeholder_values if v]:
                    project_name = extracted_metadata.get("project_title", project_name)
                if not author_name or author_name.lower() in [v for v in placeholder_values if v]:
                    author_name = extracted_metadata.get("author_name", author_name)

                # Update metadata dict
                metadata["company_name"] = company_name
                metadata["project_title"] = project_name
                metadata["author_name"] = author_name

                # Merge non-critical extracted fields (objective, dates, etc.)
                for key in ['objective', 'author_org', 'document_date']:
                    if extracted_metadata.get(key) and not metadata.get(key):
                        metadata[key] = extracted_metadata[key]

                print(f"   ✅ Final metadata after merge:")
                print(f"      Company: {company_name}")
                print(f"      Project: {project_name}")
                print(f"      Author: {author_name}")

        update_task(task_id, progress=30, current_step=f"Generating {mode} document")

        # Process supporting documents if provided
        supporting_files = task_data.get('supporting_files', [])
        supporting_context = None

        if supporting_files:
            print(f"\n[TASK] Processing {len(supporting_files)} supporting document(s)")
            update_task(task_id, progress=25, current_step="Processing supporting documents")

            try:
                from app.document.doc_reader import extract_supporting_documents
                supporting_context = extract_supporting_documents(supporting_files)

                if supporting_context:
                    print(f"   ✅ Extracted {len(supporting_context)} characters from supporting documents")
                else:
                    print(f"   ⚠️  No content extracted from supporting documents")
            except Exception as e:
                print(f"   ⚠️  Error processing supporting documents: {e}")
                supporting_context = None

        # Generate document
        print(f"\n[TASK] Generating {mode} Document")
        initial_state = {
            "metadata": metadata,
            # An empty details box is meaningful when supporting documents are
            # supplied: the uploaded corpus becomes the authoritative source.
            # Do not inject a generic objective that competes with BRD evidence.
            "objective": objective or "",
            "mode": mode,
            "source_file": source_file,
            "analyzed_requirements": None,
            "validated_requirements": None,
            "poc_content": None,
            "output_path": None,
            "json_path": None,
            "errors": [],
            "current_step": "start",
            "supporting_documents": supporting_files,
            "supporting_context": supporting_context,
            "selected_sow_sections": task_data.get("selected_sow_sections"),
            "custom_template_id": task_data.get("custom_template_id"),
            "custom_template_markdown": task_data.get("custom_template_markdown"),
            "custom_template_sections": task_data.get("custom_template_sections") or [],
        }

        app_graph = create_graph()
        final_state = app_graph.invoke(initial_state)

        # Print token usage summary
        from app.core.nodes import print_token_summary
        print_token_summary(task_id)

        update_task(task_id, progress=70, current_step="Document generated, uploading to cloud")

        print(f"✅ {mode} Document Generation Complete!")

        # Get the output file path directly from final_state (no local copying)
        upload_file = final_state.get('output_path')
        
        if not upload_file or not Path(upload_file).exists():
            raise Exception("Document generation failed - no output file produced")

        update_task(task_id, progress=80, current_step="Uploading to cloud storage")

        # Cloud uploads
        print(f"\n[TASK] Cloud Uploads")
        drive_result = None
        s3_result = None
        upload_errors = []

        try:
            drive_folder = FOLDER_MAPPING.get(mode, "default")
            drive_result = upload_generated_document(upload_file, folder_name=drive_folder)
            if drive_result:
                print("✅ Google Drive upload successful")
        except Exception as e:
            error_msg = f"Google Drive upload failed: {str(e)}"
            print(f"❌ {error_msg}")
            upload_errors.append(error_msg)

        try:
            s3_folder = FOLDER_MAPPING.get(mode, mode)
            s3_result = upload_to_s3(upload_file, mode=s3_folder)
            if s3_result:
                print("✅ S3 upload successful")
        except Exception as e:
            error_msg = f"S3 upload failed: {str(e)}"
            print(f"❌ {error_msg}")
            upload_errors.append(error_msg)

        if upload_errors:
            raise Exception(f"Cloud upload failed: {', '.join(upload_errors)}")

        update_task(task_id, progress=90, current_step="Saving to DynamoDB")

        # DynamoDB storage
        print(f"\n[TASK] DynamoDB Storage")
        db_result = None
        from app.core.nodes import get_token_usage
        token_usage = get_token_usage(task_id)
        total_tokens = int(token_usage.get("total_tokens") or 0)
        if s3_result:
            s3_url = s3_result.get('https_url') or s3_result.get('s3_url') or s3_result.get('url')
            if s3_url:
                try:
                    # Prepare drive_link if available
                    drive_link = None
                    if drive_result and isinstance(drive_result, dict):
                        drive_link = drive_result.get('link') or drive_result.get('url')
                    
                    db_result = save_to_dynamodb(
                        metadata={
                            "company_name": metadata["company_name"],
                            "author_name": metadata["author_name"],
                            "project_name": metadata["project_title"],
                            "document_date": metadata["document_date"],
                            "mode": mode,
                            "business_unit": metadata.get("business_unit"),
                            "owner_email": metadata.get("owner_email"),
                            "owner_name": metadata.get("owner_name"),
                            "total_tokens": total_tokens,
                            "token_usage": token_usage,
                            **_semantic_index_metadata(
                                final_state.get("poc_content") or {}, metadata
                            ),
                        },
                        s3_url=s3_url,
                        s3_result=s3_result,
                        drive_link=drive_link,  # ✅ Include drive link
                        table_name=os.getenv('DYNAMODB_TABLE_POC_DOCUMENTS', 'agentic-poc'),
                        region=os.getenv('AWS_REGION', 'us-east-1'),
                        task_id=task_id
                    )
                except Exception as e:
                    db_result = {"success": False, "error": str(e)}

        # No local file saving - skip save_document_info
        print(f"✅ Skipping local file saving - cloud-only mode")

        storage_success = {
            "google_drive": drive_result is not None,
            "s3": s3_result is not None,
        }
        
        # ✅ AUTO-CLEANUP: Delete temporary files after successful cloud upload
        if storage_success["s3"] and storage_success["google_drive"] and upload_file:
            try:
                if os.path.exists(upload_file):
                    os.remove(upload_file)
                    print(f"✅ Cleaned up temporary file: {Path(upload_file).name}")
                
                # Also clean up JSON file if it exists
                json_file = str(upload_file).replace('.pdf', '_data.json')
                if os.path.exists(json_file):
                    os.remove(json_file)
                    print(f"✅ Cleaned up JSON file: {Path(json_file).name}")
            except Exception as e:
                print(f"⚠️  Could not clean up temporary files: {e}")


        # Task completed successfully
        result_data = {
            "pdf_path": None,  # No local files saved
            "docx_path": None,  # No local files saved
            "filename": Path(upload_file).name if upload_file else None,
            "mode": mode,
            "extracted_company": metadata.get("company_name"),
            "extracted_project": metadata.get("project_title"),
            "storage_success": storage_success,
            "s3_url": s3_result.get('https_url') if s3_result else None,
            "s3_result": s3_result,
            "drive_result": drive_result,
            "db_result": db_result,
            "document_id": db_result.get("document_id") if db_result else None,
            "total_tokens": total_tokens,
            "token_usage": token_usage,
        }

        update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            current_step="Completed",
            completed_at=datetime.now().isoformat(),
            result=result_data
        )

        print(f"✅ Task {task_id} completed successfully")

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"\n❌ Task {task_id} failed: {e}")
        print(error_trace)

        update_task(
            task_id,
            status=TaskStatus.FAILED,
            progress=0,
            current_step="Failed",
            completed_at=datetime.now().isoformat(),
            error=str(e)
        )
    
    finally:
        if usage_context_token is not None:
            from app.core.nodes import clear_token_usage, unbind_token_usage
            unbind_token_usage(usage_context_token)
            clear_token_usage(task_id)
        # ✅ Always clean up uploaded file
        if uploaded_file_path and os.path.exists(uploaded_file_path):
            try:
                os.remove(uploaded_file_path)
                print(f"[CLEANUP] Removed uploaded file: {uploaded_file_path}")
            except Exception as cleanup_err:
                print(f"[CLEANUP] Warning: Could not remove file: {cleanup_err}")

        # ✅ Clean up supporting documents
        supporting_files = task_data.get('supporting_files', [])
        if supporting_files:
            for support_file in supporting_files:
                if os.path.exists(support_file):
                    try:
                        os.remove(support_file)
                        print(f"[CLEANUP] Removed supporting file: {support_file}")
                    except Exception as cleanup_err:
                        print(f"[CLEANUP] Warning: Could not remove supporting file: {cleanup_err}")


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/generate', methods=['POST'])
def generate_document():
    """
    ✅ FIX #1: Improved race condition handling
    Generate Document - Returns task ID immediately with task data
    """
    uploaded_file_path = None
    
    try:
        print("\n[API] Processing FormData request...")
        business_unit, denied = _business_unit_for_new_record()
        if denied:
            return denied
        ownership = _ownership_metadata(business_unit)
        mode = request.form.get('mode', '').upper()

        if not mode or mode not in ["POC", "PROD", "POC_TO_PROD"]:
            return jsonify({
                "success": False,
                "error": "Invalid or missing mode (POC, PROD, or POC_TO_PROD)"
            }), 400

        custom_template_id = request.form.get('custom_template_id', '').strip()
        custom_template = None
        if custom_template_id:
            try:
                custom_template = CustomTemplateStore().get(custom_template_id)
            except Exception as exc:
                return jsonify({"success": False, "error": f"Could not load custom template: {exc}"}), 500
            if not custom_template:
                return jsonify({"success": False, "error": "Custom template not found"}), 404
            if int(custom_template.get("schema_version") or 0) < CustomTemplateStore.SCHEMA_VERSION:
                return jsonify({
                    "success": False,
                    "error": "This preset uses the previous extraction format. Re-upload the source SOW to create a format-only template.",
                }), 409
            identity = current_identity()
            if (
                not bool(custom_template.get("saved"))
                and str(custom_template.get("owner_email") or "").casefold() != identity.email.casefold()
            ):
                return jsonify({"success": False, "error": "This template extraction belongs to another user"}), 403

        declared_supporting_count = request.form.get('supporting_doc_count', '').strip()
        if declared_supporting_count:
            try:
                declared_supporting_count = int(declared_supporting_count)
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": "supporting_doc_count must be an integer",
                }), 400
            actual_supporting_count = len([
                item for item in request.files.getlist('supporting_docs')
                if item and item.filename
            ])
            if actual_supporting_count != declared_supporting_count:
                return jsonify({
                    "success": False,
                    "error": (
                        "Supporting-document multipart transfer was incomplete; "
                        f"the browser sent {declared_supporting_count} file(s) but the server "
                        f"received {actual_supporting_count}. Generation was not started."
                    ),
                    "supporting_documents_declared": declared_supporting_count,
                    "supporting_documents_received": actual_supporting_count,
                }), 400

        from app.core.sow_section_preferences import parse_selected_section_ids
        try:
            selected_sow_sections = parse_selected_section_ids(
                request.form.get('selected_sow_sections'), mode
            )
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        selected_custom_ids = {item for item in selected_sow_sections if item.startswith("custom_")}
        valid_custom_ids = {
            str(item.get("id")) for item in (custom_template or {}).get("sections", [])
        }
        if selected_custom_ids and not custom_template:
            return jsonify({
                "success": False,
                "error": "Custom extracted sections require a selected custom template",
            }), 400
        unknown_custom = sorted(selected_custom_ids - valid_custom_ids)
        if unknown_custom:
            return jsonify({
                "success": False,
                "error": f"Unknown custom template section(s): {', '.join(unknown_custom)}",
            }), 400

        # Validate required fields based on mode
        if mode == "POC_TO_PROD":
            if 'file' not in request.files or not request.files['file'].filename:
                return jsonify({
                    "success": False,
                "error": "POC_TO_PROD mode requires a supported document upload"
                }), 400

            company_name = request.form.get('company_name', '').strip() or None
            author_name = request.form.get('author_name', '').strip() or None
            project_name = request.form.get('project_name', '').strip() or None
            objective = (
                request.form.get('additional_details', '').strip()
                or request.form.get('objective', '').strip()
                or None
            )
        else:
            company_name = request.form.get('company_name', '').strip()
            author_name = request.form.get('author_name', '').strip()
            project_name = request.form.get('project_name', '').strip()
            objective = (
                request.form.get('additional_details', '').strip()
                or request.form.get('objective', '').strip()
            )

            uploaded_supporting = [
                item for item in request.files.getlist('supporting_docs')
                if item and item.filename
            ]
            if any(Path(item.filename).suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS
                   for item in uploaded_supporting):
                return jsonify({
                    "success": False,
                    "error": "Unsupported file type. Supported files: PDF, Word, Excel, and TXT.",
                }), 415
            has_supporting_source = bool(uploaded_supporting)

            if not all([company_name, author_name, project_name]) or not (
                objective or has_supporting_source
            ):
                return jsonify({
                    "success": False,
                    "error": (
                        f"{mode} mode requires company_name, author_name, project_name, "
                        "and either a BRD/supporting document or sufficient additional details"
                    )
                }), 400
            if not objective:
                objective = ""

        document_date = request.form.get('document_date') or datetime.now().strftime("%d %B %Y")
        version = request.form.get('version', '1.0')

        # Handle file upload
        source_file = None
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename:
                file_ext = Path(file.filename).suffix.lower()
                if file_ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
                    return jsonify({
                        "success": False,
                        "error": "Unsupported file type. Supported files: PDF, Word, Excel, and TXT."
                    }), 415

                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                unique_filename = f"{timestamp}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                uploaded_file_path = filepath
                source_file = filepath
                print(f"✓ File uploaded: {filepath}")

        # Handle multiple supporting documents upload
        supporting_files = []
        if 'supporting_docs' in request.files:
            files_list = request.files.getlist('supporting_docs')
            print(f"✓ Received {len(files_list)} supporting document(s)")

            for idx, support_file in enumerate(files_list, 1):
                if support_file and support_file.filename:
                    file_ext = Path(support_file.filename).suffix.lower()
                    if file_ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
                        return jsonify({
                            "success": False,
                            "error": "Unsupported file type. Supported files: PDF, Word, Excel, and TXT.",
                        }), 415

                    filename = secure_filename(support_file.filename)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    unique_filename = f"{timestamp}_support{idx}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    support_file.save(filepath)
                    supporting_files.append(filepath)
                    print(f"✓ Supporting document {idx} uploaded: {filepath}")

        # ✅ FIX #1: Create task FIRST, verify it exists, THEN start thread
        task_id = str(uuid.uuid4())
        
        # Create task with metadata
        task = create_task(task_id, mode, {
            "company_name": company_name,
            "project_name": project_name,
            "author_name": author_name,
            **ownership,
        })

        # Verify task was created successfully
        if not task:
            raise Exception("Failed to create task")
        
        # Verify task is accessible
        if not get_task(task_id):
            raise Exception("Task created but not accessible")

        print(f"[DEBUG] Task {task_id} verified in memory")

        # Prepare task data for background processing
        task_data = {
            'mode': mode,
            'company_name': company_name,
            'author_name': author_name,
            'project_name': project_name,
            'objective': objective,
            'additional_details': objective,
            'document_date': document_date,
            'version': version,
            'source_file': source_file,
            'uploaded_file_path': uploaded_file_path,
            'supporting_files': supporting_files,  # List of supporting document paths
            'selected_sow_sections': selected_sow_sections,
            'custom_template_id': custom_template_id or None,
            'custom_template_name': str((custom_template or {}).get('name') or 'Uploaded custom template'),
            'custom_template_markdown': (custom_template or {}).get('markdown'),
            'custom_template_sections': (custom_template or {}).get('sections') or [],
            **ownership,
        }

        # Start background processing AFTER task is confirmed to exist
        thread = threading.Thread(
            target=process_document_generation,
            args=(task_id, task_data),
            daemon=True
        )
        thread.start()

        print(f"✅ Task {task_id} queued for processing")

        # ✅ Return task data immediately (no need for client to poll right away)
        response = jsonify({
            "success": True,
            "message": f"{mode} document generation started",
            "task_id": task_id,
            "task": task,  # Include initial task state
            "status_url": f"/api/task/{task_id}"
        })
        
        # Add explicit headers to ensure proper connection handling
        response.headers['Content-Type'] = 'application/json'
        response.headers['Connection'] = 'close'
        response.headers['Cache-Control'] = 'no-cache'
        
        return response, 202  # HTTP 202 Accepted

    except Exception as e:
        # Clean up uploaded files on error
        if uploaded_file_path and os.path.exists(uploaded_file_path):
            try:
                os.remove(uploaded_file_path)
                print(f"[CLEANUP] Removed orphaned file: {uploaded_file_path}")
            except Exception as cleanup_err:
                print(f"[CLEANUP] Failed to remove file: {cleanup_err}")

        # Clean up supporting documents
        if supporting_files:
            for support_file in supporting_files:
                if os.path.exists(support_file):
                    try:
                        os.remove(support_file)
                        print(f"[CLEANUP] Removed supporting file: {support_file}")
                    except Exception as cleanup_err:
                        print(f"[CLEANUP] Failed to remove supporting file: {cleanup_err}")
        
        import traceback
        traceback.print_exc()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """
    ✅ FIX #4: Enhanced task status with DynamoDB fallback
    Get task status with automatic document lookup
    """
    print(f"[DEBUG] Looking for task: {task_id}")
    
    # Try to get task from memory first
    task = get_task(task_id)
    
    if task:
        denied = _resource_denied(task.get("metadata"))
        if denied:
            return denied
        # Task found in memory
        response_data = {
            "success": True,
            "task": task,
            "source": "memory"
        }
        
        # If task is completed, try to fetch document from DB
        if task.get('status') == TaskStatus.COMPLETED:
            try:
                handler = DynamoDBHandler()
                document = handler.query_by_task_id(task_id)
                if document:
                    denied = _resource_denied(document)
                    if denied:
                        return denied
                    response_data['document'] = document
                    print(f"[DEBUG] Found document in DB for task {task_id}")
            except Exception as e:
                print(f"[DEBUG] Could not fetch document: {e}")
                # Don't fail the request, just skip document lookup
        
        return jsonify(response_data), 200
    
    # ✅ FIX #4: Task not in memory - check DynamoDB
    print(f"[DEBUG] Task not in memory, checking DynamoDB...")
    
    try:
        handler = DynamoDBHandler()
        document = handler.query_by_task_id(task_id)
        
        if document:
            denied = _resource_denied(document)
            if denied:
                return denied
            # Found in database - task completed and cleaned from memory
            print(f"[DEBUG] Found completed task in DynamoDB: {task_id}")
            return jsonify({
                "success": True,
                "task": {
                    "task_id": task_id,
                    "status": "completed",
                    "progress": 100,
                    "current_step": "Completed",
                    "mode": document.get('mode'),
                    "metadata": {
                        "company_name": document.get('customer_name'),
                        "project_name": document.get('project_name'),
                        "author_name": document.get('author_name')
                    }
                },
                "document": document,
                "source": "database",
                "note": "Task completed and cleaned from memory"
            }), 200
    
    except Exception as e:
        print(f"[DEBUG] DynamoDB lookup failed: {e}")
    
    # Task not found anywhere
    print(f"[DEBUG] Task {task_id} not found in memory or database")
    return jsonify({
        "success": False,
        "error": "Task not found in memory or database",
        "task_id": task_id,
        "total_active_tasks": len(tasks)
    }), 404


@app.route('/api/proxy-download', methods=['POST'])
def proxy_download():
    """Download a private S3 object with the application's AWS credentials."""
    try:
        data = request.get_json()
        s3_url = data.get('s3_url')
        document_id = data.get('document_id')

        if not s3_url:
            return jsonify({
                "error": "s3_url is required"
            }), 400

        # The URL alone is not an authority boundary. Confirm that it belongs
        # to a document visible to the current user before reading from S3.
        # New clients send document_id, which is the DynamoDB partition key and
        # must be queried directly. A limited Scan applies its limit before its
        # filter and can therefore miss recent records.
        handler = DynamoDBHandler()
        if document_id:
            lookup = handler.table.query(
                KeyConditionExpression='document_id = :document_id',
                ExpressionAttributeValues={':document_id': document_id},
                ConsistentRead=True,
            ).get('Items', [])
            lookup = [item for item in lookup if item.get('s3_url') == s3_url]
        else:
            # Compatibility for older records/clients that do not carry an ID.
            # Paginate until the URL is found rather than inspecting an
            # arbitrary first page of the table.
            lookup = []
            scan_kwargs = {
                'FilterExpression': 's3_url = :url',
                'ExpressionAttributeValues': {':url': s3_url},
            }
            while True:
                page = handler.table.scan(**scan_kwargs)
                lookup.extend(page.get('Items', []))
                if lookup or 'LastEvaluatedKey' not in page:
                    break
                scan_kwargs['ExclusiveStartKey'] = page['LastEvaluatedKey']
        if not lookup:
            return jsonify({"success": False, "error": "Document not found"}), 404
        if not any(item_is_visible(item, current_identity()) for item in lookup):
            return jsonify({"success": False, "error": "You do not have access to this document"}), 403

        print(f"[API] Proxy downloading from S3: {s3_url}")

        bucket, key = parse_s3_location(s3_url)
        s3_client = get_s3_client()
        if s3_client is None:
            raise RuntimeError("Unable to initialize the S3 client")

        s3_response = s3_client.get_object(Bucket=bucket, Key=key)
        body = s3_response['Body']
        try:
            content = body.read()
        finally:
            body.close()

        if not content or len(content) != int(s3_response.get('ContentLength', len(content))):
            raise RuntimeError("Document download was empty or incomplete; no file was returned")

        content_type = s3_response.get('ContentType', 'application/octet-stream')
        if 'officedocument' in content_type or s3_url.endswith('.docx'):
            content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif s3_url.endswith('.pdf'):
            content_type = 'application/pdf'

        print(f"[API] Successfully downloaded {len(content)} bytes from S3")

        filename = secure_filename(Path(key).name) or "document.docx"

        return Response(
            content,
            mimetype=content_type,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Access-Control-Allow-Origin': '*',
                'Content-Length': len(content),
                'X-Content-Type-Options': 'nosniff',
                'Content-Security-Policy': "default-src 'none'",
                'Cache-Control': 'no-cache, no-store, must-revalidate'
            }
        )

    except ValueError as e:
        print(f"[API] Proxy download rejected: {e}")
        return jsonify({"error": str(e)}), 400
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'S3Error')
        print(f"[API] S3 download error ({error_code}): {e}")
        status = 404 if error_code in {'NoSuchKey', 'NoSuchBucket', '404'} else 403
        return jsonify({"error": f"S3 download failed: {error_code}"}), status
    except Exception as e:
        print(f"[API] Proxy download error: {e}")
        return jsonify({
            "error": str(e)
        }), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    """
    ✅ ENHANCED: Get document history with full task details including drive_link
    Returns task objects matching /api/task/<id> structure
    """
    try:
        handler = DynamoDBHandler()
        filter_type = request.args.get('filter', 'all').lower()
        filter_value = request.args.get('value', '').strip()
        limit = request.args.get('limit', 100, type=int)

        print(f"\n[API] History request (GET)")
        print(f"      Filter: {filter_type}, Value: {filter_value}")

        if limit < 1 or limit > 1000:
            limit = 100

        results = []
        metadata = {
            "filter_type": filter_type,
            "filter_value": filter_value if filter_value else None,
            "limit": limit
        }

        if filter_type == 'customer':
            if not filter_value:
                return jsonify({
                    "success": False,
                    "error": "filter=customer requires 'value' parameter"
                }), 400

            print(f"      → Querying by customer: {filter_value} (using GSI)")
            results = handler.query_by_customer(filter_value, limit=limit)

        elif filter_type == 'author':
            if not filter_value:
                return jsonify({
                    "success": False,
                    "error": "filter=author requires 'value' parameter"
                }), 400

            print(f"      → Querying by author: {filter_value} (using GSI)")
            results = handler.query_by_author(filter_value, limit=limit)

        elif filter_type == 'project':
            if not filter_value:
                return jsonify({
                    "success": False,
                    "error": "filter=project requires 'value' parameter"
                }), 400

            print(f"      → Querying by project: {filter_value} (using GSI)")
            results = handler.query_by_project(filter_value, limit=limit)

        elif filter_type == 'all' or filter_type == '':
            print(f"      → Retrieving all documents")
            results = handler.list_all_documents(limit=limit)
            
            # ✅ MERGE WITH ACTIVE TASKS for 'all' filter
            results = merge_with_active_tasks(results, mode_filter=None, limit=limit)

        else:
            return jsonify({
                "success": False,
                "error": f"Invalid filter type: {filter_type}"
            }), 400

        # ✅ For filtered results, also merge with active tasks
        if filter_type != 'all' and results:
            results = merge_with_active_tasks(results, mode_filter=None, limit=limit)

        if request.args.get('mine', '').lower() in {'1', 'true', 'yes'}:
            identity_email = current_identity().email.casefold().strip()
            results = [
                item for item in results
                if str(item.get('document', item).get('owner_email') or '').casefold().strip()
                == identity_email
            ]
        else:
            results = _visible_documents(results)

        print(f"      ✓ Found {len(results)} documents (with drive links)")

        return jsonify({
            "success": True,
            "metadata": metadata,
            "documents": results or [],
            "count": len(results) if results else 0
        }), 200

    except Exception as e:
        print(f"[API] History error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "documents": [],
            "count": 0
        }), 500


@app.route('/api/history/semantic-index', methods=['GET'])
def prepare_semantic_index():
    """Warm the reusable vector index as soon as the records page opens."""
    state = _start_semantic_index_backfill()
    return jsonify({"success": True, **state}), 200


@app.route('/api/history/semantic-search', methods=['GET'])
def semantic_search_history():
    """Rank only the latest accessible version of each SOW by semantic similarity."""
    query = str(request.args.get('q') or '').strip()
    if not query:
        return jsonify({"success": False, "error": "Search query is required"}), 400
    if len(query) > 500:
        return jsonify({"success": False, "error": "Search query must be 500 characters or fewer"}), 400
    try:
        limit = request.args.get('limit', 1000, type=int)
        limit = min(max(limit, 1), 1000)
        records = DynamoDBHandler().list_all_documents(
            limit=limit, include_semantic_text=True
        )
        if request.args.get('mine', '').lower() in {'1', 'true', 'yes'}:
            email = current_identity().email.casefold().strip()
            records = [
                item for item in records
                if str(item.get('owner_email') or '').casefold().strip() == email
            ]
        else:
            records = _visible_documents(records)

        # Search never downloads documents. Vectors are created when a SOW is
        # saved and old records are migrated once by the persistent backfill.
        records = latest_versions(records)
        embedder = BedrockSemanticEmbedder(Config())
        indexed_count = sum(
            1 for item in records if stored_embedding(item, embedder.model_id)
        )
        print(
            f"[SEMANTIC SEARCH][DEBUG] query={query!r}; latest_records={len(records)}; "
            f"ready_vectors={indexed_count}; model={embedder.model_id}",
            flush=True,
        )
        missing = [
            item for item in records
            if not stored_embedding(item, embedder.model_id)
        ]
        if missing:
            print(
                f"[SEMANTIC SEARCH][DEBUG] {len(missing)} record(s) need index v3; "
                "starting/resuming persistent backfill",
                flush=True,
            )
            _start_semantic_index_backfill(force=True)
            # A records-page warm-up normally finishes before the user types.
            # This short bounded wait also covers a near-complete migration.
            semantic_index_ready.wait(timeout=0.5)
            records = DynamoDBHandler().list_all_documents(
                limit=limit, include_semantic_text=True
            )
            if request.args.get('mine', '').lower() in {'1', 'true', 'yes'}:
                email = current_identity().email.casefold().strip()
                records = [
                    item for item in records
                    if str(item.get('owner_email') or '').casefold().strip() == email
                ]
            else:
                records = _visible_documents(records)
            records = latest_versions(records)
            missing = [
                item for item in records
                if not stored_embedding(item, embedder.model_id)
            ]
            if missing:
                with semantic_index_lock:
                    state = dict(semantic_index_state)
                return jsonify({
                    "success": True,
                    "indexing": True,
                    "documents": [],
                    "count": 0,
                    "threshold": round(SIMILARITY_THRESHOLD * 100, 2),
                    "message": "Preparing semantic search for existing SOWs",
                    "index": state,
                }), 200

        diagnostics = []
        results = semantic_search_records(
            records, query, embedder.embed, threshold=SIMILARITY_THRESHOLD,
            model_id=embedder.model_id,
            diagnostics=diagnostics,
        )
        for row in sorted(
            diagnostics, key=lambda item: float(item.get("final_score") or 0), reverse=True
        )[:15]:
            print(
                f"[SEMANTIC SEARCH][SCORE] project={row.get('project_name')!r}; "
                f"version={row.get('version')}; raw_cosine={row.get('raw_semantic_score'):.2f}%; "
                f"semantic={row.get('semantic_score'):.2f}%; chunks={row.get('chunks')}; "
                f"lexical={row.get('lexical_score'):.2f}%; final={row.get('final_score'):.2f}%; "
                f"reason={row.get('reason')}; chars={row.get('indexed_chars')}; "
                f"displayed={row.get('matched')}",
                flush=True,
            )
        for item in results:
            item.pop('semantic_search_text', None)
            item.pop('semantic_search_embedding', None)
            item.pop('semantic_search_embeddings', None)
            item.pop('semantic_embedding_model_id', None)
            item.pop('semantic_search_text_hash', None)
            item.pop('semantic_index_version', None)
            item.pop('refinement_instructions', None)
        print(
            f"[SEMANTIC SEARCH] query_chars={len(query)}; accessible={len(records)}; "
            f"matches={len(results)}; threshold={SIMILARITY_THRESHOLD:.0%}",
            flush=True,
        )
        return jsonify({
            "success": True,
            "documents": results,
            "count": len(results),
            "threshold": round(SIMILARITY_THRESHOLD * 100, 2),
        }), 200
    except Exception as exc:
        logging.getLogger(__name__).exception("Semantic SOW search failed")
        return jsonify({
            "success": False,
            "error": "Semantic search is temporarily unavailable",
            "details": str(exc),
            "documents": [],
        }), 503


@app.route('/api/recent-pocs', methods=['GET'])
def get_recent_pocs():
    """
    ✅ ENHANCED: Get recent POC documents with full task details including drive_link
    Returns task objects matching /api/task/<id> structure
    """
    try:
        print(f"\n[API] Fetching recent POCs (with active tasks and drive links)...")
        handler = DynamoDBHandler()
        
        # Get completed POC documents from DynamoDB
        all_docs = handler.list_all_documents(limit=100)
        
        if all_docs:
            # Filter for POC mode only
            poc_docs = [doc for doc in all_docs if doc.get('mode') == 'POC']
        else:
            poc_docs = []
        
        # ✅ MERGE WITH ACTIVE POC TASKS (returns full task structure with drive_link)
        merged_docs = merge_with_active_tasks(poc_docs, mode_filter='POC', limit=50)
        merged_docs = _visible_documents(merged_docs)
        
        print(f"[API] Returning {len(merged_docs)} POC task objects (with drive links)")
        
        return jsonify({
            "success": True,
            "documents": merged_docs,
            "count": len(merged_docs)
        }), 200

    except Exception as e:
        print(f"[API] Recent POCs error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": True,
            "documents": [],
            "count": 0,
            "error": str(e)
        }), 200


@app.route('/api/recent-prod', methods=['GET'])
def get_recent_prods():
    """
    ✅ ENHANCED: Get recent PROD documents with full task details including drive_link
    Returns task objects matching /api/task/<id> structure
    """
    try:
        print(f"\n[API] Fetching recent PRODs (with active tasks and drive links)...")
        handler = DynamoDBHandler()
        
        # Get completed PROD documents from DynamoDB
        all_docs = handler.list_all_documents(limit=100)
        
        if all_docs:
            # Filter for PROD mode only
            prod_docs = [doc for doc in all_docs if doc.get('mode') == 'PROD']
        else:
            prod_docs = []
        
        # ✅ MERGE WITH ACTIVE PROD TASKS (returns full task structure with drive_link)
        merged_docs = merge_with_active_tasks(prod_docs, mode_filter='PROD', limit=50)
        merged_docs = _visible_documents(merged_docs)
        
        print(f"[API] Returning {len(merged_docs)} PROD task objects (with drive links)")
        
        return jsonify({
            "success": True,
            "documents": merged_docs,
            "count": len(merged_docs)
        }), 200

    except Exception as e:
        print(f"[API] Recent PRODs error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": True,
            "documents": [],
            "count": 0,
            "error": str(e)
        }), 200


@app.route('/api/recent-poc_to_prod', methods=['GET'])
def get_recent_poc_to_prods():
    """
    ✅ ENHANCED: Get recent POC_TO_PROD documents with full task details including drive_link
    Returns task objects matching /api/task/<id> structure
    """
    try:
        print(f"\n[API] Fetching recent POC_TO_PRODs (with active tasks and drive links)...")
        handler = DynamoDBHandler()
        
        # Get completed POC_TO_PROD documents from DynamoDB
        all_docs = handler.list_all_documents(limit=100)
        
        if all_docs:
            # Filter for POC_TO_PROD mode only
            poc_to_prod_docs = [doc for doc in all_docs if doc.get('mode') == 'POC_TO_PROD']
        else:
            poc_to_prod_docs = []
        
        # ✅ MERGE WITH ACTIVE POC_TO_PROD TASKS (returns full task structure with drive_link)
        merged_docs = merge_with_active_tasks(poc_to_prod_docs, mode_filter='POC_TO_PROD', limit=50)
        merged_docs = _visible_documents(merged_docs)
        
        print(f"[API] Returning {len(merged_docs)} POC_TO_PROD task objects (with drive links)")
        
        return jsonify({
            "success": True,
            "documents": merged_docs,
            "count": len(merged_docs)
        }), 200

    except Exception as e:
        print(f"[API] Recent POC_TO_PRODs error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": True,
            "documents": [],
            "count": 0,
            "error": str(e)
        }), 200


@app.route('/api/search-suggestions', methods=['GET'])
def get_search_suggestions():
    """Get autocomplete suggestions for search based on filter type and query"""
    try:
        handler = DynamoDBHandler()
        filter_type = request.args.get('filter', 'author').lower().strip()
        query = request.args.get('query', '').strip().lower()
        limit = request.args.get('limit', 10, type=int)

        print(f"\n{'='*70}")
        print(f"[API] Search Suggestions Request")
        print(f"{'='*70}")
        print(f"Filter Type: {filter_type}")
        print(f"Query: '{query}'")

        # Validate limit
        if limit < 1 or limit > 50:
            limit = 10

        # Check minimum query length
        if not query or len(query) < 2:
            return jsonify({
                "success": True,
                "suggestions": [],
                "filter_type": filter_type,
                "query": query,
                "message": "Query too short (minimum 2 characters)"
            }), 200

        all_docs = _visible_documents(handler.list_all_documents(limit=1000))

        if not all_docs:
            return jsonify({
                "success": True,
                "suggestions": [],
                "filter_type": filter_type,
                "query": query,
                "count": 0,
                "message": "No documents found in database"
            }), 200

        # Extract unique values based on filter type
        unique_values = set()

        if filter_type == 'author':
            for doc in all_docs:
                author = doc.get('author_name', '')
                if author and query in author.lower():
                    unique_values.add(author)

        elif filter_type == 'customer':
            for doc in all_docs:
                customer = doc.get('customer_name', '')
                if customer and query in customer.lower():
                    unique_values.add(customer)

        elif filter_type == 'project':
            for doc in all_docs:
                project = doc.get('project_name', '')
                if project and query in project.lower():
                    unique_values.add(project)

        else:
            return jsonify({
                "success": False,
                "error": f"Invalid filter type: {filter_type}",
                "suggestions": []
            }), 400

        # Sort and limit suggestions
        suggestions = sorted(list(unique_values))[:limit]

        return jsonify({
            "success": True,
            "suggestions": suggestions,
            "filter_type": filter_type,
            "query": query,
            "count": len(suggestions),
            "total_matches": len(unique_values)
        }), 200

    except Exception as e:
        print(f"\n❌ [API] Search suggestions error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "suggestions": []
        }), 500

@app.route('/api/companies-grouped', methods=['GET'])
def get_companies_grouped():
    """
    ✅ NEW: Get all companies grouped by projects and versions
    
    Response structure:
    {
        "success": true,
        "companies": {
            "TCS": {
                "company_name": "TCS",
                "document_count": 5,
                "projects": {
                    "E-commerce Platform": {
                        "project_name": "E-commerce Platform",
                        "POC": ["v1", "v2", "v3"],
                        "PROD": ["v1", "v2"],
                        "POC_TO_PROD": []
                    }
                }
            }
        },
        "total_companies": 2,
        "total_documents": 8
    }
    """
    try:
        print(f"\n{'='*70}")
        print(f"[API] GET /api/companies-grouped")
        print(f"{'='*70}")
        
        handler = DynamoDBHandler()
        
        # Get grouped data
        companies = handler.get_companies_grouped(
            limit=1000,
            business_unit=_requested_business_unit_filter(),
            owner_email=current_identity().email if current_identity().is_user else None,
        )
        
        # Calculate totals
        total_companies = len(companies)
        total_documents = sum(company['document_count'] for company in companies.values())
        
        print(f"\n✓ Grouped {total_documents} documents across {total_companies} companies")
        
        return jsonify({
            "success": True,
            "companies": companies,
            "total_companies": total_companies,
            "total_documents": total_documents
        }), 200
        
    except Exception as e:
        print(f"[API] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "companies": {},
            "total_companies": 0,
            "total_documents": 0
        }), 500


@app.route('/api/company/<company_name>', methods=['GET'])
def get_company_documents(company_name):
    """
    ✅ NEW: Get all documents for a specific company with optional filters
    
    Query Parameters:
        - project: Filter by project name (optional)
        - mode: Filter by mode (POC/PROD/POC_TO_PROD) (optional)
        - version: Filter by version (v1, v2, etc.) (optional)
        - limit: Max results (default: 100)
    
    Response structure:
    {
        "success": true,
        "company_name": "TCS",
        "total_documents": 5,
        "filters_applied": {
            "project": "E-commerce Platform",
            "mode": "POC",
            "version": null
        },
        "projects": {
            "E-commerce Platform": {
                "POC": {
                    "v1": [document_object],
                    "v2": [document_object]
                },
                "PROD": {
                    "v1": [document_object]
                }
            }
        }
    }
    """
    try:
        print(f"\n{'='*70}")
        print(f"[API] GET /api/company/{company_name}")
        print(f"{'='*70}")
        
        # Get query parameters
        project_name = request.args.get('project')
        mode = request.args.get('mode')
        version = request.args.get('version')
        limit = request.args.get('limit', 100, type=int)
        
        if limit < 1 or limit > 1000:
            limit = 100
        
        print(f"Filters: project={project_name}, mode={mode}, version={version}, limit={limit}")
        
        handler = DynamoDBHandler()
        
        # Get company documents with filters
        result = handler.get_company_documents(
            company_name=company_name,
            project_name=project_name,
            mode=mode,
            version=version,
            limit=limit,
            business_unit=_requested_business_unit_filter(),
            owner_email=current_identity().email if current_identity().is_user else None,
        )
        
        print(f"\n✓ Found {result['total_documents']} documents for {company_name}")
        
        return jsonify({
            "success": True,
            **result
        }), 200
        
    except Exception as e:
        print(f"[API] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "company_name": company_name,
            "total_documents": 0,
            "projects": {}
        }), 500

@app.route('/api/company/<company_name>/project/<project_name>/data', methods=['GET'])
def get_project_full_data(company_name, project_name):
    """
    Get ALL documents under a company + project
    """
    try:
        print(f"\n{'='*70}")
        print(f"[API] GET /api/company/{company_name}/project/{project_name}/data")
        print(f"{'='*70}")

        mode_filter = request.args.get('mode')
        version_filter = request.args.get('version')

        handler = DynamoDBHandler()

        # ✅ STEP 1: Query by company
        company_docs = handler.query_by_customer(company_name, limit=1000)

        project_name_lower = project_name.lower().strip()

        # ✅ STEP 2: Filter by project
        filtered_docs = []
        for doc in company_docs:
            if not item_is_visible(doc, current_identity(), request.args.get("business_unit")):
                continue
            if doc.get('project_name', '').lower().strip() != project_name_lower:
                continue

            if mode_filter and doc.get('mode') != mode_filter.upper():
                continue

            if version_filter and doc.get('version') != version_filter:
                continue

            filtered_docs.append(doc)

        # ✅ STEP 3: Group FULL documents
        grouped_data = {}

        for doc in filtered_docs:
            mode = doc.get('mode', 'UNKNOWN')
            version = doc.get('version', 'v1')

            grouped_data.setdefault(mode, {})
            grouped_data[mode].setdefault(version, [])
            grouped_data[mode][version].append(doc)

        return jsonify({
            "success": True,
            "company_name": company_name,
            "project_name": project_name,
            "total_documents": len(filtered_docs),
            "filters_applied": {
                "mode": mode_filter,
                "version": version_filter
            },
            "documents": grouped_data
        }), 200

    except Exception as e:
        print(f"[API] Error: {e}")
        import traceback
        traceback.print_exc()

        return jsonify({
            "success": False,
            "company_name": company_name,
            "project_name": project_name,
            "error": str(e),
            "documents": {}
        }), 500

# ============================================================================
# NEW PREVIEW/EDIT/FINALIZE WORKFLOW APIs
# ============================================================================

@app.route('/api/documents/<document_id>/sources', methods=['GET'])
def list_document_sources(document_id):
    """List every stored supporting-document revision for the record's project."""
    try:
        record, denied = _document_record(document_id)
        if denied:
            return denied
        scope_id = project_source_scope(record)
        sources = [public_source_metadata(item) for item in SourceDocumentStore().list_documents(scope_id)]
        return jsonify({"success": True, "documents": sources, "count": len(sources)}), 200
    except Exception as exc:
        print(f"[REFINE] Unable to list supporting documents: {exc}", flush=True)
        return jsonify({"success": False, "error": "Unable to load supporting documents"}), 500


@app.route('/api/documents/<document_id>/sources/<source_id>', methods=['GET'])
def download_document_source(document_id, source_id):
    """Download a project source after applying record-level access control."""
    try:
        record, denied = _document_record(document_id)
        if denied:
            return denied
        content, source = SourceDocumentStore().download(project_source_scope(record), source_id)
        return send_file(
            io.BytesIO(content),
            as_attachment=True,
            download_name=source.get("filename") or "supporting-document",
            mimetype="application/octet-stream",
        )
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Supporting document not found"}), 404
    except Exception as exc:
        print(f"[REFINE] Unable to download supporting document: {exc}", flush=True)
        return jsonify({"success": False, "error": "Unable to download supporting document"}), 500


@app.route('/api/documents/<document_id>/regenerate', methods=['POST'])
def regenerate_document_preview(document_id):
    """Create a refinement preview from a finalized SOW and source-document deltas."""
    preview_started_at = time.perf_counter()
    temp_paths = []
    try:
        record, denied = _document_record(document_id)
        if denied:
            return denied
        instructions = request.form.get("instructions", "").strip()
        uploads = [item for item in request.files.getlist("supporting_docs") if item and item.filename]
        declared_count = request.form.get("supporting_doc_count", "").strip()
        if declared_count:
            try:
                if int(declared_count) != len(uploads):
                    raise ValueError
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": "Supporting-document multipart transfer was incomplete",
                }), 400
        if not instructions and not uploads:
            return jsonify({
                "success": False,
                "error": "Enter refinement instructions or upload a revised supporting document",
            }), 400
        unsupported = [
            item.filename for item in uploads
            if Path(item.filename).suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS
        ]
        if unsupported:
            return jsonify({
                "success": False,
                "error": "Unsupported file type. Supported files: PDF, Word, Excel, and TXT.",
                "unsupported_files": unsupported,
            }), 415

        s3_url = str(record.get("s3_url") or "").strip()
        if not s3_url:
            return jsonify({
                "success": False,
                "error": "The saved SOW has no S3 document and cannot be regenerated",
            }), 409
        baseline_sow, baseline_path = _read_s3_document(s3_url)
        temp_paths.append(baseline_path)
        if len(baseline_sow.strip()) < 50:
            return jsonify({"success": False, "error": "The saved SOW could not be read"}), 422

        identity = current_identity()
        metadata = {
            "company_name": record.get("customer_name") or record.get("company_name") or "",
            "author_name": identity.name,
            "author_org": "Shellkode",
            "author_org_description": "Shellkode specializes in developing advanced data and AI solutions for businesses.",
            "document_date": datetime.now().strftime("%d %B %Y"),
            "version": DynamoDBHandler().get_next_version(
                record.get("customer_name") or "",
                record.get("project_name") or "",
                record.get("mode") or "POC",
            ),
            "start_date": "",
            "end_date": "",
            "timezone": "IST",
            "project_title": record.get("project_name") or "",
            "business_unit": record.get("business_unit"),
            "owner_email": identity.email,
            "owner_name": identity.name,
            "project_id": record.get("project_id"),
            "account_id": record.get("account_id"),
            "parent_document_id": record.get("document_id"),
            "refinement_instructions": instructions,
        }
        mode = str(record.get("mode") or "POC").upper()
        from app.core.sow_section_preferences import (
            infer_selected_section_ids,
            parse_selected_section_ids,
        )
        requested_sections = request.form.get("selected_sow_sections")
        if requested_sections is not None:
            selected_sections = parse_selected_section_ids(requested_sections, mode)
        elif isinstance(record.get("selected_sow_sections"), list):
            selected_sections = parse_selected_section_ids(
                record.get("selected_sow_sections"), mode
            )
        else:
            selected_sections = infer_selected_section_ids(baseline_sow, mode)
            if not selected_sections:
                return jsonify({
                    "success": False,
                    "error": (
                        "The original SOW section selection could not be recovered. "
                        "Regeneration was stopped to prevent adding template sections."
                    ),
                }), 422
        print(
            f"[REFINE] Preserving {len(selected_sections)} selected section(s): "
            f"{', '.join(selected_sections)}",
            flush=True,
        )
        metadata["selected_sow_sections"] = selected_sections
        from app.core.section_formats import timeline_format
        try:
            metadata['timeline_format'] = timeline_format(request.form.get('timeline_format') or record.get('timeline_format'))
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)}), 400

        scope_id = str(record.get("source_scope_id") or project_source_scope(record))
        metadata["source_scope_id"] = scope_id
        source_changes = []
        source_records = []
        store = SourceDocumentStore()
        for index, upload in enumerate(uploads, 1):
            filename = secure_filename(upload.filename)
            path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                f"refine_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{index}_{filename}",
            )
            upload.save(path)
            temp_paths.append(path)
            extracted = read_document(path)
            if not extracted or len(extracted.strip()) < 10:
                return jsonify({
                    "success": False,
                    "error": f"Could not extract readable content from {upload.filename}",
                }), 422
            stored = store.ingest(scope_id, path, upload.filename, extracted)
            source_records.append(public_source_metadata(stored))
            if stored.get("context"):
                source_changes.append(str(stored["context"]))
            print(
                f"[REFINE] {upload.filename}: {stored.get('comparison')} "
                f"(revision {stored.get('revision')}, reused={stored.get('reused', False)})",
                flush=True,
            )
        metadata["source_documents"] = [
            public_source_metadata(item) for item in store.list_documents(scope_id)
        ]

        initial_state = {
            "metadata": metadata,
            "objective": instructions,
            "additional_details": instructions,
            "mode": mode,
            "source_file": None,
            "analyzed_requirements": None,
            "validated_requirements": None,
            "poc_content": None,
            "output_path": None,
            "json_path": None,
            "errors": [],
            "current_step": "start",
            "supporting_documents": [],
            "supporting_context": None,
            "selected_sow_sections": selected_sections,
            "pricing_result": None,
            "scope_generation_seconds": None,
            "preview_started_at": preview_started_at,
            "refinement_request": {
                "baseline_sow": baseline_sow,
                "instructions": instructions,
                "source_changes": "\n\n".join(source_changes),
            },
        }
        preview_id = create_preview_id()
        store_preview_data(preview_id, {}, metadata, mode)
        with preview_lock:
            preview_storage[preview_id].update({
                "status": "initializing",
                "progress": 0,
                "current_step": "Preparing SOW refinement...",
                "source_diagnostics": {
                    "refinement": True,
                    "parent_document_id": document_id,
                    "documents_received": len(uploads),
                    "documents_reused": sum(1 for item in source_records if item.get("reused")),
                    "documents_changed": sum(1 for item in source_records if item.get("comparison") == "changed"),
                },
            })
        from app.preview.async_preview import process_preview_async
        process_preview_async(preview_id, initial_state, True, on_complete=_save_preview_as_draft)
        _schedule_preview_auto_draft(preview_id)
        return jsonify({
            "success": True,
            "preview_id": preview_id,
            "status": "initializing",
            "mode": mode,
            "metadata": metadata,
            "source_documents": source_records,
            "message": "SOW refinement preview started",
        }), 202
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 500
    finally:
        for path in temp_paths:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

@app.route('/api/preview', methods=['POST'])
def generate_preview():
    """
    API 1: Generate content preview without creating document
    Returns preview_id immediately and processes everything in background
    
    For POC_TO_PROD: Extracts text from uploaded document first
    """
    preview_started_at = time.perf_counter()
    uploaded_file_path = None
    
    try:
        print("\n[API] POST /api/preview - Generating content preview...")
        business_unit, denied = _business_unit_for_new_record()
        if denied:
            return denied
        ownership = _ownership_metadata(business_unit)
        
        mode = request.form.get('mode', '').upper()
        
        if not mode or mode not in ["POC", "PROD", "POC_TO_PROD"]:
            return jsonify({
                "success": False,
                "error": "Invalid or missing mode (POC, PROD, or POC_TO_PROD)"
            }), 400

        custom_template_id = request.form.get('custom_template_id', '').strip()
        custom_template = None
        if custom_template_id:
            try:
                custom_template = CustomTemplateStore().get(custom_template_id)
            except Exception as exc:
                return jsonify({"success": False, "error": f"Could not load custom template: {exc}"}), 500
            if not custom_template:
                return jsonify({"success": False, "error": "Custom template not found"}), 404
            if int(custom_template.get("schema_version") or 0) < CustomTemplateStore.SCHEMA_VERSION:
                return jsonify({
                    "success": False,
                    "error": "This preset uses the previous extraction format. Re-upload the source SOW to create a format-only template.",
                }), 409
            identity = current_identity()
            if (
                not bool(custom_template.get("saved"))
                and str(custom_template.get("owner_email") or "").casefold() != identity.email.casefold()
            ):
                return jsonify({"success": False, "error": "This template extraction belongs to another user"}), 403

        declared_supporting_count = request.form.get('supporting_doc_count', '').strip()
        if declared_supporting_count:
            try:
                declared_supporting_count = int(declared_supporting_count)
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": "supporting_doc_count must be an integer",
                }), 400
            actual_supporting_count = len([
                item for item in request.files.getlist('supporting_docs')
                if item and item.filename
            ])
            if actual_supporting_count != declared_supporting_count:
                return jsonify({
                    "success": False,
                    "error": (
                        "Supporting-document multipart transfer was incomplete; "
                        f"the browser sent {declared_supporting_count} file(s) but the server "
                        f"received {actual_supporting_count}. Generation was not started."
                    ),
                    "supporting_documents_declared": declared_supporting_count,
                    "supporting_documents_received": actual_supporting_count,
                }), 400

        from app.core.sow_section_preferences import parse_selected_section_ids
        try:
            selected_sow_sections = parse_selected_section_ids(
                request.form.get('selected_sow_sections'), mode
            )
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        selected_custom_ids = {item for item in selected_sow_sections if item.startswith("custom_")}
        valid_custom_ids = {
            str(item.get("id")) for item in (custom_template or {}).get("sections", [])
        }
        if selected_custom_ids and not custom_template:
            return jsonify({
                "success": False,
                "error": "Custom extracted sections require a selected custom template",
            }), 400
        unknown_custom = sorted(selected_custom_ids - valid_custom_ids)
        if unknown_custom:
            return jsonify({
                "success": False,
                "error": f"Unknown custom template section(s): {', '.join(unknown_custom)}",
            }), 400
        
        # Always use async mode now - remove async parameter check
        use_fast_mode = request.form.get('fast_mode', 'true').lower() == 'true'
        
        # Handle POC_TO_PROD mode - extract text from document
        extracted_text = None
        source_file = None
        document_only_request = False
        has_supporting_source = False
        
        # Initialize variables with defaults
        company_name = None
        author_name = None
        project_name = None
        objective = None
        document_date = datetime.now().strftime("%d %B %Y")
        version = '1.0'
        
        if mode == "POC_TO_PROD":
            if 'file' not in request.files or not request.files['file'].filename:
                return jsonify({
                    "success": False,
                    "error": "POC_TO_PROD mode requires a supported document upload"
                }), 400
            
            file = request.files['file']
            file_ext = Path(file.filename).suffix.lower()
            
            if file_ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
                return jsonify({
                    "success": False,
                    "error": "Unsupported file type. Supported files: PDF, Word, Excel, and TXT."
                }), 415
            
            # Save file temporarily
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            uploaded_file_path = filepath
            source_file = filepath
            
            print(f"   📄 Extracting text from: {filename}")
            
            # Extract text using doc_reader
            extracted_text = read_document(filepath)
            
            if not extracted_text or len(extracted_text.strip()) < 50:
                return jsonify({
                    "success": False,
                    "error": "Could not extract sufficient text from document"
                }), 400
            
            print(f"   ✓ Extracted {len(extracted_text)} characters")
            
            # Extract metadata from the document
            print(f"   📋 Extracting metadata from document...")
            extracted_metadata = extract_metadata_from_document(filepath)
            
            if extracted_metadata:
                # Update metadata with extracted values
                company_name = extracted_metadata.get("company_name", "Unknown Company")
                author_name = extracted_metadata.get("author_name", "Unknown Author")
                project_name = extracted_metadata.get("project_title", "Unknown Project")
                document_date = extracted_metadata.get("document_date", document_date)
                version = extracted_metadata.get("version", version)
                
                print(f"   ✓ Extracted metadata:")
                print(f"      Company: {company_name}")
                print(f"      Project: {project_name}")
                print(f"      Author: {author_name}")
            else:
                # Fallback if metadata extraction fails
                company_name = "Unknown Company"
                author_name = "Unknown Author"
                project_name = "Unknown Project"
            
            # For POC_TO_PROD, we don't need other fields to be required
            objective = "Convert POC to Production document"
        
        else:
            # For POC and PROD modes, accept either typed scope or an uploaded
            # BRD/supporting document as the authoritative project source.
            company_name = request.form.get('company_name', '').strip()
            author_name = request.form.get('author_name', '').strip()
            project_name = request.form.get('project_name', '').strip()
            
            # ✅ DEBUG: Log all form data to see what frontend is sending
            print(f"\n🔍 DEBUG: Form data received:")
            for key, value in request.form.items():
                print(f"   {key}: {value}")
            objective = (
                request.form.get('additional_details', '').strip()
                or request.form.get('objective', '').strip()
            )

            uploaded_supporting = [
                item for item in request.files.getlist('supporting_docs')
                if item and item.filename
            ]
            if any(Path(item.filename).suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS
                   for item in uploaded_supporting):
                return jsonify({
                    "success": False,
                    "error": "Unsupported file type. Supported files: PDF, Word, Excel, and TXT.",
                }), 415
            has_supporting_source = bool(uploaded_supporting)
            document_only_request = not objective and has_supporting_source
            
            if not all([company_name, author_name, project_name]) or not (
                objective or has_supporting_source
            ):
                return jsonify({
                    "success": False,
                    "error": (
                        f"{mode} mode requires company_name, author_name, project_name, "
                        "and either a BRD/supporting document or sufficient additional details"
                    )
                }), 400
            if not objective:
                objective = ""
            
            # Get optional fields for POC/PROD
            document_date = request.form.get('document_date', document_date)
            version = request.form.get('version', version)
        
        # Prepare metadata
        pricing_region = request.form.get('pricing_region', '').strip().lower()
        from app.core.section_formats import timeline_format
        try:
            selected_timeline_format = timeline_format(request.form.get('timeline_format'))
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)}), 400
        if pricing_region and not re.fullmatch(r'[a-z]{2}(?:-gov)?-[a-z]+-\d', pricing_region):
            return jsonify({
                "success": False,
                "error": "Invalid AWS pricing region code. Use a value such as ap-south-1 or us-east-1."
            }), 400
        metadata = {
            "company_name": company_name,
            "author_name": author_name,
            "author_org": "Shellkode",
            "author_org_description": "Shellkode specializes in developing advanced data and AI solutions for businesses.",
            "document_date": document_date,
            "version": version,
            "start_date": request.form.get('start_date', '').strip(),
            "end_date": request.form.get('end_date', '').strip(),
            "timezone": "IST",
            "project_title": project_name,
            "selected_sow_sections": selected_sow_sections,
            "custom_template_id": custom_template_id,
            "custom_template_name": str((custom_template or {}).get("name") or "Uploaded custom template"),
            "pricing_region": pricing_region,
            "timeline_format": selected_timeline_format,
            "pricing_include_proposed": request.form.get(
                'pricing_include_proposed', 'true'
            ).strip().lower() not in {'0', 'false', 'no', 'off'},
            "pricing_read_cost": request.form.get(
                'pricing_read_cost', 'true'
            ).strip().lower() not in {'0', 'false', 'no', 'off'},
            **ownership,
        }
        
        # ✅ NEW: Capture project_id and account_id if provided (for linking SOW to project later)
        project_id = request.form.get('project_id', '').strip()
        account_id = request.form.get('account_id', '').strip()
        
        if project_id:
            metadata["project_id"] = project_id
            print(f"   🔗 Will link to project: {project_id}")
        
        if account_id:
            metadata["account_id"] = account_id
            print(f"   🔗 Will link to account: {account_id}")
        
        print(f"   📋 Generating {mode} content preview...")
        print(f"      Company: {company_name}")
        print(f"      Project: {project_name}")
        print(f"      Mode: ASYNC | {'FAST' if use_fast_mode else 'STANDARD'}")
        

        # Extract supporting documents if provided (POC / PROD modes)
        supporting_files = []
        supporting_context = None
        supporting_docs_received = 0
        supporting_docs_extracted = 0
        supporting_uploads = []
        if 'supporting_docs' in request.files:
            files_list = request.files.getlist('supporting_docs')
            supporting_docs_received = len([
                item for item in files_list if item and item.filename
            ])
            print(f"   📎 Received {len(files_list)} supporting document(s)")
            for idx, support_file in enumerate(files_list, 1):
                if support_file and support_file.filename:
                    file_ext = Path(support_file.filename).suffix.lower()
                    if file_ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
                        return jsonify({
                            "success": False,
                            "error": "Unsupported file type. Supported files: PDF, Word, Excel, and TXT.",
                        }), 415
                    filename = secure_filename(support_file.filename)
                    unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    support_file.save(filepath)
                    supporting_files.append(filepath)
                    supporting_uploads.append((filepath, support_file.filename))

            if supporting_files:
                try:
                    supporting_context, supporting_docs_extracted = (
                        extract_supporting_documents_with_diagnostics(supporting_files)
                    )
                    supporting_context = supporting_context or None
                    if supporting_context:
                        print(f"   ✅ Extracted {len(supporting_context)} chars from supporting docs")
                    else:
                        print(f"   ⚠️  No content extracted from supporting documents")
                except Exception as e:
                    print(f"   ❌ Error extracting supporting documents: {e}")
                    supporting_context = None
                    supporting_docs_extracted = 0

        # Never silently convert an unreadable/missing multipart upload into a
        # generic SOW.  In document-only mode, successful extraction is a hard
        # precondition for starting the agent graph.
        if supporting_docs_received and (
            not supporting_context or supporting_docs_extracted != supporting_docs_received
        ):
            for fp in supporting_files:
                try:
                    if os.path.exists(fp):
                        os.remove(fp)
                except Exception:
                    pass
            return jsonify({
                "success": False,
                "error": (
                    "One or more supporting documents were received but could not be read "
                    "completely. Check that every document contains selectable text or enable OCR."
                ),
                "supporting_documents_received": supporting_docs_received,
                "supporting_documents_extracted": supporting_docs_extracted,
            }), 422

        # Persist source originals and extraction sidecars for future version
        # diffs. Failure here does not discard an otherwise valid generation;
        # the preview records a warning so the user is not misled about reuse.
        if supporting_uploads and not app.config.get("TESTING"):
            metadata['source_documents'] = []
            try:
                source_store = SourceDocumentStore()
                source_scope_id = project_source_scope(metadata)
                metadata["source_scope_id"] = source_scope_id
                # A project's archive is not the current generation's evidence.
                # Record only the documents uploaded for this request.
                metadata["source_documents"] = [public_source_metadata(
                    source_store.ingest(source_scope_id, path, original_name))
                    for path, original_name in supporting_uploads]
                print(
                    f"[SOURCE] Stored {len(supporting_uploads)} supporting document(s) "
                    f"under project scope {source_scope_id[:8]}",
                    flush=True,
                )
            except Exception as exc:
                metadata["source_storage_warning"] = "Supporting documents could not be archived for reuse"
                print(f"[SOURCE] Supporting-document archive unavailable: {exc}", flush=True)

        # Generate content using graph (without building document)
        initial_state = {
            "metadata": metadata,
            "objective": objective,
            "additional_details": objective,
            "mode": mode,
            "source_file": source_file,  # For POC_TO_PROD
            "analyzed_requirements": None,
            "validated_requirements": None,
            "poc_content": None,
            "output_path": None,
            "json_path": None,
            "errors": [],
            "current_step": "start",
            "supporting_documents": supporting_files,
            "supporting_context": supporting_context,
            "selected_sow_sections": selected_sow_sections,
            "custom_template_id": custom_template_id or None,
            "custom_template_markdown": (custom_template or {}).get("markdown"),
            "custom_template_sections": (custom_template or {}).get("sections") or [],
            "pricing_result": None,
            "scope_generation_seconds": None,
            "preview_started_at": preview_started_at,
        }
        
        # Create preview ID first
        preview_id = create_preview_id()
        
        # Always process in background now
        from app.preview.async_preview import process_preview_async
        
        # Store initial preview data with INITIALIZING status
        preview_data = store_preview_data(
            preview_id=preview_id,
            content={},  # Empty initially
            metadata=metadata,
            mode=mode
        )
        
        # Set initial status to INITIALIZING
        with preview_lock:
            if preview_id in preview_storage:
                preview_storage[preview_id]["status"] = "initializing"
                preview_storage[preview_id]["progress"] = 0
                preview_storage[preview_id]["current_step"] = "Initializing preview generation..."
                preview_storage[preview_id]["source_diagnostics"] = {
                    "document_only": document_only_request,
                    "documents_received": supporting_docs_received,
                    "documents_extracted": supporting_docs_extracted,
                    "extracted_characters": len(supporting_context or ""),
                }
        
        # Start async processing (supporting_context already extracted — files not needed by thread)
        process_preview_async(preview_id, initial_state, use_fast_mode, on_complete=_save_preview_as_draft)
        _schedule_preview_auto_draft(preview_id)

        # Safe to clean up temp supporting files now — content already extracted into supporting_context
        for fp in supporting_files:
            try:
                if os.path.exists(fp):
                    os.remove(fp)
            except Exception:
                pass

        print(f"   ✅ Preview generation started: {preview_id}")
        
        response_data = {
            "success": True,
            "preview_id": preview_id,
            "supporting_documents_received": supporting_docs_received,
            "supporting_documents_extracted": supporting_docs_extracted,
            "supporting_context_chars": len(supporting_context or ""),
            "document_only_source_mode": document_only_request,
            "mode": mode,
            "metadata": metadata,
            "status": "initializing",
            "message": "Preview generation started. Use /api/preview/status/{preview_id} to check progress."
        }
        
        response = jsonify(response_data)
        response.headers['Content-Type'] = 'application/json'
        response.headers['Connection'] = 'close'
        response.headers['Cache-Control'] = 'no-cache'
        
        return response, 202  # Accepted
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        response = jsonify({
            "success": False,
            "error": str(e)
        })
        
        # Add explicit headers even for error responses
        response.headers['Content-Type'] = 'application/json'
        response.headers['Connection'] = 'close'
        response.headers['Cache-Control'] = 'no-cache'
        
        return response, 500

def extract_sections_from_template(template_content: str, mode: str) -> list:
    """
    Extract sections from template by analyzing TOC and section headers
    """
    sections = []
    
    # Extract TOC content
    toc_match = re.search(r'## Table_of_contents\s*\n(.*?)(?=\n\[|$)', template_content, re.DOTALL)
    
    if toc_match:
        toc_content = toc_match.group(1)
        
        # Parse TOC entries
        toc_lines = [line.strip() for line in toc_content.split('\n') if line.strip()]
        
        for line in toc_lines:
            # Match numbered TOC entries like "1. About Shellkode"
            toc_match = re.match(r'^\d+\.\s*(.+)', line)
            if toc_match:
                section_title = toc_match.group(1).strip()
                
                # Convert title to section key
                section_key = title_to_section_key(section_title)
                
                # Get category and description
                category = categorize_section_by_title(section_title)
                description = get_section_description(section_title, mode)
                
                sections.append({
                    "key": section_key,
                    "title": section_title,
                    "name": section_title,
                    "description": description,
                    "category": category,
                    "mode": mode,
                    "is_editable": is_section_editable(section_key),
                    "edit_examples": [
                        f"Update the {section_title} section",
                        f"Add more details to {section_title}",
                        f"Modify the {section_title} content"
                    ]
                })
    
    # Also extract sections from template headers (for subsections)
    if mode == "PROD":
        # Extract numbered subsections like "### 1. Application & Backend Implementation"
        subsection_matches = re.findall(r'### (\d+\.\s*[^#\n]+)', template_content)
        
        for match in subsection_matches:
            section_title = match.strip()
            section_key = title_to_section_key(section_title)
            
            # Avoid duplicates
            if not any(s['key'] == section_key for s in sections):
                category = categorize_section_by_title(section_title)
                description = get_section_description(section_title, mode)
                
                sections.append({
                    "key": section_key,
                    "title": section_title,
                    "name": section_title,
                    "description": description,
                    "category": category,
                    "mode": mode,
                    "is_editable": True,
                    "edit_examples": [
                        f"Update the {section_title} section",
                        f"Add more details to {section_title}",
                        f"Modify the {section_title} content"
                    ]
                })
    
    return sections

def title_to_section_key(title: str) -> str:
    """Convert section title to section key"""
    # Remove numbers and special characters, convert to lowercase with underscores
    key = re.sub(r'^\d+\.\s*', '', title)  # Remove leading numbers
    key = re.sub(r'[{}\[\]()]', '', key)   # Remove brackets and braces
    key = re.sub(r'[^\w\s]', '', key)      # Remove special chars except spaces
    key = key.lower().replace(' ', '_')    # Convert to snake_case
    key = re.sub(r'_+', '_', key)          # Remove multiple underscores
    key = key.strip('_')                   # Remove leading/trailing underscores
    
    # Handle special cases and mappings
    key_mappings = {
        'about_author_org_short': 'about_shellkode',
        'about_company_name': 'about_company',
        'executive_summary_and_project_overview': 'project_overview',
        'detailed_scope_of_work': 'scope_of_work',
        'detailed_production_scope_of_work': 'scope_of_work',
        'architecture_overview': 'architecture_diagram',
        'shellkode_implementation_cost': 'implementation_cost',
        'project_overview_objectives': 'project_overview_objectives',
        'technical_specifications_system_design': 'technical_specifications_system_design',
        'architecture_integrations': 'architecture_integrations',
        'customer_dependencies_responsibilities': 'customer_dependencies_responsibilities',
        'day_2_operations_support': 'day_2_operations_support',
        'acceptance_and_signatories_to_statement_of_work': 'acceptance_and_signatories_to_statement_of_work'
    }
    
    return key_mappings.get(key, key)

def categorize_section_by_title(title: str) -> str:
    """Categorize section based on title"""
    title_lower = title.lower()
    
    if any(word in title_lower for word in ['cost', 'pricing', 'budget', 'aws pricing']):
        return 'financial'
    elif any(word in title_lower for word in ['scope', 'work', 'deliverable', 'out of scope']):
        return 'scope'
    elif any(word in title_lower for word in ['timeline', 'duration', 'phase', 'deliverables']):
        return 'timeline'
    elif any(word in title_lower for word in ['assumption', 'dependencies', 'responsibilities', 'acceptance', 'criteria']):
        return 'requirements'
    elif any(word in title_lower for word in ['architecture', 'technical', 'specifications', 'design', 'system']):
        return 'technical'
    elif any(word in title_lower for word in ['overview', 'objectives', 'about', 'summary']):
        return 'overview'
    elif any(word in title_lower for word in ['terms', 'conditions', 'authorization', 'signatories']):
        return 'legal'
    elif any(word in title_lower for word in ['contacts', 'reporting']):
        return 'administrative'
    elif any(word in title_lower for word in ['operations', 'support', 'day-2']):
        return 'operational'
    elif any(word in title_lower for word in ['change', 'termination', 'management']):
        return 'governance'
    else:
        return 'other'

def get_section_description(title: str, mode: str) -> str:
    """Get description for section based on title and mode"""
    descriptions = {
        'About Shellkode': 'Company information and capabilities',
        'Project Overview': 'High-level project description and goals',
        'Scope of Work': 'Detailed project deliverables and tasks',
        'Solution Architecture': 'Solution design, component interactions and architecture diagram',
        'Customer Dependencies': 'Requirements and dependencies from customer',
        'Assumptions': 'Project assumptions and constraints',
        'Out Of Scope': 'Items explicitly excluded from project',
        'Project Timeline': 'Project schedule in the selected table or Gantt format',
        'AWS Pricing': 'AWS service costs and pricing estimates',
        'Customer Responsibilities': 'Customer obligations and responsibilities',
        'Duration of Work': 'Project timeline and duration',
        'Shellkode Implementation Cost': 'Resource allocation and implementation costs',
        'Success Criteria': 'Measurable success metrics and acceptance criteria',
        'Deliverable Acceptance': 'Process for accepting deliverables',
        'Change Order': 'Process for handling scope changes',
        'Project Plan Termination': 'Conditions for project termination',
        'Contacts and Reporting': 'Key contacts and reporting structure',
        'Marketing Authorization': 'Permission for marketing and reference use',
        'Terms & Conditions': 'Legal terms and conditions',
        'Acceptance and Signatories to Statement of Work': 'Document signatures and acceptance',
        
        # PROD-specific
        'Project Overview & Objectives': 'Detailed business and technical objectives',
        'Technical Specifications & System Design': 'Comprehensive technical specifications',
        'Architecture & Integrations': 'Production architecture and integration points',
        'Customer Dependencies & Responsibilities': 'Combined customer requirements',
        'Day-2 Operations & Support': 'Ongoing operations and support model',
        'Design Validation': 'Design review and validation process',
        'Change Management': 'Change management process and procedures'
    }
    
    return descriptions.get(title, f'Content for {title}')

def is_section_editable(section_key: str) -> bool:
    """Check if section is editable (exclude static/system sections)"""
    non_editable = {
        'cover_page', 'toc_structure', 'table_of_contents',
        'contacts_and_reporting', 'terms_conditions', 
        'acceptance_and_signatories_to_statement_of_work',
        'marketing_authorization', 'project_plan_termination'
    }
    return section_key not in non_editable

def group_sections_by_category(sections: list) -> dict:
    """Group sections by category"""
    categories = {}
    for section in sections:
        category = section.get('category', 'other')
        if category not in categories:
            categories[category] = []
        categories[category].append(section)
    return categories


@app.route('/api/preview/status/<preview_id>', methods=['GET'])
def get_preview_status_api(preview_id):
    """
    API: Get preview generation status for async mode
    Returns full response like preview API when complete
    """
    try:
        with preview_lock:
            if preview_id not in preview_storage:
                return jsonify({
                    "success": False,
                    "error": "Preview not found"
                }), 404
            
            preview_data = preview_storage[preview_id]
            denied = _preview_denied(preview_data)
            if denied:
                return denied
            status = preview_data.get("status", "initializing")
            # Regeneration retains a fully usable previous preview. Reopening it
            # must show that preview and attach to the job, not the initial spinner.
            if (preview_data.get('architecture_job') or {}).get('status') == 'running':
                status = 'ready'
            preview_data["last_activity_at"] = time.time()
            metadata = preview_data.get("metadata", {})
            
            # ✅ ENHANCED: Ensure all metadata fields have values (no N/A)
            metadata_response = {
                "company_name": metadata.get("company_name", "Unknown Company"),
                "project_title": metadata.get("project_title", "Unknown Project"),
                "author_name": metadata.get("author_name", "Unknown Author"),
                "author_org": metadata.get("author_org", "Shellkode"),
                "document_date": metadata.get("document_date", datetime.now().strftime("%d %B %Y")),
                "start_date": metadata.get("start_date") or "",
                "end_date": metadata.get("end_date") or "",
                "version": metadata.get("version", "1.0"),
                "timezone": metadata.get("timezone", "IST"),
                "author_org_description": metadata.get("author_org_description", "Shellkode specializes in developing advanced data and AI solutions for businesses.")
                ,"business_unit": metadata.get("business_unit")
            }
            
            # Base response structure
            response_data = {
                "success": True,
                "preview_id": preview_id,
                "mode": preview_data.get("mode"),
                "metadata": metadata_response,
                "status": status,
                "progress": preview_data.get("progress", 0),
                "current_step": preview_data.get("current_step", "Initializing..."),
                "is_complete": status == "ready",
                "has_error": status == "failed",
                "source_diagnostics": preview_data.get("source_diagnostics", {}),
                "architecture_job": preview_data.get('architecture_job'),
                # ✅ Add metadata fields at top level for easier frontend access
                "company_name": metadata_response["company_name"],
                "project_title": metadata_response["project_title"],
                "author_name": metadata_response["author_name"],
                "author_org": metadata_response["author_org"],
                "document_date": metadata_response["document_date"],
                "start_date": metadata_response["start_date"],
                "end_date": metadata_response["end_date"],
                "version": metadata_response["version"],
                "timezone": metadata_response["timezone"],
                "author_org_description": metadata_response["author_org_description"]
            }
            
            # Add error details if failed
            if status == "failed":
                response_data["error"] = preview_data.get("error", "Unknown error")
                response_data["message"] = f"Preview generation failed: {response_data['error']}"
            
            # Add content if ready (full response like preview API)
            elif status == "ready":
                response_data["content"] = preview_data.get("content", {})
                final_state = preview_data.get("final_state") or {}
                response_data["pricing_result"] = final_state.get("pricing_result")
                response_data["message"] = "Content preview generated successfully. Use /api/edit to make changes or /api/finalize to create document."
            
            # Add progress message for in-progress statuses
            else:
                response_data["message"] = f"Preview generation in progress: {response_data['current_step']}"
            
            return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/preview/<preview_id>/heartbeat', methods=['POST'])
def heartbeat_preview(preview_id):
    """Keep a completed preview active while a reviewer has its modal open."""
    with preview_lock:
        preview = preview_storage.get(preview_id)
        if not preview:
            return jsonify({"success": False, "error": "Preview not found"}), 404
        denied = _preview_denied(preview)
        if denied:
            return denied
        preview["last_activity_at"] = time.time()
    return jsonify({"success": True}), 200


@app.route('/api/preview/<preview_id>/draft', methods=['POST'])
def save_preview_draft(preview_id):
    """Persist a completed preview as a durable SOW-record draft."""
    with preview_lock:
        preview = preview_storage.get(preview_id)
        if preview:
            denied = _preview_denied(preview)
            if denied:
                return denied
    result = _save_preview_as_draft(preview_id, automatic=False)
    if result.get("processing"):
        return jsonify(result), 202
    return jsonify(result), (200 if result.get("success") else 409)


@app.route('/api/preview/<preview_id>', methods=['DELETE'])
def discard_preview(preview_id):
    """Discard an active preview. A reopened durable draft remains untouched."""
    with preview_lock:
        preview = preview_storage.get(preview_id)
        if not preview:
            return jsonify({"success": True, "discarded": False}), 200
        denied = _preview_denied(preview)
        if denied:
            return denied
        if preview.get("status") in {"draft_saving", "document_finalizing"}:
            return jsonify({"success": False, "error": "A save is in progress; wait before discarding"}), 409
        auto_draft_id = preview.get("metadata", {}).get("draft_document_id") if preview.get("autosaved_draft") else None
        if auto_draft_id:
            preview["status"] = "draft_saving"
        else:
            del preview_storage[preview_id]
    if auto_draft_id:
        try:
            record = DynamoDBHandler().get_document_by_id(auto_draft_id)
            if record and record.get("status") == "draft":
                _delete_draft_record(record)
            delete_preview_data(preview_id)
        except Exception:
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["status"] = "ready"
            return jsonify({"success": False, "error": "Could not discard the saved draft; please retry"}), 500
    from app.core.nodes import clear_token_usage
    clear_token_usage(preview_id)
    return jsonify({"success": True, "discarded": True}), 200


@app.route('/api/sows/<document_id>/draft/open', methods=['POST'])
def open_saved_draft(document_id):
    """Restore a durable draft snapshot to the ordinary preview editor."""
    record = DynamoDBHandler().get_document_by_id(document_id)
    if not record or str(record.get("status") or "").lower() != "draft":
        return jsonify({"success": False, "error": "Draft not found"}), 404
    denied = _resource_denied(record)
    if denied:
        return denied
    with preview_lock:
        for active_id, active in preview_storage.items():
            if active.get("metadata", {}).get("draft_document_id") == document_id and (
                    active.get("status") == "ready" or (active.get('architecture_job') or {}).get('status') == 'running'):
                return jsonify({"success": True, "preview_id": active_id}), 200
    location = str(record.get("draft_preview_s3_url") or "").strip()
    if not location:
        return jsonify({"success": False, "error": "Draft preview data is unavailable"}), 409
    try:
        bucket, key = parse_s3_location(location)
        body = get_s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
        snapshot = json.loads(body.decode("utf-8"))
        metadata = dict(snapshot.get("metadata") or {})
        metadata.update({
            "draft_document_id": document_id,
            "version": record.get("version"),
            "draft_original_s3_url": record.get("s3_url"),
            "draft_preview_s3_url": location,
            "business_unit": record.get("business_unit"),
            "owner_email": record.get("owner_email"),
            "owner_name": record.get("owner_name"),
        })
        preview_id = create_preview_id()
        store_preview_data(preview_id, snapshot.get("content") or {}, metadata,
                           snapshot.get("mode") or record.get("mode") or "POC")
        with preview_lock:
            preview_storage[preview_id].update({
                "status": "ready", "progress": 100,
                "current_step": "Draft ready for review",
                "final_state": snapshot.get("final_state") or {},
                "token_usage": snapshot.get("token_usage") or {},
                "total_tokens": int(snapshot.get("total_tokens") or 0),
                "edit_count": int(snapshot.get('edit_count') or 0),
                "architecture_changes": snapshot.get('architecture_changes', []),
                "ready_at": time.time(), "last_activity_at": time.time(),
                # The persisted record already protects this preview from loss.
                "auto_draft_enabled": False,
            })
        return jsonify({"success": True, "preview_id": preview_id}), 200
    except Exception as exc:
        print(f"[DRAFT] Could not open {document_id}: {exc}", flush=True)
        return jsonify({"success": False, "error": "Unable to open this draft"}), 500


@app.route('/api/sows/<document_id>/draft', methods=['DELETE'])
def delete_saved_draft(document_id):
    """Allow a draft owner (or administrator) to permanently delete a draft."""
    record = DynamoDBHandler().get_document_by_id(document_id)
    if not record or str(record.get("status") or "").lower() != "draft":
        return jsonify({"success": False, "error": "Draft not found"}), 404
    identity = current_identity()
    owner = str(record.get("owner_email") or "").strip().lower()
    if not identity.is_admin and owner != identity.email.strip().lower():
        return jsonify({"success": False, "error": "Only the draft owner or an administrator can delete it"}), 403
    _delete_draft_record(record)
    return jsonify({"success": True, "message": "Draft permanently deleted"}), 200


@app.before_request
def protect_architecture_revision():
    """Block competing writes, including older edit/finalize endpoints, while revising."""
    if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return None
    if request.endpoint in {'regenerate_preview_architecture', 'heartbeat_preview'}:
        return None
    data = request.get_json(silent=True) if request.is_json else {}
    if not isinstance(data, dict):
        data = {}
    preview_id = (request.view_args or {}).get('preview_id') or (data or {}).get('preview_id')
    document_id = (request.view_args or {}).get('document_id')
    if not preview_id and document_id and request.method == 'DELETE':
        with preview_lock:
            preview_id = next((pid for pid, item in preview_storage.items()
                               if item.get('metadata', {}).get('draft_document_id') == document_id
                               and (item.get('architecture_job') or {}).get('status') == 'running'), None)
    if preview_id:
        with preview_lock:
            preview = preview_storage.get(preview_id)
            if preview and (preview.get('architecture_job') or {}).get('status') == 'running':
                denied = _preview_denied(preview)
                if denied:
                    return denied
                return jsonify(success=False, error='Architecture regeneration is in progress. Wait before editing or saving.'), 409


def _run_architecture_revision(preview_id, job_id, snapshot, instructions):
    from app.preview.architecture_regeneration import regenerate
    from app.core.nodes import bind_token_usage, unbind_token_usage, get_token_usage, clear_token_usage
    token = bind_token_usage(job_id)
    def combined_usage():
        usage = dict(snapshot.get('token_usage') or {})
        usage.setdefault('total_tokens', int(snapshot.get('total_tokens') or 0))
        extra = get_token_usage(job_id)
        for key in ('total_input_tokens', 'total_output_tokens', 'total_tokens', 'api_calls'):
            usage[key] = int(usage.get(key) or 0) + int(extra.get(key) or 0)
        models = dict(usage.get('models') or {})
        for key, count in (extra.get('models') or {}).items():
            models[key] = models.get(key, 0) + count
        usage['models'] = models
        return usage
    def progress(message):
        print(f'[DIAGRAM][REGENERATE] job={job_id}; {message}', flush=True)
        with preview_lock:
            live = preview_storage.get(preview_id)
            if live and (live.get('architecture_job') or {}).get('id') == job_id:
                live['architecture_job']['message'] = message
    try:
        candidate = regenerate(snapshot, instructions, Config(), progress)
        candidate['_architecture_job_id'] = job_id
        candidate['token_usage'] = combined_usage()
        candidate['total_tokens'] = int(candidate['token_usage'].get('total_tokens') or 0)
        progress('Saving the updated recoverable draft')
        # Persist both image and text before reporting success. Existing draft ID
        # is reused, so regeneration does not create a new completed SOW/version.
        result = _save_preview_as_draft(preview_id, automatic=True, revision_candidate=candidate)
        if not result.get('success'):
            raise RuntimeError('The revision could not be saved. The previous preview is unchanged.')
        with preview_lock:
            live = preview_storage.get(preview_id)
            if live and (live.get('architecture_job') or {}).get('id') == job_id:
                live['architecture_job'].update(status='completed', message='Diagram and SOW updated',
                                                changes=candidate.get('architecture_changes', []))
    except Exception as exc:
        print(f'[DIAGRAM][REGENERATE] job={job_id}; failed={exc}', flush=True)
        with preview_lock:
            live = preview_storage.get(preview_id)
            if live and (live.get('architecture_job') or {}).get('id') == job_id:
                live.update(status='ready', progress=100)
                live['token_usage'] = combined_usage()
                live['total_tokens'] = live['token_usage']['total_tokens']
                live['architecture_job'].update(status='failed', error=str(exc)[:1000],
                                                message='Previous preview retained')
    finally:
        unbind_token_usage(token)
        clear_token_usage(job_id)


@app.route('/api/preview/<preview_id>/architecture-regeneration', methods=['POST', 'GET'])
def regenerate_preview_architecture(preview_id):
    data = (request.get_json(silent=True) or {}) if request.method == 'POST' else {}
    if not isinstance(data, dict):
        return jsonify(success=False, error='Expected a JSON object'), 400
    instructions = data.get('instructions', '')
    if not isinstance(instructions, str) or len(instructions) > 4000:
        return jsonify(success=False, error='Instructions must be text of at most 4000 characters'), 400
    with preview_lock:
        live = preview_storage.get(preview_id)
        if not live:
            return jsonify(success=False, error='Preview not found'), 404
        denied = _preview_denied(live)
        if denied:
            return denied
        job = live.get('architecture_job') or {}
        if request.method == 'GET':
            payload = {'success': True, 'job': job, 'preview_id': preview_id}
            if job.get('status') == 'completed':
                payload.update(content=live.get('content'), metadata=live.get('metadata'),
                               pricing_result=(live.get('final_state') or {}).get('pricing_result'))
            return jsonify(payload), 200
        if job.get('status') == 'running':
            return jsonify(success=True, job=job, preview_id=preview_id), 202
        if live.get('status') != 'ready':
            return jsonify(success=False, error='Preview is not ready'), 409
        state = live.get('final_state') or {}
        if not (state.get('supporting_context') or state.get('objective')):
            return jsonify(success=False, error='Original BRD context is unavailable for this preview. Generate a new preview.'), 409
        snapshot = copy.deepcopy(live)
        job_id = uuid.uuid4().hex
        live['architecture_job'] = {'id': job_id, 'status': 'running', 'message': 'Starting architecture regeneration',
                                    'started_at': datetime.now().isoformat()}
        live['status'] = 'architecture_regenerating'
        job = dict(live['architecture_job'])
    try:
        threading.Thread(target=_run_architecture_revision,
                         args=(preview_id, job_id, snapshot, instructions.strip()), daemon=True).start()
    except Exception:
        with preview_lock:
            live['status'] = 'ready'
            live['architecture_job'].update(status='failed', error='Unable to start regeneration')
        return jsonify(success=False, error='Unable to start regeneration'), 503
    return jsonify(success=True, job=job, preview_id=preview_id), 202


@app.route('/api/preview/<preview_id>/architecture-diagram', methods=['PUT'])
def update_preview_architecture_diagram(preview_id):
    """Persist draw.io XML and its exported PNG into an active preview."""
    data = request.get_json(silent=True) or {}
    xml = data.get("drawio_xml")
    image_data = data.get("image_data")
    diagram_index = data.get("diagram_index", 0)
    try:
        with preview_lock:
            preview_data = preview_storage.get(preview_id)
            if not preview_data:
                return jsonify({"success": False, "error": "Preview not found"}), 404
            denied = _preview_denied(preview_data)
            if denied:
                return denied
            if preview_data.get("status") != "ready":
                return jsonify({"success": False, "error": "Preview is not ready"}), 409
            content = preview_data.get("content")
            if not isinstance(content, dict):
                return jsonify({"success": False, "error": "Preview has no structured content"}), 409
            assets = content.get(ARCHITECTURE_ASSETS_KEY)
            if diagram_index == -1:
                existing = content.get('conceptual_flow_asset')
                if not isinstance(existing, dict):
                    return jsonify(success=False, error='Conceptual flow not found'), 404
            elif isinstance(assets, list):
                try:
                    diagram_index = int(diagram_index)
                except (TypeError, ValueError):
                    return jsonify({"success": False, "error": "Invalid diagram index"}), 400
                if diagram_index < 0 or diagram_index >= len(assets) or not isinstance(assets[diagram_index], dict):
                    return jsonify({"success": False, "error": "Architecture diagram not found"}), 404
                existing = assets[diagram_index]
            else:
                existing = content.get(ARCHITECTURE_ASSET_KEY)
                if not isinstance(existing, dict):
                    return jsonify({"success": False, "error": "Preview has no architecture diagram"}), 404
            asset = update_architecture_asset(
                xml,
                image_data,
                existing,
            )
            if diagram_index == -1:
                content['conceptual_flow_asset'] = asset
            elif isinstance(assets, list):
                assets[diagram_index] = asset
                content[ARCHITECTURE_ASSETS_KEY] = assets
            else:
                content[ARCHITECTURE_ASSET_KEY] = asset
            preview_data["last_modified"] = datetime.now().isoformat()
            preview_data["edit_count"] = preview_data.get("edit_count", 0) + 1
        return jsonify({"success": True, "asset": asset}), 200
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        print(f"❌ Architecture diagram update failed: {exc}")
        return jsonify({"success": False, "error": "Unable to save architecture diagram"}), 500


DIRECT_MARKDOWN_EDIT_RESERVED_KEYS = {
    'conceptual_flow_asset',
    "cover_page",
    "toc_structure",
    "table_of_contents",
    "tableofcontents",
    "table_contents",
    "generation_quality_summary",
    ARCHITECTURE_ASSET_KEY,
    ARCHITECTURE_ASSETS_KEY,
}


@app.route('/api/preview/<preview_id>/aws-pricing/recalculate', methods=['POST'])
def recalculate_preview_aws_pricing(preview_id):
    """Rebuild pricing from the preview's immutable source-grounded baseline."""
    data = request.get_json(silent=True) or {}
    with preview_lock:
        preview_data = preview_storage.get(preview_id)
        if not preview_data:
            return jsonify({"success": False, "error": "Preview not found"}), 404
        denied = _preview_denied(preview_data)
        if denied:
            return denied

        if preview_data.get("status") != "ready":
            return jsonify({"success": False, "error": "Preview is not ready"}), 409
        final_state = dict(preview_data.get("final_state") or {})
        metadata = {**(final_state.get("metadata") or {}), **(preview_data.get("metadata") or {})}
        requirements = dict(final_state.get("validated_requirements") or {})
        supporting_context = str(final_state.get("supporting_context") or "")
        expected_edit_count = preview_data.get('edit_count', 0)
    requested_region = str(data.get("pricing_region") or metadata.get("pricing_region") or "").strip().lower()
    if requested_region and not re.fullmatch(r'[a-z]{2}(?:-gov)?-[a-z]+-\d', requested_region):
        return jsonify({"success": False, "error": "Invalid AWS region code"}), 400
    metadata["pricing_region"] = requested_region
    if "pricing_include_proposed" in data:
        metadata["pricing_include_proposed"] = bool(data["pricing_include_proposed"])
    if "pricing_read_cost" in data:
        metadata["pricing_read_cost"] = bool(data["pricing_read_cost"])

    from app.core.nodes import bind_token_usage, get_token_usage, unbind_token_usage
    usage_token = bind_token_usage(preview_id)
    try:
        result = AwsPricingService(Config()).generate(requirements, metadata, supporting_context)
    finally:
        unbind_token_usage(usage_token)
    token_usage = get_token_usage(preview_id)
    rendered = render_aws_pricing_section(result)
    with preview_lock:
        preview_data = preview_storage.get(preview_id)
        if not preview_data:
            return jsonify({"success": False, "error": "Preview expired during recalculation"}), 404
        content = preview_data.get("content") or {}
        if preview_data.get('status') != 'ready' or preview_data.get('edit_count', 0) != expected_edit_count:
            return jsonify(success=False, error='Preview changed during pricing recalculation; retry when ready'), 409
        content["aws_pricing"] = rendered
        preview_data["content"] = content
        preview_data["metadata"].update(metadata)
        final_state = preview_data.get("final_state") or {}
        final_state["pricing_result"] = result
        final_state["metadata"] = metadata
        preview_data["final_state"] = final_state
        preview_data["token_usage"] = token_usage
        preview_data["total_tokens"] = int(token_usage.get("total_tokens") or 0)
        preview_data["last_modified"] = datetime.now().isoformat()
        preview_data["edit_count"] = preview_data.get("edit_count", 0) + 1
    return jsonify({
        "success": True,
        "preview_id": preview_id,
        "status": "ready",
        "progress": 100,
        "current_step": "AWS pricing recalculated",
        "mode": preview_data.get("mode"),
        "metadata": metadata,
        "content": content,
        "pricing_result": result,
    }), 200


@app.route('/api/preview/<preview_id>/content', methods=['PUT'])
def update_preview_content(preview_id):
    """Persist direct reviewer Markdown edits without invoking the LLM."""
    data = request.get_json(silent=True) or {}
    submitted = data.get("content")
    if not isinstance(submitted, dict) or not submitted:
        return jsonify({
            "success": False,
            "error": "content must be a non-empty object of section Markdown",
        }), 400
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in submitted.items()):
        return jsonify({
            "success": False,
            "error": "Every edited section must have a string key and Markdown string value",
        }), 400
    if any("\x00" in value for value in submitted.values()):
        return jsonify({"success": False, "error": "Markdown cannot contain null characters"}), 400

    with preview_lock:
        preview_data = preview_storage.get(preview_id)
        if not preview_data:
            return jsonify({"success": False, "error": "Preview not found"}), 404
        denied = _preview_denied(preview_data)
        if denied:
            return denied

        if preview_data.get("status") != "ready":
            return jsonify({"success": False, "error": "Preview is not ready"}), 409

        existing = preview_data.get("content")
        if not isinstance(existing, dict):
            return jsonify({"success": False, "error": "Preview has no structured content"}), 409

        editable_keys = {
            key
            for key, value in existing.items()
            if isinstance(value, str) and key not in DIRECT_MARKDOWN_EDIT_RESERVED_KEYS
        }
        unknown = sorted(set(submitted) - editable_keys)
        if unknown:
            return jsonify({
                "success": False,
                "error": f"Unknown or system-managed section(s): {', '.join(unknown)}",
            }), 400

        changed_sections = [
            key for key, value in submitted.items()
            if existing.get(key) != value
        ]
        # Rebuild from the existing mapping so section insertion order and every
        # system-managed value (including draw.io assets) remain untouched.
        merged_content = {
            key: submitted.get(key, value)
            for key, value in existing.items()
        }
        preview_data["content"] = merged_content
        preview_data["last_modified"] = datetime.now().isoformat()
        if changed_sections:
            preview_data["edit_count"] = preview_data.get("edit_count", 0) + 1
        pricing_relevant = {
            "aws_pricing", "scope_of_work", "architecture_diagram",
            "architecture_integrations", "assumptions", "timelines_and_deliverables",
        }
        final_state = preview_data.get("final_state") or {}
        pricing_result = final_state.get("pricing_result")
        if pricing_result and pricing_relevant.intersection(changed_sections):
            pricing_result = dict(pricing_result)
            pricing_result["stale"] = True
            pricing_result["status_before_edit"] = pricing_result.get("status")
            pricing_result["status"] = "stale"
            final_state["pricing_result"] = pricing_result
            preview_data["final_state"] = final_state
            merged_content["aws_pricing"] = render_aws_pricing_section(pricing_result)
            preview_data["content"] = merged_content

        response_data = {
            "success": True,
            "preview_id": preview_id,
            "status": preview_data.get("status"),
            "progress": preview_data.get("progress", 100),
            "current_step": "Reviewer Markdown edits saved",
            "mode": preview_data.get("mode"),
            "metadata": preview_data.get("metadata", {}),
            "content": merged_content,
            "edited_sections": changed_sections,
            "edit_count": preview_data["edit_count"],
            "pricing_result": pricing_result,
            "message": "Markdown content updated successfully",
        }

    return jsonify(response_data), 200


@app.route('/api/sections/poc', methods=['GET'])
def get_poc_sections():
    """
    API: Get all available sections for POC mode - simplified
    """
    try:
        print(f"\n[API] GET /api/sections/poc - Getting POC sections")
        
        template = config.POC_TEMPLATE_FILE.read_text(encoding='utf-8')
        extracted = extract_sections_from_template(template, 'POC')
        sections = [{"key": item["key"], "name": item["name"]} for item in extracted]
        
        return jsonify({
            "success": True,
            "mode": "POC",
            "sections": sections,
            "total_sections": len(sections)
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/sections/prod', methods=['GET'])
def get_prod_sections():
    """
    API: Get all available sections for PROD mode - simplified
    """
    try:
        print(f"\n[API] GET /api/sections/prod - Getting PROD sections")
        
        template = config.PRODUCTION_TEMPLATE_FILE.read_text(encoding='utf-8')
        extracted = extract_sections_from_template(template, 'PROD')
        sections = [{"key": item["key"], "name": item["name"]} for item in extracted]
        
        return jsonify({
            "success": True,
            "mode": "PROD",
            "sections": sections,
            "total_sections": len(sections)
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/previews/active', methods=['GET'])
def get_active_previews():
    """
    API: Get list of all active in-memory previews for a project
    Query params:
      - project_id: Filter by project ID (optional)
      - account_id: Filter by account ID (optional)
    """
    try:
        project_id = request.args.get('project_id')
        account_id = request.args.get('account_id')

        print(f"\n[API] GET /api/previews/active - project_id={project_id}, account_id={account_id}")

        with preview_lock:
            active_previews = []

            for preview_id, preview_data in preview_storage.items():
                status = preview_data.get("status", "initializing")
                metadata = preview_data.get("metadata", {})
                if not item_is_visible(metadata, current_identity(), request.args.get("business_unit")):
                    continue

                # Filter by project_id if provided
                if project_id and metadata.get("project_id") != project_id:
                    continue

                # Filter by account_id if provided
                if account_id and metadata.get("account_id") != account_id:
                    continue

                # Only include non-finalized previews (drafts)
                if status != "finalized":
                    preview_info = {
                        "preview_id": preview_id,
                        "status": status,
                        "progress": preview_data.get("progress", 0),
                        "current_step": preview_data.get("current_step", ""),
                        "mode": preview_data.get("mode", "POC"),
                        "metadata": {
                            "company_name": metadata.get("company_name", "Unknown"),
                            "project_title": metadata.get("project_title", "Unknown"),
                            "author_name": metadata.get("author_name", "Unknown"),
                            "project_id": metadata.get("project_id"),
                            "account_id": metadata.get("account_id"),
                            "business_unit": metadata.get("business_unit"),
                        },
                        "created_at": preview_data.get("created_at", datetime.now().isoformat()),
                    }
                    active_previews.append(preview_info)

            # Sort by created_at (newest first)
            active_previews.sort(key=lambda x: x.get("created_at", ""), reverse=True)

            print(f"[API] Found {len(active_previews)} active previews")

            return jsonify({
                "success": True,
                "previews": active_previews,
                "count": len(active_previews)
            }), 200

    except Exception as e:
        print(f"[API] Error fetching active previews: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "previews": [],
            "count": 0
        }), 500


@app.route('/api/preview/storage/stats', methods=['GET'])
def get_preview_storage_stats():
    """
    API: Get preview storage statistics and health - UPDATED for finalize-only cleanup
    """
    try:
        denied = _require_admin_response()
        if denied:
            return denied
        from app.preview.preview_config import PreviewConfig
        from app.preview.preview_handler import get_preview_stats

        stats = get_preview_stats()  # Use enhanced stats with age info
        
        # Add health indicators
        health_status = "healthy"
        warnings = []
        
        if stats["memory_usage_percent"] > PreviewConfig.MEMORY_WARNING_THRESHOLD:
            health_status = "warning"
            warnings.append(f"High memory usage: {stats['memory_usage_percent']}%")
        
        if stats["total_previews"] > stats["max_previews"] * PreviewConfig.PREVIEW_COUNT_WARNING_THRESHOLD:
            health_status = "warning"
            warnings.append(f"High preview count: {stats['total_previews']}/{stats['max_previews']}")
        
        # Emergency thresholds (150% of limits)
        emergency_preview_threshold = stats["max_previews"] * 1.5
        emergency_memory_threshold = stats["max_memory_mb"] * 1.5
        
        if stats["memory_usage_mb"] > emergency_memory_threshold or stats["total_previews"] > emergency_preview_threshold:
            health_status = "critical"
            warnings.append("Emergency cleanup thresholds exceeded")
        
        return jsonify({
            "success": True,
            "storage_stats": stats,
            "health_status": health_status,
            "warnings": warnings,
            "cleanup_policy": {
                "type": "finalize_only_strict",
                "description": "Previews persist indefinitely until finalized (no automatic cleanup of any kind)",
                "emergency_cleanup": "disabled",
                "oldest_preview_hours": stats.get("oldest_preview_hours", 0)
            },
            "configuration": PreviewConfig.get_config_summary()
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/edit', methods=['POST'])
def edit_preview():
    """
    API 2: Smart content editing based on user input
    Analyzes which sections need changes and regenerates only those sections
    """
    try:
        print("\n[API] POST /api/edit - Enhanced section-based editing...")
        
        # Handle potential JSON parsing issues
        try:
            data = request.get_json()
        except Exception as json_error:
            print(f"   ❌ JSON parsing error: {json_error}")
            # Try to get raw data and clean it
            try:
                raw_data = request.get_data(as_text=True)
                print(f"   📄 Raw request data length: {len(raw_data)} chars")
                print(f"   📄 First 200 chars: {raw_data[:200]}")
                
                # Try to clean and parse manually
                import json
                cleaned_data = raw_data.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                data = json.loads(cleaned_data)
                print(f"   ✅ Successfully parsed cleaned JSON")
            except Exception as cleanup_error:
                print(f"   ❌ Failed to clean and parse JSON: {cleanup_error}")
                return jsonify({
                    "success": False,
                    "error": f"Invalid JSON format: {str(json_error)}. Please check for special characters in your input."
                }), 400
        
        if not data:
            return jsonify({
                "success": False,
                "error": "Request body must be JSON"
            }), 400
        
        preview_id = data.get('preview_id')
        user_input = data.get('user_input', '').strip()
        selected_sections = data.get('selected_sections', [])  # User-selected sections
        full_replace = data.get('full_replace', False)  # NEW: Explicit full replacement flag
        
        print(f"   📋 Request data:")
        print(f"      preview_id: {preview_id}")
        print(f"      user_input: {user_input[:100]}...")
        print(f"      selected_sections: {selected_sections}")
        print(f"      full_replace: {full_replace}")
        
        if full_replace:
            print(f"   🚀 FULL REPLACE MODE: User text will be used directly without LLM processing")
        
        if not preview_id:
            return jsonify({
                "success": False,
                "error": "preview_id is required"
            }), 400
        
        if not user_input:
            return jsonify({
                "success": False,
                "error": "user_input is required (describe what changes you want)"
            }), 400
        
        if not selected_sections:
            return jsonify({
                "success": False,
                "error": "selected_sections is required (array of section keys to edit)"
            }), 400
        
        # Retrieve preview data
        print(f"   🔍 Retrieving preview data for: {preview_id}")
        with preview_lock:
            preview_data = copy.deepcopy(preview_storage.get(preview_id))
        expected_edit_count = (preview_data or {}).get('edit_count', 0)
        
        if not preview_data:
            print(f"   ❌ Preview not found: {preview_id}")
            return jsonify({
                "success": False,
                "error": f"Preview not found: {preview_id}. It may have expired."
            }), 404

        denied = _preview_denied(preview_data)
        if denied:
            return denied
        
        print(f"   ✅ Preview data retrieved successfully")
        print(f"      Status: {preview_data.get('status', 'unknown')}")
        print(f"      Content sections: {len(preview_data.get('content', {}))}")
        
        poc_content = preview_data.get("content", {})
        mode = preview_data.get("mode", "POC")
        
        if not poc_content:
            print(f"   ❌ No content found in preview")
            return jsonify({
                "success": False,
                "error": "No content found in preview. Preview may not be ready."
            }), 400
        
        # Validate selected sections exist
        missing_sections = [s for s in selected_sections if s not in poc_content]
        if missing_sections:
            print(f"   ❌ Missing sections: {missing_sections}")
            available_sections = list(poc_content.keys())
            return jsonify({
                "success": False,
                "error": f"Sections not found: {missing_sections}. Available sections: {available_sections[:10]}"
            }), 400
        
        print(f"   ✅ All selected sections exist in content")
        
        # Use enhanced smart editor
        print(f"   🤖 Initializing SmartContentEditor...")
        try:
            editor = SmartContentEditor()
            print(f"   ✅ SmartContentEditor initialized successfully")
        except Exception as e:
            print(f"   ❌ Failed to initialize SmartContentEditor: {e}")
            return jsonify({
                "success": False,
                "error": f"Failed to initialize content editor: {str(e)}"
            }), 500
        
        # Step 1: Apply edits to user-selected sections
        print(f"   📝 Applying edits to selected sections...")
        try:
            from app.core.nodes import bind_token_usage, unbind_token_usage
            usage_token = bind_token_usage(preview_id)
            try:
                edit_result = editor.apply_section_edits(
                    poc_content, selected_sections, user_input, mode, full_replace=full_replace
                )
            finally:
                unbind_token_usage(usage_token)
            print(f"   ✅ Section edits applied successfully")
        except Exception as e:
            print(f"   ❌ Failed to apply section edits: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "success": False,
                "error": f"Failed to apply edits: {str(e)}"
            }), 500
        
        print(f"   🔍 Edit results:")
        print(f"      Edited sections: {edit_result.get('edited_sections', [])}")
        print(f"      Auto-updated sections: {edit_result.get('auto_updated_sections', [])}")
        
        updated_content = edit_result.get('updated_content', poc_content)
        
        # Validate updated content
        if not updated_content:
            print(f"   ❌ No updated content returned from editor")
            return jsonify({
                "success": False,
                "error": "No updated content returned from editor"
            }), 500
        
        # Debug: Verify what we're about to store
        print(f"\n🔍 DEBUG: About to update preview with...")
        print(f"   Total sections: {len(updated_content)}")
        edited_sections = edit_result.get('edited_sections', [])
        for section in edited_sections:
            if section in updated_content:
                content_preview = str(updated_content[section])[:100]
                print(f"   {section}: {content_preview}...")
        
        # Step 2: Update preview data in memory
        print(f"   💾 Updating preview data in storage...")
        try:
            update_success = update_preview_data(preview_id, updated_content, expected_edit_count=expected_edit_count)
            
            if not update_success:
                print(f"   ❌ Failed to update preview data in storage")
                return jsonify({
                    "success": False,
                    "error": "The preview changed while editing. Reload it and retry your edit."
                }), 409
            
            print(f"   ✅ Preview data updated in storage")
            from app.core.nodes import get_token_usage
            token_usage = get_token_usage(preview_id)
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["token_usage"] = token_usage
                    preview_storage[preview_id]["total_tokens"] = int(token_usage.get("total_tokens") or 0)
        except Exception as e:
            print(f"   ❌ Exception during preview update: {e}")
            return jsonify({
                "success": False,
                "error": f"Failed to update preview: {str(e)}"
            }), 500
        
        # Step 3: Verify the update was successful
        print(f"   🔍 Verifying update was successful...")
        try:
            verification_data = get_preview_data(preview_id)
            if verification_data:
                stored_content = verification_data.get("content", {})
                if len(stored_content) != len(updated_content):
                    print(f"   ⚠️  Verification failed: section count mismatch")
                    print(f"      Expected: {len(updated_content)}, Stored: {len(stored_content)}")
                else:
                    print(f"   ✅ Verification passed: {len(stored_content)} sections stored")
            else:
                print(f"   ⚠️  Could not retrieve data for verification")
        except Exception as e:
            print(f"   ⚠️  Verification error: {e}")
        
        print(f"   ✅ Edit operation completed successfully")
        
        # Include metadata from preview_data so frontend can display document information
        metadata = preview_data.get("metadata", {})
        
        # ✅ ENHANCED: Ensure all metadata fields have values (no N/A)
        # Get the latest preview data to ensure we have the most current metadata
        latest_preview = get_preview_data(preview_id)
        if latest_preview:
            metadata = latest_preview.get("metadata", metadata)
        
        # Ensure all required metadata fields exist with proper defaults
        metadata_response = {
            "company_name": metadata.get("company_name", "Unknown Company"),
            "project_title": metadata.get("project_title", "Unknown Project"),
            "author_name": metadata.get("author_name", "Unknown Author"),
            "author_org": metadata.get("author_org", "Shellkode"),
            "document_date": metadata.get("document_date", datetime.now().strftime("%d %B %Y")),
            "start_date": metadata.get("start_date") or "",
            "end_date": metadata.get("end_date") or "",
            "version": metadata.get("version", "1.0"),
            "timezone": metadata.get("timezone", "IST"),
            "author_org_description": metadata.get("author_org_description", "Shellkode specializes in developing advanced data and AI solutions for businesses.")
        }
        
        print(f"   📋 Returning metadata:")
        print(f"      Company: {metadata_response['company_name']}")
        print(f"      Project: {metadata_response['project_title']}")
        print(f"      Author: {metadata_response['author_name']}")
        
        return jsonify({
            "success": True,
            "preview_id": preview_id,
            "edited_sections": edit_result.get('edited_sections', []),
            "auto_updated_sections": edit_result.get('auto_updated_sections', []),
            "dependency_changes": edit_result.get('dependency_changes', {}),
            "updated_content": updated_content,
            "edit_count": preview_data.get("edit_count", 0) + 1,
            "full_replace_used": full_replace,
            "message": "Content updated successfully. Use /api/finalize to create document.",
            # ✅ ENHANCED: Include complete metadata with proper defaults
            "mode": mode,
            "metadata": metadata_response,
            "company_name": metadata_response["company_name"],
            "project_title": metadata_response["project_title"],
            "author_name": metadata_response["author_name"],
            "author_org": metadata_response["author_org"],
            "document_date": metadata_response["document_date"],
            "start_date": metadata_response["start_date"],
            "end_date": metadata_response["end_date"],
            "version": metadata_response["version"],
            "timezone": metadata_response["timezone"],
            "author_org_description": metadata_response["author_org_description"]
        }), 200
        
    except Exception as e:
        print(f"\n❌ EDIT API ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }), 500


@app.route('/api/finalize', methods=['POST'])
def finalize_document():
    """
    API 3: Create final document from preview and save to DB/S3/Drive
    Uses the same task ID as preview_id for tracking
    ✅ IDEMPOTENT: Returns cached result if already finalized
    """
    try:
        print("\n[API] POST /api/finalize - Creating final document...")
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "Request body must be JSON"
            }), 400
        
        preview_id = data.get('preview_id')
        
        if not preview_id:
            return jsonify({
                "success": False,
                "error": "preview_id is required"
            }), 400
        
        # ✅ IDEMPOTENCY CHECK: If task already exists and is completed, return cached result
        task_id = preview_id
        with preview_lock:
            has_preview = preview_id in preview_storage
        if not has_preview:
            saved = DynamoDBHandler().query_by_task_id(preview_id)
            if saved:
                denied = _resource_denied(saved)
                if denied:
                    return denied
                if str(saved.get("status") or "").lower() == "draft":
                    return jsonify({
                        "success": False, "code": "PREVIEW_SAVED_AS_DRAFT",
                        "document_id": saved.get("document_id"),
                        "error": "This preview was saved as a draft. Open it from SOW Records to continue.",
                    }), 200
                return jsonify({
                    "success": True, "cached": True,
                    "document_id": saved.get("document_id"),
                    "s3_url": saved.get("s3_url"), "drive_link": saved.get("drive_link"),
                    "result": saved,
                }), 200
        existing_task = get_task(task_id)
        if existing_task:
            denied = _resource_denied(existing_task.get("metadata"))
            if denied:
                return denied
        
        if existing_task and existing_task.get('status') == TaskStatus.COMPLETED:
            print(f"   ⚡ Task already completed, returning cached result")
            result = existing_task.get('result', {})
            if result.get("is_draft"):
                return jsonify({
                    "success": False,
                    "code": "PREVIEW_SAVED_AS_DRAFT",
                    "document_id": result.get("document_id"),
                    "error": "This preview was automatically saved as a draft after the review session disconnected.",
                }), 200
            return jsonify({
                "success": True,
                "task_id": task_id,
                "document_id": result.get("document_id"),
                "s3_url": result.get("s3_url"),
                "drive_link": result.get("drive_link"),
                "message": "Document already created (cached result)",
                "result": result,
                "cached": True
            }), 200
        
        # ✅ IDEMPOTENCY CHECK: If task is processing, return processing status
        if existing_task and existing_task.get('status') == TaskStatus.PROCESSING:
            print(f"   ⏳ Task already processing, returning status")
            return jsonify({
                "success": True,
                "task_id": task_id,
                "status": "processing",
                "progress": existing_task.get('progress', 0),
                "current_step": existing_task.get('current_step', 'Processing...'),
                "message": "Document is being created",
                "processing": True
            }), 202
        
        # Retrieve preview data
        preview_data = get_preview_data(preview_id)
        
        if not preview_data:
            # ✅ FALLBACK: If preview not found but task exists, return task result
            if existing_task and existing_task.get('status') == TaskStatus.COMPLETED and existing_task.get('result', {}).get('s3_url'):
                print(f"   ⚠️  Preview expired but task exists, returning task result")
                result = existing_task.get('result', {})
                return jsonify({
                    "success": True,
                    "task_id": task_id,
                    "document_id": result.get("document_id"),
                    "s3_url": result.get("s3_url"),
                    "drive_link": result.get("drive_link"),
                    "message": "Preview expired but document was created",
                    "result": result,
                    "cached": True
                }), 200
            
            return jsonify({
                "success": False,
                "error": f"Preview not found: {preview_id}. It may have expired."
            }), 404

        denied = _preview_denied(preview_data)
        if denied:
            return denied
        
        mode = preview_data.get("mode")
        metadata = preview_data.get("metadata")
        content = preview_data.get("content")

        architecture_assets = (content or {}).get('architecture_diagram_assets') or []
        if any(isinstance(asset, dict) and asset.get('status') == 'unavailable' for asset in architecture_assets):
            return jsonify(success=False, code='ARCHITECTURE_REGENERATION_REQUIRED',
                           error='The architecture diagram did not pass validation. Regenerate it before finalizing; you can still save this preview as a draft.'), 409
        pricing_result = (preview_data.get("final_state") or {}).get("pricing_result") or {}
        if pricing_result.get("status") == "stale":
            return jsonify({
                "success": False,
                "error": "AWS pricing is stale after content edits. Recalculate pricing before finalizing.",
                "code": "AWS_PRICING_STALE",
            }), 409

        # Claim the preview only after all non-mutating preflight checks. This
        # prevents the abandonment monitor from saving the same content while
        # finalisation is running, without wedging a preview on validation errors.
        with preview_lock:
            live_preview = preview_storage.get(preview_id)
            if not live_preview:
                return jsonify({"success": False, "error": "Preview is no longer available"}), 404
            if live_preview.get("status") == "draft_saving":
                return jsonify({"success": False, "error": "Draft save is already in progress"}), 409
            if live_preview.get("status") != "ready":
                return jsonify({"success": False, "error": "Preview is not ready to finalize"}), 409
            live_preview["status"] = "document_finalizing"

        from app.core.nodes import get_token_usage
        live_token_usage = get_token_usage(preview_id)
        stored_token_usage = preview_data.get("token_usage") or {}
        token_usage = (
            live_token_usage
            if int(live_token_usage.get("total_tokens") or 0) >= int(stored_token_usage.get("total_tokens") or 0)
            else stored_token_usage
        )
        total_tokens = int(token_usage.get("total_tokens") or 0)
        
        print(f"   📄 Finalizing {mode} document from preview: {preview_id}")
        
        # Use preview_id as task_id for consistency
        task_id = preview_id
        
        # Create task for tracking (only if not exists)
        if not existing_task:
            task = create_task(task_id, mode, {
                "company_name": metadata.get("company_name"),
                "project_name": metadata.get("project_title"),
                "author_name": metadata.get("author_name"),
                "business_unit": metadata.get("business_unit"),
                "owner_email": metadata.get("owner_email"),
                "owner_name": metadata.get("owner_name"),
            })
        
        update_task(task_id, status=TaskStatus.PROCESSING, progress=10, current_step="Building document")
        
        # Reconstruct final_state for document building with all required fields
        final_state = {
            "metadata": metadata,
            "mode": mode,
            "poc_content": content,  # Pass the original poc_content structure
            "validated_requirements": {},  # Empty dict for preview workflow
            "analyzed_requirements": {},  # Empty dict for preview workflow
            "source_file": None,
            "output_path": None,
            "json_path": None,
            "errors": [],
            "current_step": "build"
        }
        
        # Import document builder
        from app.core.nodes import pdf_build_node
        
        # Build document
        print(f"   🔨 Building document...")
        final_state = pdf_build_node(final_state)
        
        if final_state.get("errors"):
            raise Exception(f"Document build failed: {final_state['errors']}")
        
        update_task(task_id, progress=50, current_step="Document built, uploading to cloud")
        
        # Get the output file path directly from final_state (no local copying)
        upload_file = final_state.get('output_path')
        
        if not upload_file or not Path(upload_file).exists():
            raise Exception("Document generation failed - no output file produced")
        
        update_task(task_id, progress=60, current_step="Uploading to cloud storage")
        
        # Cloud uploads
        print(f"   ☁️  Uploading to cloud...")
        drive_result = None
        s3_result = None
        
        try:
            drive_folder = FOLDER_MAPPING.get(mode, "default")
            drive_result = upload_generated_document(upload_file, folder_name=drive_folder)
            if drive_result:
                print("   ✅ Google Drive upload successful")
        except Exception as e:
            print(f"   ⚠️  Google Drive upload failed: {e}")
        
        try:
            s3_folder = FOLDER_MAPPING.get(mode, mode)
            s3_result = upload_to_s3(upload_file, mode=s3_folder)
            if s3_result:
                print("   ✅ S3 upload successful")
        except Exception as e:
            print(f"   ⚠️  S3 upload failed: {e}")
        
        update_task(task_id, progress=80, current_step="Saving to DynamoDB")
        
        # Save to DynamoDB
        db_result = None
        if s3_result:
            s3_url = s3_result.get('https_url') or s3_result.get('s3_url') or s3_result.get('url')
            if s3_url:
                drive_link = None
                if drive_result and isinstance(drive_result, dict):
                    drive_link = drive_result.get('link') or drive_result.get('url')
                
                # ✅ Extract account_id and project_id from preview metadata
                account_id = preview_data.get("metadata", {}).get("account_id")
                project_id = preview_data.get("metadata", {}).get("project_id")
                
                print(f"   🔍 Extracted from preview metadata:")
                print(f"      account_id: {account_id}")
                print(f"      project_id: {project_id}")
                
                db_result = save_to_dynamodb(
                    metadata={
                        "company_name": metadata["company_name"],
                        "author_name": metadata["author_name"],
                        "project_name": metadata["project_title"],
                        "document_date": metadata["document_date"],
                        "mode": mode,
                        "business_unit": metadata.get("business_unit"),
                        "owner_email": metadata.get("owner_email"),
                        "owner_name": metadata.get("owner_name"),
                        "total_tokens": total_tokens,
                        "token_usage": token_usage,
                        "aws_pricing": _pricing_audit_record(
                            (preview_data.get("final_state") or {}).get("pricing_result")
                        ),
                        "source_documents": metadata.get("source_documents", []),
                        "source_scope_id": metadata.get("source_scope_id"),
                        "parent_document_id": metadata.get("parent_document_id"),
                        "refinement_instructions": metadata.get("refinement_instructions"),
                        "selected_sow_sections": metadata.get("selected_sow_sections", []),
                        "timeline_format": metadata.get("timeline_format", "table"),
                        "status": "completed",
                        **_semantic_index_metadata(content, metadata),
                    },
                    s3_url=s3_url,
                    s3_result=s3_result,
                    drive_link=drive_link,
                    table_name=os.getenv('DYNAMODB_TABLE_POC_DOCUMENTS', 'agentic-poc'),
                    region=os.getenv('AWS_REGION', 'us-east-1'),
                    task_id=task_id,
                    account_id=account_id,  # ✅ NEW: Pass account_id
                    project_id=project_id,
                    existing_document_id=metadata.get("draft_document_id"),
                )
                
                # ✅ NEW: Link SOW to project if project_id exists in preview metadata
                if project_id and db_result:
                    try:
                        sow_id = db_result.get("document_id")
                        if sow_id:
                            sow_data = {
                                'mode': mode,
                                'status': 'completed',
                                'customer_name': metadata["company_name"],
                                'project_name': metadata["project_title"],
                                'author_name': metadata["author_name"],
                                'drive_link': drive_link,
                                's3_url': s3_url,
                                'sow_db_id': sow_id,
                                'document_date': metadata.get("document_date"),
                                'created_at': datetime.now().isoformat(),
                                'business_unit': metadata.get("business_unit"),
                                'owner_email': metadata.get("owner_email"),
                                'owner_name': metadata.get("owner_name"),
                                'total_tokens': total_tokens,
                                'token_usage': token_usage,
                                'aws_pricing': _pricing_audit_record(
                                    (preview_data.get("final_state") or {}).get("pricing_result")
                                ),
                                'source_documents': metadata.get("source_documents", []),
                                'source_scope_id': metadata.get("source_scope_id"),
                                'parent_document_id': metadata.get("parent_document_id"),
                                'selected_sow_sections': metadata.get("selected_sow_sections", []),
                            }
                            account_handler.link_sow_to_project(project_id, sow_id, sow_data)
                            print(f"   ✅ Linked SOW {sow_id} to project {project_id}")
                    except Exception as link_error:
                        print(f"   ⚠️  Failed to link SOW to project: {link_error}")
                        # Don't fail the entire operation if linking fails
        
        if not s3_result or not db_result or not db_result.get("success") or not db_result.get("document_id"):
            raise RuntimeError("Final document was not persisted; the preview remains available for retry")
        if metadata.get("draft_document_id"):
            _cleanup_replaced_draft_artifacts({
                "s3_url": metadata.get("draft_original_s3_url"),
                "draft_preview_s3_url": metadata.get("draft_preview_s3_url"),
            }, s3_url)

        
        # No local file saving - skip save_document_info
        print(f"   ✅ Skipping local file saving - cloud-only mode")
        
        # ✅ AUTO-CLEANUP: Delete temporary files after successful cloud upload
        if s3_result and upload_file:
            try:
                if os.path.exists(upload_file):
                    os.remove(upload_file)
                    print(f"   ✅ Cleaned up temporary file: {Path(upload_file).name}")
                
                # Also clean up JSON file if it exists
                json_file = str(upload_file).replace('.docx', '_data.json').replace('.pdf', '_data.json')
                if os.path.exists(json_file):
                    os.remove(json_file)
                    print(f"   ✅ Cleaned up JSON file: {Path(json_file).name}")
            except Exception as e:
                print(f"   ⚠️  Could not clean up temporary files: {e}")
        
        # A reopened draft is replaced only after the finalized record is
        # safely persisted. On any earlier failure the original draft remains.
        old_draft_id = str(metadata.get("draft_document_id") or "").strip()
        new_document_id = db_result.get("document_id") if db_result else None
        if old_draft_id and new_document_id and old_draft_id != new_document_id:
            old_record = DynamoDBHandler().get_document_by_id(old_draft_id)
            if old_record and str(old_record.get("status") or "").lower() == "draft":
                _delete_draft_record(old_record)

        # Delete preview from memory
        delete_preview_data(preview_id)
        from app.core.nodes import clear_token_usage
        clear_token_usage(preview_id)
        
        # Complete task
        result_data = {
            "pdf_path": None,  # No local files saved
            "docx_path": None,  # No local files saved
            "filename": Path(upload_file).name if upload_file else None,
            "mode": mode,
            "s3_url": s3_result.get('https_url') if s3_result else None,
            "drive_link": drive_result.get('link') if drive_result else None,
            "document_id": db_result.get("document_id") if db_result else None,
            "total_tokens": total_tokens,
            "token_usage": token_usage,
            "version": db_result.get("version"),
            "project_name": metadata.get("project_title"),
            "timestamp": db_result.get("timestamp"),
        }
        
        update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            current_step="Completed",
            completed_at=datetime.now().isoformat(),
            result=result_data
        )
        
        print(f"   ✅ Document finalized successfully")
        print(f"   Total token usage: {total_tokens:,}", flush=True)
        
        return jsonify({
            "success": True,
            "task_id": task_id,
            "document_id": db_result.get("document_id") if db_result else None,
            "s3_url": s3_result.get('https_url') if s3_result else None,
            "drive_link": drive_result.get('link') if drive_result else None,
            "total_tokens": total_tokens,
            "token_usage": token_usage,
            "message": "Document created and saved successfully",
            "result": result_data
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()

        with preview_lock:
            if 'preview_id' in locals() and preview_id in preview_storage:
                if preview_storage[preview_id].get("status") == "document_finalizing":
                    preview_storage[preview_id]["status"] = "ready"
                    preview_storage[preview_id]["current_step"] = "Preview ready; finalization can be retried"
                    preview_storage[preview_id]["last_activity_at"] = time.time()
        
        # Update task as failed
        if 'task_id' in locals():
            update_task(
                task_id,
                status=TaskStatus.FAILED,
                progress=0,
                current_step="Failed",
                completed_at=datetime.now().isoformat(),
                error=str(e)
            )
        
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/test', methods=['GET', 'POST'])
def test_endpoint():
    """Simple test endpoint to verify server responsiveness"""
    import time
    start_time = time.time()
    
    response_data = {
        "success": True,
        "message": "Server is responding normally",
        "timestamp": datetime.now().isoformat(),
        "method": request.method,
        "response_time_ms": round((time.time() - start_time) * 1000, 2)
    }
    
    response = jsonify(response_data)
    response.headers['Connection'] = 'close'
    response.headers['Cache-Control'] = 'no-cache'
    
    return response

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for load balancers/monitoring"""
    try:
        # Check DynamoDB connection
        handler = DynamoDBHandler()

        # Check S3 connection
        s3_client = get_s3_client()

        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "dynamodb": "connected",
                "s3": "connected" if s3_client else "disconnected"
            },
            "tasks": {
                "active": len(tasks),
                "memory_usage": "in-memory"
            }
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


@app.errorhandler(404)
def not_found(error):
    """404 handler"""
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """500 handler"""
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500


@app.errorhandler(413)
def file_too_large(error):
    """413 handler for file size exceeded"""
    return jsonify({
        "success": False,
        "error": "File size exceeds 10MB limit"
    }), 413


# ============================================================================
# ACCOUNT & PROJECT MANAGEMENT APIs
# ============================================================================

# Initialize account handler
account_handler = AccountHandler()

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts with optional filters"""
    try:
        segment = request.args.get('segment')
        priority = request.args.get('priority')
        limit = int(request.args.get('limit', 100))

        accounts = account_handler.list_accounts(
            segment=segment,
            priority=priority,
            limit=limit
        )
        accounts = filter_visible_items(
            accounts, current_identity(), request.args.get('business_unit')
        )

        return jsonify({
            "success": True,
            "accounts": accounts,
            "count": len(accounts)
        })
    except Exception as e:
        print(f"❌ Error getting accounts: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/accounts/statistics', methods=['GET'])
def get_account_statistics():
    """Get account statistics for dashboard"""
    try:
        accounts = filter_visible_items(
            account_handler.list_accounts(limit=1000),
            current_identity(),
            request.args.get('business_unit'),
        )
        stats = {
            'total': len(accounts),
            'with_projects': sum(1 for account in accounts if account.get('project_count', 0) > 0),
            'without_projects': sum(1 for account in accounts if account.get('project_count', 0) <= 0),
            'by_segment': {},
            'by_priority': {},
        }
        for account in accounts:
            segment = account.get('segment', 'Others')
            priority = account.get('priority', 'P3')
            stats['by_segment'][segment] = stats['by_segment'].get(segment, 0) + 1
            stats['by_priority'][priority] = stats['by_priority'].get(priority, 0) + 1
        return jsonify({
            "success": True,
            "statistics": stats
        })
    except Exception as e:
        print(f"❌ Error getting statistics: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/accounts/<account_id>', methods=['GET'])
def get_account(account_id):
    """Get account by ID"""
    try:
        account = account_handler.get_account(account_id)
        if not account:
            return jsonify({
                "success": False,
                "error": "Account not found"
            }), 404
        denied = _resource_denied(account)
        if denied:
            return denied

        return jsonify({
            "success": True,
            "account": account
        })
    except Exception as e:
        print(f"❌ Error getting account: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/accounts', methods=['POST'])
def create_account():
    """Create a new account"""
    try:
        data = request.json
        business_unit, denied = _business_unit_for_new_record()
        if denied:
            return denied
        account_name = data.get('account_name')

        if not account_name:
            return jsonify({
                "success": False,
                "error": "account_name is required"
            }), 400

        segment = data.get('segment', 'Others')
        priority = data.get('priority', 'P3')
        metadata = {
            **data.get('metadata', {}),
            **_ownership_metadata(business_unit),
        }

        account = account_handler.create_account(
            account_name=account_name,
            segment=segment,
            priority=priority,
            metadata=metadata
        )

        return jsonify({
            "success": True,
            "account": account,
            "message": f"Account '{account_name}' created successfully"
        }), 201
    except Exception as e:
        print(f"❌ Error creating account: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/accounts/<account_id>', methods=['PUT'])
def update_account(account_id):
    """Update an account"""
    try:
        existing = account_handler.get_account(account_id)
        denied = _resource_denied(existing)
        if denied:
            return denied
        data = request.json
        updates = data.get('updates', {})
        updates.pop('business_unit', None)

        account = account_handler.update_account(account_id, updates)
        if not account:
            return jsonify({
                "success": False,
                "error": "Account not found or update failed"
            }), 404

        return jsonify({
            "success": True,
            "account": account,
            "message": "Account updated successfully"
        })
    except Exception as e:
        print(f"❌ Error updating account: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/accounts/<account_id>', methods=['DELETE'])
def delete_account(account_id):
    """Delete an account (soft delete)"""
    try:
        existing = account_handler.get_account(account_id)
        denied = _resource_denied(existing)
        if denied:
            return denied
        success = account_handler.delete_account(account_id)
        if not success:
            return jsonify({
                "success": False,
                "error": "Account not found or deletion failed"
            }), 404

        return jsonify({
            "success": True,
            "message": "Account deleted successfully"
        })
    except Exception as e:
        print(f"❌ Error deleting account: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# PROJECT MANAGEMENT APIs
# ============================================================================

@app.route('/api/accounts/<account_id>/projects', methods=['GET'])
def get_projects_for_account(account_id):
    """Get all projects for an account"""
    try:
        limit = int(request.args.get('limit', 100))

        account = account_handler.get_account(account_id)
        denied = _resource_denied(account)
        if denied:
            return denied
        projects = filter_visible_items(
            account_handler.list_projects_for_account(account_id, limit=limit),
            current_identity(), request.args.get('business_unit')
        )

        return jsonify({
            "success": True,
            "projects": projects,
            "count": len(projects),
            "account_id": account_id
        })
    except Exception as e:
        print(f"❌ Error getting projects: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/projects/<project_id>', methods=['GET'])
def get_project(project_id):
    """Get project by ID"""
    try:
        project = account_handler.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": "Project not found"
            }), 404
        denied = _resource_denied(project)
        if denied:
            return denied

        return jsonify({
            "success": True,
            "project": project
        })
    except Exception as e:
        print(f"❌ Error getting project: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/accounts/<account_id>/projects', methods=['POST'])
def create_project(account_id):
    """Create a new project within an account"""
    try:
        account = account_handler.get_account(account_id)
        denied = _resource_denied(account)
        if denied:
            return denied
        data = request.json
        project_name = data.get('project_name')

        if not project_name:
            return jsonify({
                "success": False,
                "error": "project_name is required"
            }), 400

        description = data.get('description', '')
        metadata = {
            **data.get('metadata', {}),
            **_ownership_metadata(account.get('business_unit')),
        }

        project = account_handler.create_project(
            account_id=account_id,
            project_name=project_name,
            description=description,
            metadata=metadata
        )

        return jsonify({
            "success": True,
            "project": project,
            "message": f"Project '{project_name}' created successfully"
        }), 201
    except Exception as e:
        print(f"❌ Error creating project: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/projects/<project_id>', methods=['PUT'])
def update_project(project_id):
    """Update a project"""
    try:
        existing = account_handler.get_project(project_id)
        denied = _resource_denied(existing)
        if denied:
            return denied
        data = request.json
        updates = data.get('updates', {})
        updates.pop('business_unit', None)

        project = account_handler.update_project(project_id, updates)
        if not project:
            return jsonify({
                "success": False,
                "error": "Project not found or update failed"
            }), 404

        return jsonify({
            "success": True,
            "project": project,
            "message": "Project updated successfully"
        })
    except Exception as e:
        print(f"❌ Error updating project: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    """Delete a project (soft delete)"""
    try:
        existing = account_handler.get_project(project_id)
        denied = _resource_denied(existing)
        if denied:
            return denied
        success = account_handler.delete_project(project_id)
        if not success:
            return jsonify({
                "success": False,
                "error": "Project not found or deletion failed"
            }), 404

        return jsonify({
            "success": True,
            "message": "Project deleted successfully"
        })
    except Exception as e:
        print(f"❌ Error deleting project: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/debug/projects/<project_id>', methods=['GET'])
def debug_project(project_id):
    """
    🔍 DEBUG ENDPOINT: Detailed project lookup diagnostics
    
    This endpoint helps troubleshoot project lookup issues by:
    1. Checking direct PROJECT# metadata lookup
    2. Scanning entire table for matching project_id
    3. Showing all related entries (PK/SK combinations)
    """
    try:
        denied = _require_admin_response()
        if denied:
            return denied
        from boto3.dynamodb.conditions import Attr
        
        debug_info = {
            "project_id": project_id,
            "timestamp": datetime.now().isoformat(),
            "checks": {}
        }
        
        # Check 1: Direct metadata lookup
        print(f"\n🔍 DEBUG: Looking up project {project_id}")
        print(f"   Check 1: Direct metadata lookup")
        
        try:
            response = account_handler.table.get_item(
                Key={
                    'PK': f'PROJECT#{project_id}',
                    'SK': 'METADATA'
                }
            )
            
            if 'Item' in response:
                debug_info['checks']['direct_lookup'] = {
                    "status": "FOUND",
                    "item": response['Item']
                }
                print(f"   ✅ Found via direct lookup")
            else:
                debug_info['checks']['direct_lookup'] = {
                    "status": "NOT_FOUND",
                    "message": "No item with PK=PROJECT#{project_id}, SK=METADATA"
                }
                print(f"   ❌ Not found via direct lookup")
        except Exception as e:
            debug_info['checks']['direct_lookup'] = {
                "status": "ERROR",
                "error": str(e)
            }
            print(f"   ❌ Error: {e}")
        
        # Check 2: Scan for project_id attribute
        print(f"   Check 2: Scanning for project_id attribute")
        
        try:
            response = account_handler.table.scan(
                FilterExpression=Attr('project_id').eq(project_id),
                Limit=10
            )
            
            items = response.get('Items', [])
            if items:
                debug_info['checks']['scan_lookup'] = {
                    "status": "FOUND",
                    "count": len(items),
                    "items": items
                }
                print(f"   ✅ Found {len(items)} item(s) via scan")
                for idx, item in enumerate(items, 1):
                    print(f"      {idx}. PK={item.get('PK')}, SK={item.get('SK')}, name={item.get('project_name')}")
            else:
                debug_info['checks']['scan_lookup'] = {
                    "status": "NOT_FOUND",
                    "message": "No items with project_id attribute matching"
                }
                print(f"   ❌ Not found via scan")
        except Exception as e:
            debug_info['checks']['scan_lookup'] = {
                "status": "ERROR",
                "error": str(e)
            }
            print(f"   ❌ Error: {e}")
        
        # Check 3: Try to find account and list its projects
        print(f"   Check 3: Attempting to find parent account")
        
        try:
            # If we found the project via scan, get its account_id
            if debug_info['checks'].get('scan_lookup', {}).get('status') == 'FOUND':
                items = debug_info['checks']['scan_lookup']['items']
                if items:
                    account_id = items[0].get('account_id')
                    if account_id:
                        print(f"      Found account_id: {account_id}")
                        projects = account_handler.list_projects_for_account(account_id)
                        debug_info['checks']['account_projects'] = {
                            "status": "FOUND",
                            "account_id": account_id,
                            "project_count": len(projects),
                            "projects": [
                                {
                                    "project_id": p.get('project_id'),
                                    "project_name": p.get('project_name'),
                                    "PK": p.get('PK'),
                                    "SK": p.get('SK')
                                }
                                for p in projects
                            ]
                        }
                        print(f"      ✅ Account has {len(projects)} project(s)")
                    else:
                        debug_info['checks']['account_projects'] = {
                            "status": "NO_ACCOUNT_ID",
                            "message": "Project item has no account_id field"
                        }
                        print(f"      ⚠️  No account_id in project item")
            else:
                debug_info['checks']['account_projects'] = {
                    "status": "SKIPPED",
                    "message": "Project not found via scan, cannot determine account"
                }
                print(f"      ⚠️  Skipped (project not found)")
        except Exception as e:
            debug_info['checks']['account_projects'] = {
                "status": "ERROR",
                "error": str(e)
            }
            print(f"      ❌ Error: {e}")
        
        # Summary
        found_anywhere = any(
            check.get('status') == 'FOUND' 
            for check in debug_info['checks'].values()
        )
        
        debug_info['summary'] = {
            "project_exists": found_anywhere,
            "recommendation": (
                "Project found in database but may have inconsistent entries. Check PK/SK structure."
                if found_anywhere
                else "Project does not exist in database. It may have been deleted or never created."
            )
        }
        
        print(f"\n   Summary: Project {'EXISTS' if found_anywhere else 'NOT FOUND'}")
        
        return jsonify({
            "success": True,
            "debug": debug_info
        })
        
    except Exception as e:
        print(f"❌ Debug endpoint error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============================================================================
# SOW MANAGEMENT APIs (within projects)
# ============================================================================

@app.route('/api/projects/<project_id>/sows', methods=['GET'])
def get_sows_for_project(project_id):
    """
    Get all SOWs for a project
    ✅ ENHANCED: Now queries both agentic-sow-v2 (linked SOWs) and agentic-poc (all documents)
    """
    try:
        limit = int(request.args.get('limit', 100))

        # Get project details to extract company and project names
        project = account_handler.get_project(project_id)
        
        if not project:
            print(f"⚠️  Project {project_id} not found, returning empty list")
            return jsonify({
                "success": True,
                "sows": [],
                "count": 0,
                "project_id": project_id,
                "note": "Project not found"
            })
        denied = _resource_denied(project)
        if denied:
            return denied

        # Get linked SOWs from agentic-sow-v2 table
        linked_sows = account_handler.list_sows_for_project(project_id, limit=limit)
        linked_sows = filter_visible_items(linked_sows, current_identity())
        print(f"✅ Retrieved {len(linked_sows)} linked SOWs from agentic-sow-v2")

        # ✅ NEW: Query agentic-poc table by account_id
        account_id = project.get('account_id')
        
        if not account_id:
            print(f"⚠️  No account_id found for project {project_id}")
            return jsonify({
                "success": True,
                "sows": linked_sows,
                "count": len(linked_sows),
                "project_id": project_id
            })
        
        print(f"🔍 Querying agentic-poc table by account_id: {account_id}")
        
        # Query agentic-poc table by account_id
        handler = DynamoDBHandler()
        all_documents = []
        
        try:
            # Query documents by account_id
            response = handler.table.scan(
                FilterExpression='account_id = :aid',
                ExpressionAttributeValues={
                    ':aid': account_id
                },
                Limit=1000
            )
            
            all_documents = response.get('Items', [])
            
            # Filter by project_id if available
            if project_id:
                filtered_docs = [
                    doc for doc in all_documents 
                    if doc.get('project_id') == project_id
                ]
            all_documents = filtered_docs
            all_documents = filter_visible_items(all_documents, current_identity())
            
            print(f"✅ Retrieved {len(all_documents)} documents from agentic-poc")
        except Exception as e:
            print(f"⚠️  Error querying agentic-poc: {e}")
        
        # Merge linked SOWs and documents from agentic-poc
        # Create a set of linked SOW IDs to avoid duplicates
        linked_sow_ids = {sow.get('sow_id') or sow.get('document_id') for sow in linked_sows}
        
        # Add documents from agentic-poc that aren't already linked
        for doc in all_documents:
            doc_id = doc.get('document_id')
            if doc_id not in linked_sow_ids:
                # Add to results
                linked_sows.append(doc)
        
        # Sort by timestamp (most recent first)
        def safe_timestamp(doc):
            ts = doc.get('timestamp') or doc.get('created_at') or doc.get('linked_at', '')
            if not ts:
                return datetime.min
            try:
                ts_clean = ts.replace('Z', '+00:00')
                return datetime.fromisoformat(ts_clean)
            except:
                return datetime.min
        
        linked_sows.sort(key=safe_timestamp, reverse=True)
        
        # Apply limit
        linked_sows = linked_sows[:limit]
        
        print(f"✅ Retrieved {len(linked_sows)} SOWs for project: {project_id}")

        return jsonify({
            "success": True,
            "sows": linked_sows,
            "count": len(linked_sows),
            "project_id": project_id
        })
    except Exception as e:
        print(f"❌ Error getting SOWs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/projects/<project_id>/sows', methods=['POST'])
def create_sow_for_project(project_id):
    """
    Create a new SOW within a project
    This endpoint wraps the existing /api/generate endpoint and links the SOW to the project
    """
    try:
        # Verify project exists
        project = account_handler.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": "Project not found"
            }), 404
        denied = _resource_denied(project)
        if denied:
            return denied
        business_unit = project.get('business_unit')
        ownership = _ownership_metadata(business_unit)

        # Extract request data with enhanced fallbacks
        data = request.json
        mode = data.get('mode', 'POC')
        
        # Enhanced company name resolution with multiple fallbacks
        customer_name = (
            data.get('customer_name') or 
            project.get('project_name') or 
            'Unknown Company'
        )
        
        author_name = data.get('author_name', 'ShellKode')
        project_name = (
            data.get('project_name') or 
            project.get('project_name') or 
            customer_name
        )
        objective = data.get('objective', '')

        print(f"📋 SOW Creation - Enhanced Data Resolution:")
        print(f"   Project ID: {project_id}")
        print(f"   Mode: {mode}")
        print(f"   Customer Name: {customer_name}")
        print(f"   Project Name: {project_name}")
        print(f"   Author Name: {author_name}")
        print(f"   Objective Length: {len(objective)} chars")

        # Create task ID
        task_id = str(uuid.uuid4())

        # Store project_id in task metadata so we can link it later
        metadata = {
            'customer_name': customer_name,
            'author_name': author_name,
            'project_name': project_name,
            'mode': mode,
            'objective': objective,
            'project_id': project_id,  # Link to project
            'account_id': project.get('account_id'),  # Link to account
            **ownership,
        }

        create_task(task_id, mode, metadata)

        # Start background generation (same as existing /api/generate logic)
        def generate_sow_worker():
            usage_context_token = None
            try:
                from app.core.nodes import start_token_usage
                usage_context_token = start_token_usage(task_id)
                update_task(task_id, status=TaskStatus.PROCESSING, progress=10, current_step="Initializing SOW generation...")

                # Run the graph workflow (same as existing logic)
                initial_state = {
                    "metadata": {
                        "customer_name": customer_name,
                        "author_name": author_name,
                        "author_org": "Shellkode",  # Required by research_node
                        "company_name": customer_name,  # Required by research_node
                        "project_name": project_name,
                        "mode": mode,
                        "task_id": task_id,
                        **ownership,
                    },
                    "objective": objective,
                    "analyzed_requirements": None,
                    "validated_requirements": None,
                    "poc_content": None,
                    "output_path": None,
                    "json_path": None,
                    "errors": [],
                    "current_step": "Starting",
                    "mode": mode,
                    "source_file": None,
                    "is_poc_table_conversion": False,
                    "supporting_documents": None,
                    "supporting_context": None
                }

                # Create and run graph
                graph = create_graph()
                config_obj = {"recursion_limit": 100}

                final_state = None
                for step_state in graph.stream(initial_state, config=config_obj):
                    final_state = step_state
                    # Update progress based on steps
                    if 'research' in step_state:
                        update_task(task_id, progress=30, current_step="Researching company...")
                    elif 'analyze' in step_state:
                        update_task(task_id, progress=50, current_step="Analyzing requirements...")
                    elif 'validate' in step_state:
                        update_task(task_id, progress=70, current_step="Validating content...")
                    elif 'generate' in step_state:
                        update_task(task_id, progress=85, current_step="Generating document...")
                    elif 'build' in step_state:
                        update_task(task_id, progress=95, current_step="Building final document...")

                # Extract result from final state
                if final_state and '__end__' in final_state:
                    end_state = final_state['__end__']
                    output_path = end_state.get('output_path')
                    from app.core.nodes import get_token_usage
                    token_usage = get_token_usage(task_id)
                    total_tokens = int(token_usage.get("total_tokens") or 0)

                    if output_path and os.path.exists(output_path):
                        # Upload to S3 and get drive link (same as existing logic)
                        drive_link = None
                        s3_url = None

                        try:
                            drive_link = upload_generated_document(output_path)
                        except Exception as upload_error:
                            print(f"⚠️ Google Drive upload failed: {upload_error}")

                        try:
                            folder = FOLDER_MAPPING.get(mode, "other")
                            s3_url = upload_to_s3(output_path, folder)
                        except Exception as s3_error:
                            print(f"⚠️ S3 upload failed: {s3_error}")

                        # Save to DynamoDB (agentic-poc table)
                        sow_id = save_to_dynamodb(
                            metadata={
                                "company_name": customer_name,
                                "author_name": author_name,
                                "project_name": project_name,
                                "document_date": datetime.now().strftime("%d %B %Y"),
                                "mode": mode,
                                "total_tokens": total_tokens,
                                "token_usage": token_usage,
                                **ownership,
                            },
                            s3_url=s3_url,
                            s3_result={"https_url": s3_url, "s3_url": s3_url} if s3_url else None,
                            drive_link=drive_link,
                            table_name=os.getenv('DYNAMODB_TABLE_POC_DOCUMENTS', 'agentic-poc'),
                            region=os.getenv('AWS_REGION', 'us-east-1'),
                            task_id=task_id,
                            account_id=project.get('account_id'),
                            project_id=project_id
                        )

                        # Link SOW to project in agentic-sow-v2 table
                        sow_data = {
                            'mode': mode,
                            'customer_name': customer_name,
                            'project_name': project_name,
                            'drive_link': drive_link,
                            's3_url': s3_url,
                            'sow_db_id': sow_id,
                            'total_tokens': total_tokens,
                            'token_usage': token_usage,
                            **ownership,
                        }
                        account_handler.link_sow_to_project(project_id, sow_id, sow_data)

                        # Update task as completed
                        update_task(
                            task_id,
                            status=TaskStatus.COMPLETED,
                            progress=100,
                            current_step="Completed",
                            completed_at=datetime.now().isoformat(),
                            result={
                                'output_path': output_path,
                                'drive_link': drive_link,
                                's3_url': s3_url,
                                'sow_id': sow_id,
                                'project_id': project_id,
                                'total_tokens': total_tokens,
                                'token_usage': token_usage,
                            }
                        )
                    else:
                        update_task(task_id, status=TaskStatus.FAILED, error="Document generation failed")
                else:
                    update_task(task_id, status=TaskStatus.FAILED, error="Workflow did not complete")

            except Exception as e:
                print(f"❌ Error in SOW generation worker: {e}")
                import traceback
                traceback.print_exc()
                update_task(task_id, status=TaskStatus.FAILED, error=str(e))
            finally:
                if usage_context_token is not None:
                    from app.core.nodes import clear_token_usage, unbind_token_usage
                    unbind_token_usage(usage_context_token)
                    clear_token_usage(task_id)

        # Start worker thread
        worker = threading.Thread(target=generate_sow_worker, daemon=True)
        worker.start()

        return jsonify({
            "success": True,
            "task_id": task_id,
            "project_id": project_id,
            "message": "SOW generation started"
        }), 202

    except Exception as e:
        print(f"❌ Error creating SOW for project: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/sows/<sow_id>', methods=['DELETE'])
def delete_sow(sow_id):
    """Permanently delete a generated SOW. Administrators only."""
    try:
        denied = _require_admin_response()
        if denied:
            return denied

        handler = DynamoDBHandler()
        record = handler.get_document_by_id(sow_id)
        if not record:
            return jsonify({"success": False, "error": "SOW not found"}), 404

        for url_field in ('s3_url', 'draft_preview_s3_url'):
            s3_url = str(record.get(url_field) or '').strip()
            if s3_url:
                bucket, key = parse_s3_location(s3_url)
                get_s3_client().delete_object(Bucket=bucket, Key=key)
                print(f"[SOW DELETE] Removed {url_field} s3://{bucket}/{key}", flush=True)

        if not handler.delete_document(sow_id, str(record.get('timestamp') or '')):
            return jsonify({"success": False, "error": "SOW metadata deletion failed"}), 500

        # Remove any project/account link and repair its counters. This helper
        # is tolerant of records generated outside the Accounts workflow.
        account_handler.delete_sow(sow_id)
        print(
            f"[SOW DELETE] Admin {current_identity().email} permanently deleted {sow_id}",
            flush=True,
        )

        return jsonify({
            "success": True,
            "message": "SOW permanently deleted"
        })
    except Exception as e:
        print(f"❌ Error deleting SOW: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/admin/fix-account-counts/<account_id>', methods=['POST'])
def fix_account_counts_admin(account_id):
    """Admin endpoint to manually fix account counts"""
    try:
        denied = _require_admin_response()
        if denied:
            return denied
        data = request.json or {}
        project_count = data.get('project_count', 0)
        sow_count = data.get('sow_count', 0)

        account_handler.table.update_item(
            Key={
                'PK': f'ACCOUNT#{account_id}',
                'SK': 'METADATA'
            },
            UpdateExpression='SET project_count = :pc, sow_count = :sc',
            ExpressionAttributeValues={
                ':pc': project_count,
                ':sc': sow_count
            }
        )

        return jsonify({
            "success": True,
            "message": f"Updated counts to {project_count} projects, {sow_count} SOWs"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# DRAFT MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/projects/<project_id>/drafts', methods=['GET'])
def get_project_drafts(project_id):
    """Get all drafts for a project"""
    try:
        denied = _resource_denied(account_handler.get_project(project_id))
        if denied:
            return denied
        print(f"📝 Fetching drafts for project: {project_id}")
        drafts = account_handler.list_drafts_for_project(project_id)
        print(f"📝 Found {len(drafts)} drafts")

        # Debug: print draft details
        for draft in drafts:
            print(f"   - Draft ID: {draft.get('draft_id')}")
            print(f"     Created: {draft.get('created_at')}")
            print(f"     Project: {draft.get('metadata', {}).get('project_title', 'N/A')}")

        return jsonify({
            "success": True,
            "drafts": drafts,
            "count": len(drafts)
        })
    except Exception as e:
        print(f"❌ Error fetching drafts: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/projects/<project_id>/drafts/<draft_id>', methods=['GET'])
def get_draft(project_id, draft_id):
    """Get a specific draft"""
    try:
        denied = _resource_denied(account_handler.get_project(project_id))
        if denied:
            return denied
        draft = account_handler.get_draft(project_id, draft_id)
        if not draft:
            return jsonify({
                "success": False,
                "error": "Draft not found"
            }), 404

        return jsonify({
            "success": True,
            "draft": draft
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/projects/<project_id>/drafts/<draft_id>', methods=['DELETE'])
def delete_draft(project_id, draft_id):
    """Delete a draft"""
    try:
        denied = _resource_denied(account_handler.get_project(project_id))
        if denied:
            return denied
        success = account_handler.delete_draft(project_id, draft_id)
        if not success:
            return jsonify({
                "success": False,
                "error": "Failed to delete draft"
            }), 500

        return jsonify({
            "success": True,
            "message": "Draft deleted successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# MAIN
# ============================================================================

_server_instance_mutex = None


def _acquire_server_instance_lock():
    """Prevent two Windows backend processes from sharing port 9000.

    Multiple Flask processes were able to listen on the same Windows port,
    causing requests and terminal output to be split between two consoles.
    A named OS mutex gives this local development server one unambiguous owner.
    """
    global _server_instance_mutex
    if os.name != "nt":
        return
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.CreateMutexW(None, False, "Local\\ShellKodeSOWBackend9000")
    if not handle:
        raise OSError(ctypes.get_last_error(), "Could not create backend instance lock")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        raise RuntimeError(
            "Another ShellKode backend is already running on port 9000. "
            "Stop its terminal with Ctrl+C before starting a new one."
        )
    _server_instance_mutex = handle

if __name__ == '__main__':
    print("[LLM] Pipeline revision: sonnet5-compact-json-v2")
    print("[LLM] Structured-generation output ceiling: 32768 tokens per call")
    print("[LLM] Truncation/invalid structured output: hard failure (no document fallback)")
    print("[LLM] Raw responses: backend/output/llm-debug")
    _acquire_server_instance_lock()
    print("\n" + "="*70)
    print("🚀 AWS SOW Generator API (WITH PREVIEW/EDIT/FINALIZE WORKFLOW)")
    print("="*70)
    print("\n📌 Server Configuration:")
    print(f"   • Port: 9000")
    print(f"   • Host: 0.0.0.0")
    print(f"   • Upload folder: {UPLOAD_FOLDER}")
    print(f"   • Max file size: 10MB")
    print(f"   • CORS: Enabled")
    print(f"   • Processing: Async (Background threads)")
    print("\n✅ ASYNC FEATURES")
    print("   • Immediate response with task ID")
    print("   • No connection timeouts")
    print("   • Background processing")
    print("   • Real-time status updates")
    print("   • Concurrent request handling")
    print("   • Automatic task cleanup (1 hour)")
    print("\n✨ NEW: PREVIEW/EDIT/FINALIZE WORKFLOW")
    print("   • API 1: /api/preview → Generate content only (no document)")
    print("   • API 2: /api/edit → Smart section editing with LLM analysis")
    print("   • API 3: /api/finalize → Create document from edited content")
    print("   • Preview data stored in memory (not in history)")
    print("   • Smart editing identifies which sections to change")
    print("   • POC_TO_PROD: Extract text from PDF/DOCX first")
    print("\n✅ ENHANCED: FULL TASK DETAILS IN ALL HISTORY APIS + DRIVE LINKS")
    print("   • History APIs return same structure as /api/task/<id>")
    print("   • Active tasks include full task + document objects")
    print("   • Completed tasks include full task + document objects")
    print("   • Consistent structure across all endpoints")
    print("   • Real-time progress with complete metadata")
    print("   • Google Drive links included in ALL responses")
    print("\n✅ FIXES APPLIED:")
    print("   1. Race condition in task creation (FIXED)")
    print("   2. Timestamp sorting with error handling (FIXED)")
    print("   3. Memory leak prevention for stuck tasks (FIXED)")
    print("   4. DynamoDB fallback for cleaned tasks (FIXED)")
    print("   5. Unified response structure across all endpoints (NEW)")
    print("   6. Drive link integration in ALL history APIs (UPDATED)")
    print("   7. Preview/Edit/Finalize workflow (NEW)")
    print("\n✅ CONVERSION METHODS:")
    print("   1. Native dynamic Word fields (default, dependency-free)")
    print("   2. Optional LibreOffice cache precomputation")
    print("\n✅ CLOUD STORAGE:")
    print("   • Google Drive (Optional - with link in ALL history APIs)")
    print("   • AWS S3 (Primary)")
    print("   • DynamoDB History (agentic-poc)")
    print("\n" + "="*70)
    print("📋 API ENDPOINTS:")
    print("="*70)
    print("\n🔹 Document Generation (Original):")
    print("   POST /api/generate → Returns task ID immediately")
    print("   GET  /api/task/<task_id> → Full task details (with DB fallback)")
    print("\n✨ Preview/Edit/Finalize Workflow (NEW):")
    print("   POST /api/preview → Generate content preview (returns preview_id)")
    print("   POST /api/edit → Smart edit specific sections (requires preview_id + user_input)")
    print("   POST /api/finalize → Create final document (requires preview_id)")
    print("\n🔹 Health & Monitoring:")
    print("   GET  /health → Health check")
    print("\n🔹 Download:")
    print("   POST /api/proxy-download (CORS fallback)")
    print("\n🔹 History (WITH FULL TASK DETAILS + DRIVE LINKS):")
    print("   GET  /api/history → All task objects (active + completed + drive_link)")
    print("   GET  /api/recent-pocs → POC task objects (+ drive_link)")
    print("   GET  /api/recent-prod → PROD task objects (+ drive_link)")
    print("   GET  /api/recent-poc_to_prod → POC_TO_PROD task objects (+ drive_link)")
    print("   GET  /api/search-suggestions → Autocomplete")
    print("\n📦 WORKFLOW EXAMPLE:")
    print("   1. POST /api/preview (mode=POC, company_name, project_name, ...)")
    print("      → Returns: preview_id + structured content")
    print("   2. POST /api/edit (preview_id, user_input='Change executive summary')")
    print("      → Returns: updated content with smart section editing")
    print("   3. POST /api/finalize (preview_id)")
    print("      → Creates document, saves to S3/Drive/DB, returns task_id")
    print("\n" + "="*70)
    print("🌐 Server URL: http://localhost:9000")
    print("="*70 + "\n")

    # Start the Flask server
    try:
        app.run(
            host='0.0.0.0',
            port=9000,
            debug=False,
            threaded=True,
            use_reloader=False,   # prevents double-start on Windows
        )
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
    except Exception as e:
        print(f"\n\n❌ Server error: {e}")
        import traceback
        traceback.print_exc()

        
