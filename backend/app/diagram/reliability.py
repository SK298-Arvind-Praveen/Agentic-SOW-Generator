"""Structural publication checks and bounded best-effort visual repairs."""
import copy
import json
import time
from xml.etree.ElementTree import ParseError
from contextvars import ContextVar

# Each stage gets an initial call and one corrective call. A shared ledger keeps
# nested JSON helpers and pipeline resumes from multiplying the allowance.
pipeline_attempt = ContextVar('architecture_pipeline_attempt', default=0)
model_attempts = ContextVar('architecture_model_attempts', default=None)


def semantic_acceptance(asset):
    """A candidate can change dependent business content only after image review."""
    review = asset.get('vision_review') or {}
    return bool(asset.get('image_base64') and asset.get('spec') and not asset.get('used_fallback')
        and asset.get('status') not in {'unavailable', 'review_required'}
        and not asset.get('validation_warnings') and not asset.get('quality_warnings')
        and review.get('image_reviewed') is True
        and review.get('status') in {'reviewed', 'passed', 'reviewed_no_issues'}
        and not review.get('unresolved_architecture') and not review.get('issues'))


def _merge_repair(base, patch, allowed_fields=()):
    if not isinstance(patch, dict) or not patch or any(k not in base and k not in allowed_fields for k in patch):
        raise ValueError('Repair must update existing contract fields')
    result = copy.deepcopy(base)
    for key, value in patch.items():
        old = result.get(key)
        if isinstance(old, list) and old and all(isinstance(r, dict) and r.get('id') for r in old):
            if not isinstance(value, list) or any(not isinstance(r, dict) or not r.get('id') for r in value):
                raise ValueError('ID-based repair requires complete rows with IDs')
            ids = [r['id'] for r in value]
            if len(set(ids)) != len(ids):
                raise ValueError('Duplicate IDs in repair')
            replacements = {r['id']: r for r in value}
            result[key] = [replacements.pop(r['id'], r) for r in old] + list(replacements.values())
        else:
            result[key] = value
    return result


def structured_retry(call, prompt, validate, *, attempts=3, deadline=None, cache_key=None, targeted_repair=False, repair_fields=()):
    """Retry the exact contract, never accept malformed patches or invent a graph."""
    from app.diagram.service import _extract_json
    from app.core.bedrock_llm import BedrockOutputTruncatedError
    from botocore.exceptions import ClientError, ConnectionClosedError, EndpointConnectionError, ReadTimeoutError, ResponseStreamingError
    from urllib3.exceptions import ProtocolError, ReadTimeoutError as StreamReadTimeoutError
    attempts = min(attempts, 2) if pipeline_attempt.get() else attempts
    original_prompt = prompt
    from app.core.generation_efficiency import stage_cache, run_id, record
    import hashlib
    run = run_id()
    key = hashlib.sha256((str(cache_key) + prompt).encode()).hexdigest() if cache_key and run else None
    if key:
        cached = stage_cache.get(run, key)
        if cached is not None:
            try:
                result = validate(copy.deepcopy(cached))
                record({'stage': str(cache_key).split(':', 1)[0], 'result_cache_hits': 1})
                return result
            except (ValueError, TypeError, KeyError, IndexError):
                pass  # The current validator remains authoritative.
    last = None
    candidate = None
    patch_requested = False
    for attempt in range(attempts):
        if deadline is not None and deadline - time.monotonic() < 5:
            break
        try:
            raw = call(prompt)
        except (BedrockOutputTruncatedError, ConnectionClosedError, EndpointConnectionError, ReadTimeoutError,
                ResponseStreamingError, ProtocolError, StreamReadTimeoutError, ClientError) as exc:
            if isinstance(exc, ClientError) and str(exc.response.get('Error', {}).get('Code', '')).casefold() not in {
                    'throttlingexception', 'serviceunavailableexception', 'internalserverexception',
                    'modelnotreadyexception', 'modelstreamerrorexception'}:
                raise
            last = exc
            print(f'[DIAGRAM][STRUCTURE] attempt={attempt + 1}; transient={type(exc).__name__}', flush=True)
            if isinstance(exc, BedrockOutputTruncatedError):
                prompt += '\nThe response exceeded its output limit. Return concise COMPLETE JSON; no prose or repeated evidence.'
            elif attempt + 1 < attempts:
                # Do not burn the corrective attempt immediately into the same
                # transient endpoint outage. Keep cancellation responsive.
                from app.preview.cancellation import check_cancelled
                for _ in range(8):
                    check_cancelled()
                    time.sleep(.25)
            continue
        try:
            parsed = _extract_json(raw)
            if patch_requested and 'patch' in parsed:
                parsed = _merge_repair(candidate, parsed['patch'], repair_fields)
            candidate = copy.deepcopy(parsed)
            result = validate(copy.deepcopy(parsed))
            if key: stage_cache.put(run, key, parsed)
            return result
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            last = exc
            print(f'[DIAGRAM][STRUCTURE] attempt={attempt + 1}; rejected={exc}', flush=True)
            if targeted_repair and candidate is not None and not patch_requested:
                patch_requested = True
                prompt = original_prompt + ('\nValidation failed: ' + str(exc)
                    + '\nReturn only {"patch":{changed_field: corrected_value}}. '
                    'For arrays of objects with IDs return ONLY complete changed/new rows; unchanged IDs are retained. '
                    'For other fields return the corrected field value. Do not remove requirements or services. '
                    'The merged object will pass the same full validation.\nCURRENT JSON:\n'
                    + json.dumps(candidate, ensure_ascii=False))
                continue
            patch_requested = False
            prompt = original_prompt + ('\nYour previous response failed validation: ' + str(exc)
                       + '\nReturn the COMPLETE corrected JSON object using exactly the specified schema. '
                       'Preserve graph membership and all connections. No Markdown.\nREJECTED JSON:\n'
                       + (json.dumps(candidate, ensure_ascii=False) if candidate is not None else str(raw)))
    raise ValueError(f'Structured diagram response could not be validated: {last}')


