"""Replay an existing calculator audit without repeating BRD or Bedrock calls."""
import argparse
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--restore-opensearch-serverless', action='store_true',
                        help='Remove zero-node provisioned inputs added by the broken template retry')
    args = parser.parse_args()
    from app.pricing.mcp_client import CalculatorMcpClient
    from app.pricing.service import AwsPricingService

    records = (json.loads(line) for line in (BACKEND / 'output/logs/pricing.jsonl').read_text(encoding='utf8').splitlines())
    record = next(row for row in records if row['audit_id'] == args.audit_id)
    entries = copy.deepcopy(record['result']['calculator_entries'])
    runtime = BACKEND.parent / 'tools/aws-pricing-calculator'
    result = {'source_audit_id': args.audit_id, 'region': record['region'], 'corrections': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with CalculatorMcpClient(runtime / 'dist/mcp-server.js', timeout=180) as client:
        if args.restore_opensearch_serverless:
            fields = client.call('get_service_fields', {'service': 'amazonElasticsearchService', 'partition': 'aws'})
            allowed = {field['id'] for field in fields['fields']
                       if field.get('templateId') == 'elasticSearchService-serverlesss'} | {'region', 'description'}
            for entry in entries:
                if entry['service'] != 'amazonElasticsearchService' or 'serverless' not in entry.get('instance', '').lower():
                    continue
                config = entry['config']
                # These nodes were introduced by the failed repair at zero.
                # Refuse to remove provisioned capacity with a real charge.
                for key in ('columnFormIPM', 'columnFormIPM_1', 'columnFormIPM_2'):
                    for row in config.get(key, {}).get('value', []):
                        assert all(float(value['value']) == 0 for name, value in row.items()
                                   if name.startswith('Number of Nodes')), 'Cannot discard provisioned nodes'
                removed = set(config) - allowed
                assert removed <= {'columnFormIPM', 'columnFormIPM_1', 'columnFormIPM_2',
                                   'numberOfInstances', 'storageType', 'storageAmount'}, removed
                assert float(config.get('storageAmount', {}).get('value', 0)) == 0, 'Cannot discard storage'
                entry['config'] = {key: value for key, value in config.items() if key in allowed}
                result['corrections'].append({'service': entry['service'], 'removed_retry_fields': sorted(removed)})
        result['calculator_entries'] = entries
        built = client.call('build_estimate', {
            'services': json.dumps(entries, separators=(',', ':')),
            'name': record['project'][:80] + ' - verified replay', 'partition': 'aws'})
        result['build'] = built
        args.output.write_text(json.dumps(result, indent=2), encoding='utf8')
        assert built.get('sharable_url'), built
        assert not any(row.get('partial') or row.get('success') is False or row.get('error')
                       for row in built.get('services', [])), built
    reader = AwsPricingService(SimpleNamespace(
        AWS_PRICING_COST_READER=runtime / 'scripts/read-cost.js',
        AWS_PRICING_NODE_BINARY='node', AWS_PRICING_COST_TIMEOUT_SECONDS=150), llm=object())
    result['estimate_url'] = built['sharable_url']
    result['cost'] = reader._read_cost(result['estimate_url'])
    args.output.write_text(json.dumps(result, indent=2), encoding='utf8')
    assert result['cost'].get('monthlyCost', 0) > 0, result['cost']
    assert abs(sum(result['cost']['monthlyByService'].values()) - result['cost']['monthlyCost']) < 0.15
    print(json.dumps({'audit_id': args.audit_id, 'estimate_url': result['estimate_url'],
                      'entry_count': len(entries), 'cost': result['cost']}, indent=2))


if __name__ == '__main__':
    main()
