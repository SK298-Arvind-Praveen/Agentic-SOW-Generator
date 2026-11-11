"""Optional conceptual diagrams must never discard otherwise valid SOW content."""
import logging

logger = logging.getLogger(__name__)


def generate_optional(config, requirements, source, scope, following_sections):
    from app.diagram.service import DiagramService
    from app.diagram.conceptual_drawio import generate
    service = None
    failures = []
    try:
        for attempt in (1, 2):
            try:
                if service is None:
                    service = DiagramService(config)
                asset = generate(service.llm, config, requirements, source, scope,
                                 planning_attempts=1, review_feedback=(
                                     'Previous attempt failed: '+failures[-1] if failures else ''))
                if not isinstance(asset, dict) or not asset.get('image_base64'):
                    raise ValueError('Conceptual diagram returned no image')
                return {**asset, 'following_sections': following_sections,
                        'generation_attempts': attempt, 'previous_errors': failures}
            except Exception as exc:
                failures.append(str(exc))
                logger.exception('Conceptual diagram attempt %s/2 failed; SOW content retained', attempt)
        return {'diagram_type':'conceptual_flow', 'status':'unavailable', 'image_base64':'',
                'following_sections':following_sections, 'generation_attempts':2,
                'errors':failures,
                'warning':'Conceptual diagram could not be generated after one retry. SOW content was preserved.'}
    finally:
        if service is not None:
            try:
                service.bedrock.close()
            except Exception:
                logger.exception('Could not close conceptual diagram client; SOW content retained')
