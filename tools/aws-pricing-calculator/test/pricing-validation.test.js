const test=require('node:test');
const assert=require('node:assert/strict');
const {validateFieldValue}=require('../lib/lint/validation');
const {loadCatalog}=require('../lib/lint/catalog');
const path=require('node:path');

test('inactive NAT fields accept zero without allowing zero active capacity',()=>{
  const field={id:'regionalNatGatewayCount',type:'numericInput',minValue:1,validations:{minValue:1}};
  const opts={serviceCode:'networkAddressTranslationNatGatewayVpc',config:{numberOfGateways:'2'}};
  assert.equal(validateFieldValue(field,'0',opts).ok,true);
  assert.equal(validateFieldValue(field,'0',{...opts,config:{numberOfGateways:'0'}}).ok,false);
  assert.equal(validateFieldValue(field,'-1',opts).ok,false);
});
test('current Cognito and CloudTrail form defaults retain explicit template and units',()=>{
  const c=loadCatalog(path.join(__dirname,'../catalog/services'));
  assert.equal(c.get('amazonCognito').templateId,'CognitoEssentials');
  assert.deepEqual(c.get('amazonCognito').defaultFields,{optimizationRateTokenRequests:'0',optimizationRateAppClients:'0'});
  assert.equal(c.get('awsCloudTrail').defaultFields.dataOpsMult,'1');
});
