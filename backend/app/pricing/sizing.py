"""BRD-grounded estimates mapped to live calculator contracts, with one repair."""
import json
import math
import re

from .bedrock import bedrock_calculator_fields, bedrock_workload, prepare_guardrails, unsupported_embedding_basis, validate_bedrock_calculator
from .ec2_inventory import EC2_CODE, map_ec2_configurations


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


def _check_consumption(value):
    if isinstance(value, (dict, list)):
        for child in value.values() if isinstance(value, dict) else value:
            _check_consumption(child)
    elif (isinstance(value, (int, float)) and not isinstance(value, bool)
          or isinstance(value, str) and re.fullmatch(r'-?\d+(?:\.\d+)?|nan|inf(?:inity)?', value, re.I)):
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError('Consumption must be finite and nonnegative')


def _validated_config_and_sizing(mapped, contracts, name, source):
    config, sizing = mapped.get('config'), mapped.get('sizing')
    if not isinstance(config, dict) or not config or not isinstance(sizing, list) or not sizing:
        raise ValueError('Complete config and sizing explanations are required')
    config = normalize_config(config, contracts)
    _check_consumption(config)
    unknown = set(config) - set(contracts) - {'region', 'description'}
    if unknown:
        raise ValueError('Unknown field IDs: ' + str(sorted(unknown)))
    for key, value in config.items():
        if value is None or value == '':
            raise ValueError(f'Blank input: {key}')
        contract = contracts.get(key, {})
        if contract.get('type') == 'dropdown':
            choices = [str(o.get('id')) for o in contract.get('options', []) if isinstance(o, dict)]
            selected = value.get('value') if isinstance(value, dict) else value
            if choices and str(selected) not in choices:
                raise ValueError(f'{key} must use one of {choices}')
    rows = []
    for item in sizing:
        if not isinstance(item, dict) or not item.get('input') or not item.get('value'):
            raise ValueError('Sizing explanations must contain input and value')
        # Only exact supplied facts can be marked source-backed.
        status = 'Source-backed' if item.get('status') == 'Source-backed' and str(item['value']).lower() in source else 'Approximated'
        rows.append({**item, 'service': name, 'status': status})
    return config, rows