def unavailable_asset(reason):
    # UI-only diagnostic; document builder already skips assets without pixels.
    return {'type': 'drawio_architecture', 'diagram_type': 'architecture_overview',
            'placement_heading': 'Solution Architecture', 'title': 'Solution Architecture',
            'status': 'unavailable', 'image_base64': '', 'drawio_xml': '', 'edit_url': '',
            'error': 'The diagram did not pass validation. Regenerate it in the preview.',
            'diagnostic': str(reason)[:1000], 'used_fallback': False}


def publication_issues(asset):
    reasons = []
    reasons.extend((asset.get('renderer_details') or {}).get('decoration_warnings') or [])
    if not asset.get('image_base64'):
        reasons.append('No rendered image')
    if asset.get('used_fallback'):
        reasons.append('Recovery diagram used because the primary pipeline failed; architecture is not verified')
    overview_diagnostic = ((asset.get('spec') or {}).get('architecture_plan') or {}).get('narrative_diagnostic')
    if overview_diagnostic:
        reasons.append('Functional overview unavailable; full graph retained: ' + str(overview_diagnostic)[:200])
    design = ((asset.get('spec') or {}).get('architecture_plan') or {}).get('service_design') or {}
    if design.get('status') == 'needs_review':
        reasons.append('Service selection needs review: ' + str(design.get('error', 'planning unavailable'))[:200])
    metrics = asset.get('layout_metrics') or {}
    # Crossings, shared tracks, detours and omitted arrow captions are layout
    # diagnostics, not grounds to discard an otherwise valid architecture.
    # Physical typography is checked against the exported figure in retry_issues.
    for key in ('node_overlaps', 'out_of_bounds', 'containment_violations'):
        if metrics.get(key, 0):
            reasons.append(f'{key}={metrics[key]}')
    review = asset.get('vision_review') or {}
    if asset.get('layout_engine') in {'narrative_drawio', 'deployment_drawio'} and any(
            i.get('kind') == 'visual' for i in review.get('issues', []) if isinstance(i, dict)):
        reasons.append('Overview image review found visual issues; see diagram diagnostics')
    # A timed-out/malformed cosmetic review must not veto the original image.
    # Architecture findings remain blocking, including ones recorded before a
    # malformed visual patch prevented the reviewer from completing.
    if review.get('unresolved_architecture') or any(
            i.get('kind') == 'architecture' for i in review.get('issues', []) if isinstance(i, dict)):
        reasons.append('Unresolved architecture findings')
    return reasons


