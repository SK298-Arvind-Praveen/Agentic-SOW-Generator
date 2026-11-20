"""Pricing inventory derived from the selected architecture's EC2 nodes."""

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re


EC2_NAME = 'Amazon EC2'
EC2_CODE = 'ec2Enhancement'
EC2_ICONS = {
    'aws.service.compute.amazon-ec2',
    'aws.resource.compute.amazon-ec2-db-instance',
    'aws.resource.compute.amazon-ec2-instance',
    'aws.resource.compute.amazon-ec2-instances',
    'aws.resource.compute.amazon-ec2-instance-with-cloudwatch',
    'aws.resource.compute.amazon-ec2-spot-instance',
}
EC2_HOST_NAME = re.compile(r'(?:(?:amazon|aws) )?ec2(?: (?:db |spot )?instances?(?: with cloudwatch)?)?')
MONTH_HOURS = Decimal(730)
_HOURS_PER_MONTH = r'(\d+(?:\.\d+)?)\s*(?:h|hours?)\s*(?:/\s*|per\s+)month'


def selected_ec2_resources(requirements):
    architecture = requirements.get('approved_architecture') or requirements.get('architecture_design') or {}
    return sorted(({
        'id': node['id'],
        'label': node.get('label') or node['id'],
        'placement_role': node.get('placement_role') or '',
        'evidence': node.get('evidence') or '',
        'subtitle': node.get('subtitle') or '',
    } for node in architecture.get('nodes', [])
        if node.get('icon_key') in EC2_ICONS and node.get('scope') != 'external' and node.get('kind') != 'group'),
        key=lambda node: node['id'])


def ec2_resource_coverage(resources, configurations=()):
    required = sorted(node['id'] for node in resources)
    covered = sorted(resource_id for row in configurations for resource_id in row['resource_ids'])
    return {
        'required_resource_ids': required,
        'covered_resource_ids': covered,
        'missing_resource_ids': sorted(set(required) - set(covered)),
        'complete': bool(required) and required == covered,
        'configurations': list(configurations),
    }


def _decimal(value):
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Expected a finite numeric input') from exc
    if not number.is_finite():
        raise ValueError('Expected a finite numeric input')
    return number


def _quantity(workload):
    if isinstance(workload, dict):
        workload = workload.get('value')
        if not isinstance(workload, dict) or workload.get('workloadType') != 'consistent':
            raise ValueError('EC2 workload must use a consistent instance count plus monthly_hours')
        workload = workload.get('data')
    number = _decimal(workload)
    if number != number.to_integral_value():
        raise ValueError('EC2 workload must be a whole instance count')
    return int(number)


def _runtime_sizing(rows, monthly_hours, role, source):
    runtime = [row for row in rows if str(row.get('input')).strip().casefold() == 'monthly runtime']
    if len(runtime) != 1:
        raise ValueError('Each EC2 configuration requires one Monthly runtime sizing row')
    row = runtime[0]
    quantity = re.fullmatch(_HOURS_PER_MONTH, str(row.get('value', '')).strip(), flags=re.I)
    if not quantity or _decimal(quantity.group(1)) != monthly_hours:
        raise ValueError('Monthly runtime sizing must match monthly_hours in hours/month')
    reason = row.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Monthly runtime sizing requires a reason for the duty cycle')

    evidence = row.get('evidence_quote')
    quote = ' '.join(evidence.casefold().split()) if isinstance(evidence, str) else ''
    role = re.sub(r'\b(?:amazon |aws )?ec2\b', '', role, flags=re.I)
    role = ' '.join(role.casefold().split())
    backed = False
    if row.get('status') == 'Source-backed' and role and quote and quote in source:
        for sentence in re.split(r'(?<=[.!?])\s+|;', quote):
            quoted_hours = re.findall(rf'(?<![\w,.-]){_HOURS_PER_MONTH}\b', sentence)
            if re.search(rf'\b{re.escape(role)}s?\b', sentence) and {_decimal(n) for n in quoted_hours} == {monthly_hours}:
                backed = True
                break
    runtime = {'input': 'Monthly runtime', 'value': f'{format(monthly_hours.normalize(), "f")} hours/month',
               'reason': reason.strip(), 'status': 'Source-backed' if backed else 'Approximated'}
    if backed:
        runtime['evidence_quote'] = evidence.strip()
    return runtime


