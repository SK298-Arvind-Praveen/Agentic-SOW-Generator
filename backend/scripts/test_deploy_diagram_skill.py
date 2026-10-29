"""Isolated AWS plugin skill experiment; never imports the SOW diagram pipeline."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import boto3
from defusedxml import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.config import Config
from app.core.bedrock_llm import BedrockLLM

BASE = ROOT / 'output/deploy-plugin-test'
PLUGIN = BASE / 'upstream/plugins/deploy-on-aws'
SKILL = PLUGIN / 'skills/aws-architecture-diagram'
REFS = ['xml-rules.md', 'style-guide.md', 'xml-templates-structure.md',
        'layout-guidelines.md', 'general-icons.md', 'group-styles.md',
        'aws4-shapes-services.md', 'aws4-shapes-resources.md']
OVERRIDES = """
User overrides take priority over conflicting skill defaults:
NO title, subtitle, separator, legend, numbered badges, notes or explanatory text.
Service labels only, not feature labels or descriptions. Separate Lambda functions
are allowed for distinct business responsibilities; do not force consolidation.
NO tinted category boxes or service containers. Bare official icons and their labels.
White/unfilled Cloud and Region boundaries; shading ONLY for actual subnets.
Region label must be 'Region'. No geographic region or 'proposed'.
Do not force VPCs or subnets for this managed-serverless logical design.
KMS, Secrets Manager, CloudWatch are a compact unfilled Security and Monitoring
group, no individual control arrows. IAM inside Cloud, outside Region.
Use the skill's decoration-only Region (container=0); real visible AWS borders/logos.
The architecture is already selected: do not ask questions or change the scope.
Use a compact landscape layout; short, distinct connections that visibly touch
their endpoints. Avoid crossings, arrow paths through labels, long perimeter loops,
and duplicate API Gateway-to-Lambda edges. Allow space for labels below icons.
All external systems remain outside Cloud. No external image URLs or hyperlinks.
Output ONLY complete uncompressed mxfile XML. No code fences or prose.
This host renders/validates locally; do not launch commands or claim to check docs.
"""

def command(args, output, name):
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=90,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (output / name).write_text(result.stdout + result.stderr, encoding='utf-8')
    print(result.stdout + result.stderr, flush=True)
    result.check_returncode()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repair', type=Path)
    parser.add_argument('--feedback', default='')
    args = parser.parse_args()
    output = BASE / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output.mkdir(parents=True)
    os.environ['LLM_RAW_OUTPUT_DIR'] = str(output / 'llm-outputs')
    config = Config()
    client = boto3.client('bedrock-runtime', region_name=config.BEDROCK_REGION,
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        aws_session_token=os.getenv('AWS_SESSION_TOKEN'), config=config.BOTO_CONFIG)
    architecture = (ROOT / 'scripts/axis_mcp_explicit_prompt.txt').read_text(encoding='utf-8')
    architecture = architecture.split('Check AWS documentation')[0]
    prompt = 'Generate the Axis diagram using this AWS plugin skill and references.\n'
    prompt += (SKILL / 'SKILL.md').read_text(encoding='utf-8')
    for name in REFS:
        prompt += '\nREFERENCE: ' + name + '\n' + (SKILL / 'references' / name).read_text(encoding='utf-8')
    prompt += '\nARCHITECTURE:\n' + architecture + '\nFINAL USER OVERRIDES:\n' + OVERRIDES
    if args.repair:
        prompt += '\nCorrect this previous XML:\n' + args.repair.read_text(encoding='utf-8')
        prompt += '\nVisual review feedback:\n' + args.feedback
    (output / 'prompt.txt').write_text(prompt, encoding='utf-8')
    print('OUTPUT: ' + str(output), flush=True)
    start = time.monotonic()
    result = BedrockLLM(config, client).generate(prompt, task='diagram', max_tokens=16000,
        call_name='AWS deploy plugin drawio standalone', retry_on_truncation=False)
    metadata = asdict(result)
    metadata.pop('text')
    metadata['generation_seconds'] = round(time.monotonic() - start, 2)
    (output / 'usage.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    match = re.search(r'<mxfile\b[\s\S]*?</mxfile>', result.text)
    if not match:
        raise ValueError('Model returned no complete mxfile XML')
    xml = match.group()
    tree = ET.fromstring(xml)
    if any('image=' in c.get('style', '') or c.get('link') for c in tree.iter()):
        raise ValueError('External images/links are not permitted')
    raw = output / 'axis-first-pass.drawio'
    raw.write_text(xml, encoding='utf-8')
    target = output / 'axis.drawio'
    shutil.copy2(raw, target)
    for script in ('post_process_drawio.py', 'validate_drawio.py'):
        command([sys.executable, str(PLUGIN / 'scripts/lib' / script), str(target)],
                output, script + '.log')
    renderer = BASE / 'drawio-portable/draw.io.exe'
    command([str(renderer), '-x', '-f', 'png', '-e', '-b', '20', '-s', '2',
             '-o', str(output / 'axis.drawio.png'), str(target)], output, 'export.log')
    png = output / 'axis.drawio.png'
    if not png.exists() or png.stat().st_size == 0:
        raise RuntimeError('Export did not produce a nonempty PNG')
    print(json.dumps(metadata), flush=True)
    print('IMAGE: ' + str(png), flush=True)

if __name__ == '__main__':
    main()
