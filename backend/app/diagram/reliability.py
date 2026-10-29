"""Structural publication checks and bounded best-effort visual repairs."""
import copy
import json
import time


def structured_retry(call, prompt, validate, *, attempts=3, deadline=None):
    """Retry the exact contract, never accept malformed patches or invent a graph."""
    from app.diagram.service import _extract_json
    from app.core.bedrock_llm import BedrockOutputTruncatedError
    from botocore.exceptions import ClientError, ConnectionClosedError, EndpointConnectionError, ReadTimeoutError
    last = None
    for attempt in range(attempts):
        if deadline is not None and deadline - time.monotonic() < 5:
            break
        try:
            raw = call(prompt)
        except (BedrockOutputTruncatedError, ConnectionClosedError, EndpointConnectionError, ReadTimeoutError, ClientError) as exc:
            if isinstance(exc, ClientError) and exc.response.get('Error', {}).get('Code') not in {
                    'ThrottlingException', 'ServiceUnavailableException', 'InternalServerException', 'ModelNotReadyException'}:
                raise
            last = exc
            print(f'[DIAGRAM][STRUCTURE] attempt={attempt + 1}; transient={type(exc).__name__}', flush=True)
            if isinstance(exc, BedrockOutputTruncatedError):
                prompt += '\nThe response exceeded its output limit. Return concise COMPLETE JSON; no prose or repeated evidence.'
            continue
        try:
            return validate(_extract_json(raw))
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            last = exc
            print(f'[DIAGRAM][STRUCTURE] attempt={attempt + 1}; rejected={exc}', flush=True)
            prompt += ('\nYour previous response failed validation: ' + str(exc)
                       + '\nReturn the COMPLETE corrected JSON object using exactly the specified schema. '
                       'Preserve graph membership and all connections. No Markdown.\nREJECTED JSON:\n'
                       + str(raw)[:24000])
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
    if not asset.get('image_base64'):
        reasons.append('No rendered image')
    if asset.get('used_fallback'):
        reasons.append('Generic fallback plan is not publishable')
    metrics = asset.get('layout_metrics') or {}
    # Crossings, shared tracks, detours and omitted arrow captions are layout
    # diagnostics, not grounds to discard an otherwise valid architecture.
    # Font size deliberately has no publication threshold.
    for key in ('node_overlaps', 'out_of_bounds', 'containment_violations'):
        if metrics.get(key, 0):
            reasons.append(f'{key}={metrics[key]}')
    review = asset.get('vision_review') or {}
    # A timed-out/malformed cosmetic review must not veto the original image.
    # Architecture findings remain blocking, including ones recorded before a
    # malformed visual patch prevented the reviewer from completing.
    if review.get('unresolved_architecture') or any(
            i.get('kind') == 'architecture' for i in review.get('issues', []) if isinstance(i, dict)):
        reasons.append('Unresolved architecture findings')
    return reasons


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