def map_ec2_configurations(mapped, resources, validate_config_and_sizing, region, source):
    """Validate the complete set atomically before producing calculator rows."""
    configs = mapped.get('configurations')
    if not isinstance(configs, list) or not configs:
        raise ValueError('Named EC2 configurations are required for the selected resource inventory')
    by_id = {node['id']: node for node in resources}
    if len(by_id) != len(resources):
        raise ValueError('Selected EC2 architecture contains duplicate resource IDs')
    labels = set()
    seen = set()
    entries, sizing, coverage = [], [], []
    source = ' '.join(source.casefold().split())
    for item in configs:
        if not isinstance(item, dict):
            raise ValueError('Each EC2 configuration must be an object')
        label = item.get('instance')
        if not isinstance(label, str) or not label.strip() or label.strip().casefold() in labels:
            raise ValueError('Each EC2 configuration requires a unique instance name')
        label = label.strip()
        labels.add(label.casefold())
        ids = item.get('resource_ids')
        if not isinstance(ids, list) or not ids or any(not isinstance(key, str) or key not in by_id for key in ids):
            raise ValueError(f'{label} must identify its selected EC2 resource IDs')
        if len(ids) != len(set(ids)) or seen.intersection(ids):
            raise ValueError(f'{label} repeats a selected EC2 resource ID')
        ids = sorted(ids)
        seen.update(ids)
        roles = {(by_id[key]['label'].casefold().strip(), by_id[key]['placement_role']) for key in ids}
        if len(roles) != 1:
            raise ValueError(f'{label} combines distinct EC2 roles; size each role separately')

        config, rows = validate_config_and_sizing(item)
        quantity = _quantity(config.get('workload'))
        if quantity < len(ids):
            raise ValueError(f'{label} workload must cover all {len(ids)} explicit instances')
        monthly_hours = _decimal(item.get('monthly_hours'))
        if not 0 < monthly_hours <= MONTH_HOURS:
            raise ValueError(f'{label} monthly_hours must be greater than 0 and at most 730')
        runtime = _runtime_sizing(item['sizing'], monthly_hours, by_id[ids[0]]['label'], source)
        rows = [{**runtime, 'service': EC2_NAME} if str(row['input']).strip().casefold() == 'monthly runtime' else row
                for row in rows]
        if not config.get('instanceType'):
            raise ValueError(f'{label} requires an EC2 instance type')
        storage_fields = ('storageAmount', 'storageAmountIo2', 'storageAmountDH', 'storageAmountIo2DH')
        if not any(_decimal(config[key].get('value') if isinstance(config[key], dict) else config[key]) > 0
                   for key in storage_fields if key in config):
            raise ValueError(f'{label} requires its own positive storage quantity')
        if not any(re.search(r'\bstorage\b|\bEBS\b|\bvolume\b', str(row['input']), re.I) for row in rows):
            raise ValueError(f'{label} requires a sizing explanation for its storage')

        # Use the graph IDs for identity so a sizing repair may rename or reorder rows.
        digest = sha256(json.dumps(ids).encode()).hexdigest()[:12]
        slug = re.sub(r'[^a-z0-9]+', '-', ids[0].casefold()).strip('-')[:35]
        instance = f'{slug}-{digest}'
        config.update(region=region, description=label, pricingStrategy='ondemand',
                      utilization=format((monthly_hours * 100 / MONTH_HOURS).normalize(), 'f'))
        entries.append({'service': EC2_CODE, 'instance': instance, 'config': config})
        sizing.extend({**row, 'instance': instance, 'configuration': label} for row in rows)
        coverage.append({'instance': instance, 'label': label, 'resource_ids': ids, 'quantity': quantity,
                         'monthly_hours': float(monthly_hours),
                         'runtime_status': runtime['status'], 'runtime_basis': runtime['reason'],
                         'status': 'Approximated' if any(r['status'] == 'Approximated' for r in rows) else 'Source-backed'})

    if uncovered := sorted(set(by_id) - seen):
        raise ValueError('Missing EC2 resource coverage: ' + ', '.join(uncovered))
    if len({entry['instance'] for entry in entries}) != len(entries):
        raise ValueError('EC2 calculator instance keys must be unique')
    return entries, sizing, ec2_resource_coverage(resources, coverage)
