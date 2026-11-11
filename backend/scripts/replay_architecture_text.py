"""Exercise the same final-diagram prose writer used by preview generation."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    from app.core.config import Config
    from app.diagram.service import DiagramService
    from app.diagram.architecture_text import write
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit',required=True)
    parser.add_argument('--inputs',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.audit).read_text(encoding='utf8'))
    asset = report['assets'][0] if 'assets' in report else report
    inputs = json.loads(Path(args.inputs).read_text(encoding='utf8'))
    service = DiagramService(Config())
    try:
        text,audit = write(service.llm,asset,inputs.get('narrative',''),inputs.get('requirements',{}))
        path = Path(args.output)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding='utf8')
        path.with_suffix('.audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
        print(text)
        print(audit)
    finally:
        service.bedrock.close()


if __name__=='__main__':
    main()
