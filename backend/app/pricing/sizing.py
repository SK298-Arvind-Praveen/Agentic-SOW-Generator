"""BRD-grounded estimates mapped to live calculator contracts, with one repair."""
import json
import math
import re


def normalize_config(config, contracts):
    """Translate equivalent scalar/wrapper forms using the live schema only."""
    # Some models return the calculator's API envelope rather than its flat
    # config. Unwrap only known envelopes; still validate every actual field.
    result={k:v for k,v in config.items() if k not in {'serviceCode','serviceName','fields','calculationComponents','estimateFor'}}
    for wrapper in ('fields','calculationComponents'):
        if isinstance(config.get(wrapper),dict):
            for key,value in config[wrapper].items():
                if key in result and result[key] != value:
                    raise ValueError(f'Conflicting wrapped input: {key}')
                result[key]=value
    if str(result.get('vcpuPerTask')) in {'0.5','1','2','4'} and 'smallMemory' in result and 'memoryStandardFargateOnDemand' in contracts:
        memory=result.pop('smallMemory')
        memory=memory.get('value') if isinstance(memory,dict) else memory
        target={'value':str(memory),'unit':'gb|NA'}
        if 'memoryStandardFargateOnDemand' in result and result['memoryStandardFargateOnDemand'] != target:
            raise ValueError('Conflicting Fargate memory quantities')
        result['memoryStandardFargateOnDemand']=target
    for key,value in list(result.items()):
        field=contracts.get(key,{})
        kind=field.get('type')
        if kind=='numericInput':
            if isinstance(value,dict):
                if value.get('unit'):
                    raise ValueError(f'{key} is a plain numericInput; express its quantity in the field label units')
                value=value.get('value')
            result[key]=str(value)
        elif kind=='dropdown':
            result[key]=str(value.get('value') if isinstance(value,dict) else value)
        elif kind in {'fileSize','frequency','durationInput'}:
            if isinstance(value,str) and '|' in value and kind=='fileSize':
                quantity,unit=value.split('|',1)
                value={'value':quantity,'unit':unit}
            if not isinstance(value,dict):
                unit=field.get('defaultUnit')
                if not unit: raise ValueError(f'{key} needs a value/unit object; choose unit from its contract')
                value={'value':str(value),'unit':unit}
            value=dict(value)
            if not value.get('unit') and field.get('defaultUnit'):
                value['unit']=field['defaultUnit']
            if not value.get('unit'): raise ValueError(f'{key} has no unit')
            choices=[o['id'] for o in field.get('options',[]) if isinstance(o,dict) and o.get('id')]
            if kind!='fileSize' and choices and value['unit'] not in choices:
                raise ValueError(f'{key} unit must be one of {choices}')
            if kind=='fileSize' and '|' not in value['unit']:
                raise ValueError(f'{key} unit must include size and frequency, e.g. {field.get("defaultUnit")}')
            value['value']=str(value.get('value',''))
            if not value['value']: raise ValueError(f'{key} has an empty quantity')
            result[key]=value
    return result