def prepare_estimated_service(owner, client, service, region):
    from .service import _json_object, _normalise_evidence, _field_contracts
    name = service['service_name']
    # Calculator names often include the standard acronym after the full
    # product name. Preserve the original display/evidence text while treating
    # these equivalent names consistently for no-direct-charge controls.
    classification_name = re.sub(r'\s*\((?:AWS\s+|Amazon\s+)?(?:IAM|VPC|IGW)\)\s*$', '', name, flags=re.I)
    normalized = _normalise_evidence(classification_name)
    context = str(service.get('_sizing_context') or '')
    bedrock = bedrock_workload(name)
    if bedrock == 'guardrails':
        return None, prepare_guardrails(owner, service, region)
    if bedrock == 'knowledge_base' and 'managed knowledge base' in normalized:
        return None, [{'field': name, 'basis': 'Calculator coverage',
                       'reason': 'Managed Knowledge Base storage and retrieval require a separate price basis'}]
    if bedrock == 'knowledge_base' and unsupported_embedding_basis(
        ' '.join([str(service.get('_bedrock_selected_design') or ''),
                  str(service.get('evidence_quote') or ''), json.dumps(service.get('usage_facts') or {})]),
    ):
        return None, [{'field': name, 'basis': 'Calculator coverage',
                       'reason': 'The selected embedding model is outside the verified Knowledge Bases calculator contract'}]
    # These controls have no separate usage line; their billable dependencies
    # (compute, storage, logs, etc.) remain separate calculator services.
    if normalized in {'aws iam', 'iam', 'aws identity and access management',
                      'amazon vpc', 'vpc', 'aws auto scaling', 'ec2 auto scaling', 'amazon ec2 auto scaling',
                      'internet gateway', 'amazon vpc internet gateway', 'aws internet gateway',
                      's3 gateway endpoint', 'dynamodb gateway endpoint', 'amazon vpc gateway endpoint'}:
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
    if normalized in {'aws iot core', 'amazon iot core', 'iot core'}:
        # The live catalog splits Core by protocol; there is no umbrella
        # product named "IoT Core". Select only a protocol in this design.
        protocol_context = service.get('_pricing_selected_design') or context
        if re.search(r'\bMQTT\b', protocol_context, re.I):
            alias = ('awsIoTCoreMqtt', 'AWS IoT Core MQTT')
        elif re.search(r'\bLoRaWAN\b', protocol_context, re.I):
            alias = ('awsIoTCoreLoRaWan', 'AWS IoT Core LoRaWAN')
        elif re.search(r'\bHTTPS?\b', protocol_context, re.I):
            alias = ('awsIoTCoreHttp', 'AWS IoT Core HTTP')
    context = str(service.get('_sizing_context') or '')
    evidence = json.dumps(service.get('usage_facts') or {})+' '+str(service.get('evidence_quote') or '')
    if normalized in {'rds', 'amazon rds', 'aws rds'}:
        engines = {'postgresql': ('postgres(?:ql)?', 'amazonRDSPostgreSQLDB'),
                   'mysql': ('mysql', 'amazonRDSMySQLDB'), 'mariadb': ('mariadb', 'amazonRDSMariaDB'),
                   'oracle': ('oracle', 'amazonRdsForOracle'), 'sql server': ('sql[ -]*server', 'amazonRDSForSQLServer')}
        facts = service.get('usage_facts') or {}
        explicit = ' '.join(str(facts.get(k) or '') for k in ('target_engine','engine','db_engine','database_engine'))
        # The source system can use a different engine. Prefer service-specific
        # facts, then its evidence, and only explicit RDS product names in context.
        for text, attached in ((explicit,False),(str(service.get('evidence_quote') or ''),False),(context,True)):
            matches = [(engine,code) for engine,(pattern,code) in engines.items()
                       if re.search((r'\bRDS\s+(?:for\s+)?' if attached else r'\b')+pattern+r'\b',text,re.I)]
            if matches:
                if len(matches)==1: alias = (matches[0][1], 'Amazon RDS for '+matches[0][0])
                break  # Conflicting explicit evidence must be resolved, not overridden by broad context.
    if not alias and re.search('load.?balanc',name,re.I) and re.search(r'\bALB\b|Application Load Balancer',context,re.I):
        alias = owner._calculator_service_code('Application Load Balancer')
    if not alias and normalized in {'amazon elastic container service','amazon ecs','aws ecs'} and 'fargate' in context.lower():
        alias = ('awsFargate','AWS Fargate')
    if alias:
        code = alias[0]
    else:
        hits = client.call('search_services', {'query':re.sub(r'^(AWS|Amazon)\s+', '', name, flags=re.I),'partition':'aws'})
        # The catalog calls its backup-only product "RDS". It must never win
        # an exact-name match when the selected service is the database itself.
        if normalized in {'rds', 'amazon rds', 'aws rds'} and isinstance(hits, list):
            hits = [h for h in hits if 'backup' not in str(h.get('key', '')).lower()]
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
    separate_kb = bool(service.get('_separate_bedrock_kb'))
    if code == 'amazon':
        fields = bedrock_calculator_fields(fields, bedrock, separate_kb)
    # Keep optional products visible: sizing is allowed to infer audit usage
    # from the full architecture, not just the extractor's narrow quote.
    feedback = service.get('_calculator_feedback', '')
    ec2_resources = service.get('_ec2_resources') if code == EC2_CODE else None
    contracts = _field_contracts(fields)
    source = (context + ' ' + evidence).lower()
    sizing_shape = '''Return JSON {"config":{...},"sizing":[{"input":"brief sizing input","value":"value with units",
"status":"Approximated or Source-backed","reason":"brief rationale"}]}.
Every estimated rate-driving choice must have a sizing explanation. Combine related choices into 4-8 concise rows.'''
    if ec2_resources:
        sizing_shape = '''Return JSON {"configurations":[{"instance":"unique human-readable role name",
"resource_ids":["exact selected resource id"],"monthly_hours":number,"config":{...},
"sizing":[{"input":"brief sizing input","value":"value with units","status":"Approximated or Source-backed",
"reason":"brief rationale"}]}]}. Return ALL configurations even on repair.
Cover every selected EC2 resource ID exactly once. Use one configuration per distinct lifecycle/role.
Group identical replicas with the same role and runtime when their host and storage sizing are shared.
Set config.workload to the actual concurrent instance count (a scalar or consistent workload envelope).
For each configuration give monthly_hours per instance (greater than 0 and at most 730). The service
will convert hours into calculator utilization; do not include utilization in config. Estimate missing runtime
from the role and schedule, including rehearsal and repeated runs when warranted. Use 730 hours if the role
and schedule justify continuous operation. Include exactly one sizing row with input "Monthly runtime", value
"<same monthly_hours> hours/month", and a nonempty reason explaining the duty cycle. Mark inferred hours
Approximated. To mark hours Source-backed, add evidence_quote quoting the BRD sentence with the role name
and exact monthly hours. Modeled or calculated hours remain Approximated.
Model storage independently for every configuration, including root disks of part-time hosts. Give the per-instance
EBS capacity in the applicable calculator field and explain capacity and retention in a storage or EBS sizing row.
Treat storage retained between runs as billable for the month even when compute is stopped. Mark inferred sizing
and runtime Approximated. Explain every rate-driving choice in a few concise sizing rows per configuration.'''
    elif bedrock == 'knowledge_base':
        sizing_shape += '''
Price the selected self-managed Knowledge Base's text embeddings in-region. If no model was specified, assume Titan Text Embeddings V2.
Use the same Titan model in modelSelection and selectedEmbeddingModel. Include both ingestion/reindexing and query embedding tokens
in documentsPerMonth and averageTokensPerDocument, using a weighted average or equivalent text inputs. Explain the two workload drivers.
Foundation model response generation and external vector storage are priced by their own services.'''
    elif bedrock == 'inference' and separate_kb:
        sizing_shape += '''
Price only foundation-model inference here. A separate Knowledge Bases configuration covers embeddings. For standard on-demand
text, use the matching modelSelection, selectedModel, and selectedModel_od IDs for the active route and positive request/token quantities.
Use imageInput and withPromptCaching set to the explicit No selector unless the design includes those features.'''
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
Keep reasons under 12 words. Do not list unused zero-cost optional features or repeat the selected region.
Do not add unrelated products. Empty config and empty sizing are invalid.
''' + sizing_shape + '\n' + json.dumps({'service':name,'region':region,'source_facts':service.get('usage_facts'),
                'BRD':context,'live_contract':fields,'repair_feedback':feedback,
                **({'selected_ec2_resources': ec2_resources} if ec2_resources else {})},default=str)
            result=owner.llm.generate(prompt,task='analysis',max_tokens=10000,temperature=0,
                call_name=f'AWS Pricing Estimated Fields - {name}')
            mapped=_json_object(result.text)
            if ec2_resources:
                entries, rows, coverage = map_ec2_configurations(
                    mapped, ec2_resources,
                    lambda item: _validated_config_and_sizing(item, contracts, name, source), region,
                    service.get('_ec2_runtime_source') or '',
                )
                service.update(_calculator_entries=entries, _calculator_fields=fields,
                               _sizing_details=rows, _resource_coverage=coverage)
                return entries, []
            config, rows = _validated_config_and_sizing(mapped, contracts, name, source)
            if code == 'amazon':
                validate_bedrock_calculator(config, contracts, bedrock, separate_kb)
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
            entry = {'service':code,'instance':name[:48],'config':config}
            service['_calculator_entries'] = [entry]
            return entry, []
        except Exception as exc:
            feedback=str(exc)
            print(f'[PRICING][SIZING-RETRY] {name} attempt={attempt+1}: {feedback}',flush=True)
    return None,[{'field':name,'reason':feedback,'basis':'Estimated sizing failed validation after one retry'}]
