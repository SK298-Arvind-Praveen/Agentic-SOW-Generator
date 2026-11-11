"""Inspect reference retrieval without sending source documents to a model.

Run from backend: python scripts/inspect_architecture_knowledge.py --query "database migration"
Use --inputs repeatedly for saved Architecture_Inputs JSON snapshots.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.diagram.knowledge import reference_bundle, select_patterns, MAX_REFERENCE_PATTERNS
from app.diagram.service_design import _facts


def inspect(requirements, label):
    # This is the exact source-facts view used by capability/service selection.
    facts = _facts(requirements)
    bundle = reference_bundle(facts)
    return {'input': label, **{k: v for k, v in bundle.items() if k != 'context'},
            'context_chars': len(bundle['context']),
            'candidates': [{'id': c['id'], 'source_url': c['source_url']}
                           for c in select_patterns(facts, limit=MAX_REFERENCE_PATTERNS)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', action='append', default=[])
    parser.add_argument('--query', action='append', default=[])
    parser.add_argument('--output', default='output/architecture-knowledge-retrieval.json')
    args = parser.parse_args()
    if not args.inputs and not args.query:
        parser.error('Provide --inputs or --query')
    rows = [inspect({'features': [query]}, 'query-' + str(i + 1))
            for i, query in enumerate(args.query)]
    for filename in args.inputs:
        raw = json.loads(Path(filename).read_text(encoding='utf-8-sig'))
        rows.append(inspect(raw.get('requirements', raw), str(Path(filename))))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'mode': 'offline_retrieval_only', 'results': rows}, indent=2), encoding='utf-8')
    for row in rows:
        print(json.dumps({'input': row['input'], 'patterns': row['pattern_ids'],
                          'omitted': row['omitted_for_budget'], 'chars': row['context_chars']}))
    print('Report:', path)


if __name__ == '__main__':
    main()
