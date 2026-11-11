"""Check explicit deployment facts before a valid-looking graph can lose them."""
import re


def validate(spec, requirements):
    source = str(requirements.get('architecture_source_context') or '')
    if not source:
        return spec
    issues = []
    nodes = spec.nodes
    balancers = [n for n in nodes if 'load-balanc' in n.icon_key or re.search(r'\bALB\b', n.label)]
    if re.search(r'\binternal\s+(?:application load balancer|ALB)\b', source, re.I):
        if not balancers or any('internal' not in (n.label+' '+n.subtitle).lower() for n in balancers):
            issues.append('BRD requires an internal ALB: explicitly label it Internal ALB and preserve private ingress')
    migrations = {f['id'] for f in spec.architecture_plan.get('flows', []) if f.get('kind') == 'migration'}
    compute = [n for n in nodes if n.scope in {'az','vpc'} and n.placement_role == 'compute' and n.flow_id not in migrations]
    if compute and re.search(r'\b(?:two|2)\s+(?:(?:independent|hosting)\s+)*(?:AZs|availability zones|facilities)\b', source, re.I):
        if len({n.availability_zone for n in compute if n.availability_zone}) < 2:
            issues.append('BRD explicitly requires two AZs: distribute the application compute across two named AZs; do not invent duplicate resources')
    regions = set(re.findall(r'\b(?:eu|us|ap|sa|ca|me|af|il)-(?:north|south|east|west|central|northeast|southeast)-\d\b', source))
    if re.search(r'\b(?:UK|United Kingdom)\s+region\b', source, re.I) and any(
            not re.search(r'\b(?:UK|United Kingdom|London|eu-west-2)\b', n.region, re.I)
            for n in nodes if n.scope not in {'global','external'}):
        issues.append('Source requires UK-region hosting: explicitly choose and label the UK deployment region on regional nodes; do not use the placeholder Region')
    if len(regions) == 1:
        region = next(iter(regions))
        if any(n.region != region for n in nodes if n.scope not in {'global','external'}):
            issues.append('BRD specifies region '+region+': preserve it in every regional node, not the placeholder Region')
    if issues:
        raise ValueError('Deployment constraints: ' + '; '.join(issues))
    return spec
