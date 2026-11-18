"""Exercise production extraction, analysis, service selection and pricing on a BRD."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    for stream in (sys.stdout,sys.stderr):
        stream.reconfigure(encoding='utf8',errors='replace')
    parser=argparse.ArgumentParser()
    parser.add_argument('--brd',required=True)
    parser.add_argument('--company',required=True)
    parser.add_argument('--region',default='ap-south-1')
    parser.add_argument('--output',required=True)
    parser.add_argument('--pricing-only',action='store_true')
    args=parser.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    from app.document.doc_reader import extract_supporting_documents_with_diagnostics
    from app.core.nodes import analyze_objective_node,rule_validation_node,solution_design_node,aws_pricing_node
    from app.pricing.renderer import render_aws_pricing_section
    if args.pricing_only:
        state=json.loads((out/'state.json').read_text(encoding='utf8'))
    else:
        source,count=extract_supporting_documents_with_diagnostics([args.brd])
        assert count==1 and source
        state={'metadata':{'company_name':args.company,'project_title':Path(args.brd).stem,
            'pricing_region':args.region},'supporting_context':source,'objective':'','mode':'POC',
            'selected_sow_sections':['aws_pricing'],'errors':[]}
        for node in (analyze_objective_node,rule_validation_node,solution_design_node):
            state.update(node(state))
            if state.get('errors'):raise RuntimeError(state['errors'])
            (out/'state.json').write_text(json.dumps(state,indent=2,default=str),encoding='utf8')
    state.update(aws_pricing_node(state))
    result=state['pricing_result']
    (out/'result.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf8')
    text=render_aws_pricing_section(result)
    (out/'pricing.md').write_text(text,encoding='utf8')
    print('RESULT',json.dumps({k:result.get(k) for k in ('status','region','estimate_url','monthly_cost','missing_inputs')},default=str))
    assert result['status']=='priced',result['status']
    assert result['region']==args.region and result['monthly_cost']>0
    assert not result['missing_inputs'],result['missing_inputs']
    assert text.startswith('AWS Pricing Calculator: [Open Link](https://calculator.aws/')
    assert 'Approximated' in text and 'Pending' not in text
    assert result['monthly_by_service']
    assert abs(sum(result['monthly_by_service'].values())-result['monthly_cost']) < 0.15
    for line in text.splitlines():
        if line.startswith('|'):
            assert all(cell.strip() for cell in line.strip('|').split('|')),line
    assert all(result['calculator_config_summaries'].values()),'Blank calculator configuration summary'

if __name__=='__main__':main()