def retry_issues(asset):
    """Quality triggers corrective work, never prevents saving the retained image."""
    reasons = publication_issues(asset) + asset.get('validation_warnings', [])
    metrics = asset.get('layout_metrics') or {}
    review = asset.get('vision_review') or {}
    if asset.get('diagram_type') == 'architecture_overview':
        if (review.get('image_reviewed') is not True
                or review.get('status') not in {'reviewed', 'passed', 'reviewed_no_issues'}):
            reasons.append('Image review is incomplete; the available architecture is not verified')
        if asset.get('image_base64') and asset.get('drawio_xml'):
            from app.diagram.figure_readability import fit_figure
            try:
                size = fit_figure(asset, 8.5, 11)['minimum_type_pt']
                if size is None or size < 8:
                    reasons.append(f'Architecture text needs a readable export layout (projected minimum {size} pt)')
            except (ValueError, TypeError, OSError, ParseError):
                reasons.append('Architecture export readability could not be verified')
    if metrics.get('connector_node_intersections'):
        reasons.append('Connectors intersect nodes')
    if metrics.get('connector_crossings', 0) > max(3, metrics.get('edges', 0) * .25):
        reasons.append('Overview has too many connector crossings')
    if review.get('status') in {'unavailable', 'review_unavailable', 'repair_failed', 'started'}:
        reasons.append('Image review incomplete: ' + str(review.get('error', review.get('status')))[:200])
    if any(i.get('kind') == 'visual' for i in review.get('issues', []) if isinstance(i, dict)):
        reasons.append('Image review found visual defects')
    return list(dict.fromkeys(reasons))


def retain_with_warning(asset):
    """Keep rendered output usable without representing a failed check as a pass."""
    advisories = [str(i['description']) for i in (asset.get('vision_review') or {}).get('advisories', [])
                  if isinstance(i, dict) and i.get('description')]
    if advisories: asset['layout_advisories'] = list(dict.fromkeys(advisories))
    reasons = retry_issues(asset)
    reasons += [str(i.get('description')) for i in (asset.get('vision_review') or {}).get('issues', [])
                if isinstance(i, dict) and i.get('description')]
    reasons = list(dict.fromkeys(reasons))
    if reasons:
        asset.update(status='review_required', quality_warnings=reasons,
            review_warning='Diagram needs review — generation or validation did not fully succeed. '
                           'The available diagram is retained for review and download.',
            diagnostic='; '.join(reasons)[:4000])
    return asset


def architecture_evidence(requirements):
    """Do not promote a service inventory from an earlier SOW into client facts."""
    result = copy.deepcopy(requirements)
    explicit = result.get('architecture_confirmed_services')
    if explicit is None:
        # Legacy requirements lack per-service evidence. Preserve choices, but
        # describe them honestly as proposals, not confirmed deployed products.
        explicit = []
    def names_in(value):
        return [s for s in (value if isinstance(value, list) else [value]) if isinstance(s, str) and s.strip()]
    explicit = names_in(explicit)
    names = list(dict.fromkeys(names_in(result.get('aws_services')) + names_in(result.get('confirmed_aws_services'))
                              + names_in(result.get('proposed_aws_services')) + explicit))
    result['confirmed_aws_services'] = explicit
    result['proposed_aws_services'] = [s for s in names if s not in explicit]
    result['aws_services'] = names
    result['architecture_evidence_policy'] = (
        'Existing systems are established by the current source documents. AWS implementation '
        'products named in a prior SOW or generated requirements are proposals, not client mandates. '
        'Select the minimum coherent deployment. Never treat the candidate inventory as a checklist. '
        'Discovery assumptions remain assumptions; region, AZ count and private connectivity are '
        'design choices unless the original evidence explicitly confirms them.')
    return result