def prepare_estimated_service(owner, client, service, region):
    from .service import _json_object, _normalise_evidence, _field_contracts
    name = service['service_name']
    normalized = _normalise_evidence(name)
    context = str(service.get('_sizing_context') or '')
    # These controls have no separate usage line; their billable dependencies
    # (compute, storage, logs, etc.) remain separate calculator services.
    if normalized in {'aws iam', 'iam', 'aws identity and access management',
                      'amazon vpc', 'vpc', 'aws auto scaling', 'ec2 auto scaling', 'amazon ec2 auto scaling'}:
        service['_no_direct_charge'] = True
        service['_sizing_details'] = [{'service':name,'input':'Direct service charge',
            'value':'No separate charge; billable resources priced separately', 'status':'Pricing basis'}]
        return None, []
    if normalized in {'aws systems manager', 'systems manager', 'aws systems manager parameter store', 'aws systems manager session manager'} and not re.search(
            r'advanced parameters|higher.throughput|systems manager automation|opscenter|incident manager', context, re.I):
        service['_no_direct_charge'] = True
        service['_sizing_details'] = [{'service':name,'input':'Management tier',
            'value':'Standard-throughput parameters and EC2 Session Manager; no direct service charge',
            'status':'Approximated','reason':'POC assumes standard features; CloudWatch logs and private endpoints are priced separately. https://aws.amazon.com/systems-manager/pricing/'}]
        return None, []
    alias = owner._calculator_service_code(name)
    context = str(service.get('_sizing_context') or '')
    evidence = json.dumps(service.get('usage_facts') or {})+' '+str(service.get('evidence_quote') or '')
    if not alias and re.search('load.?balanc',name,re.I) and re.search(r'\bALB\b|Application Load Balancer',context,re.I):
        alias = owner._calculator_service_code('Application Load Balancer')
    if not alias and normalized in {'amazon elastic container service','amazon ecs','aws ecs'} and 'fargate' in context.lower():
        alias = ('awsFargate','AWS Fargate')
    if alias:
        code = alias[0]
    else:
        hits = client.call('search_services', {'query':re.sub(r'^(AWS|Amazon)\s+', '', name, flags=re.I),'partition':'aws'})
        hit = owner._select_service_hit(hits,name)
        if not hit:
            result = owner.llm.generate('Select the exact calculator product for this architecture service. '
                'Return JSON {"key":"exact key from results"}. Do not invent keys.\n'
                +json.dumps({'service':name,'context':context,'search_results':hits}),
                task='analysis',max_tokens=1500,temperature=0,call_name='AWS Pricing Product Selection')
            key = _json_object(result.text).get('key')
            candidates = hits if isinstance(hits,list) else [x for v in hits.values() if isinstance(v,list) for x in v]
            hit = next((h for h in candidates if isinstance(h,dict) and h.get('key')==key),None)
        if not hit:
            return None,[{'field':name,'reason':'No matching calculator product found','basis':'Product resolution'}]
        code = hit.get('redirect_to') or hit.get('key') or hit.get('serviceCode')
    fields = client.call('get_service_fields',{'service':code,'partition':'aws'})
    # Keep optional products visible: sizing is allowed to infer audit usage
    # from the full architecture, not just the extractor's narrow quote.
    feedback = service.get('_calculator_feedback', '')
    for attempt in range(2):
        try:
            prompt = '''Size this AWS service for a non-binding SOW monthly estimate, then map it to the live calculator.
The user authorizes reasonable engineering estimates for ALL missing inputs. Never return missing_inputs or blanks.
Preserve explicit BRD quantities, deployment constraints and supported service choices. Website region is authoritative.
Use on-demand prices, no commitments or discounts. Estimate normal monthly operation (730 hours for always-on
resources); do not confuse total POC duration with monthly hours. Record that assumption. Avoid overprovisioning.
For tests with peak RPS, distinguish peak from average; estimate duty cycle and payload sizes explicitly.
Use the real calculator fields and wrapped shapes, exact selector IDs and option IDs. Catalogue examples are shape
guidance; adapt sizes to this BRD. No dotted matrix keys. For RDS Multi-AZ use one DB deployment (standby included),
not two Multi-AZ DB instances. For NAT per AZ, use zonal numberOfGateways and zero all regional NAT fields;
use regional NAT only if the selected architecture explicitly requests it. Omit unused optional features.
Do not invent AWS dollar rates.
Return JSON {"config":{...},"sizing":[{"input":"brief sizing input","value":"value with units",
"status":"Approximated or Source-backed","reason":"brief rationale"}]}.
Every estimated rate-driving choice must have a sizing explanation. Combine related choices into 4-8 concise rows.
Keep reasons under 12 words. Do not list unused zero-cost optional features or repeat the selected region.
Do not add unrelated products. Empty config and empty sizing are invalid.
'''+json.dumps({'service':name,'region':region,'source_facts':service.get('usage_facts'),
                'BRD':context,'live_contract':fields,'repair_feedback':feedback},default=str)
            result=owner.llm.generate(prompt,task='analysis',max_tokens=10000,temperature=0,
                call_name=f'AWS Pricing Estimated Fields - {name}')
            mapped=_json_object(result.text)
            config=mapped.get('config')
            sizing=mapped.get('sizing')
            contracts=_field_contracts(fields)
            if not isinstance(config,dict) or not config or not sizing:
                raise ValueError('Complete config and sizing explanations are required')
            config=normalize_config(config,contracts)
            def check_values(value):
                if isinstance(value,dict):
                    for child in value.values(): check_values(child)
                elif isinstance(value,list):
                    for child in value: check_values(child)
                elif isinstance(value,(int,float)) and not isinstance(value,bool):
                    if not math.isfinite(value) or value<0: raise ValueError('Consumption must be finite and nonnegative')
                elif isinstance(value,str) and re.fullmatch(r'-?\d+(?:\.\d+)?|nan|inf(?:inity)?',value,re.I):
                    number=float(value)
                    if not math.isfinite(number) or number<0: raise ValueError('Consumption must be finite and nonnegative')
            check_values(config)
            unknown=set(config)-set(contracts)-{'region','description'}
            if unknown: raise ValueError('Unknown field IDs: '+str(sorted(unknown)))
            for key,value in config.items():
                if value is None or value=='': raise ValueError(f'Blank input: {key}')
                contract=contracts.get(key,{})
                if contract.get('type')=='dropdown':
                    choices=[str(o.get('id')) for o in contract.get('options',[]) if isinstance(o,dict)]
                    selected=value.get('value') if isinstance(value,dict) else value
                    if choices and str(selected) not in choices: raise ValueError(f'{key} must use one of {choices}')
            rows=[]
            for item in sizing:
                if not isinstance(item,dict) or not item.get('input') or not item.get('value'):
                    raise ValueError('Sizing explanations must contain input and value')
                # Preserve conservative provenance: only exact supplied facts
                # can be marked source-backed; inferred values stay approximate.
                status='Source-backed' if item.get('status')=='Source-backed' and str(item['value']).lower() in (context+' '+evidence).lower() else 'Approximated'
                rows.append({'service':name,**item,'status':status})
            calculator_region = region
            if code == 'awsCostExplorer':
                # Cost Explorer is global; its calculator product has only the
                # us-east-1 pricebook. This never relocates the workload.
                calculator_region = 'us-east-1'
                rows.append({'service':name,'input':'Global service pricebook','value':'Global (calculator uses us-east-1)',
                    'status':'Pricing basis','reason':f'Workload region remains {region}; Cost Explorer has no regional deployment.'})
            config.update(region=calculator_region,description=name+' - approximate monthly sizing')
            service['_sizing_details']=rows
            service['_calculator_fields']=fields
            # Flat estimate exposes every service directly; environment remains
            # in the SOW sizing evidence rather than hiding rows inside groups.
            service['_calculator_entry']={'service':code,'instance':name[:48],'config':config}
            return service['_calculator_entry'],[]
        except Exception as exc:
            feedback=str(exc)
            print(f'[PRICING][SIZING-RETRY] {name} attempt={attempt+1}: {feedback}',flush=True)
    return None,[{'field':name,'reason':feedback,'basis':'Estimated sizing failed validation after one retry'}]
