const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const aws = require('../lib/aws/aws-client');
const { loadCatalog } = require('../lib/lint/catalog');
const { canRehydrate } = require('../lib/lint/can-rehydrate');
// Public AWS calculator definition captured 2026-11-18. Network boundaries
// are replaced; field extraction, entry validation, builder and lint stay real.
const definition = require('./opensearch-definition.json');
const code = 'amazonElasticsearchService';
const manifest = new Map([[code, { key: code, name: 'Amazon OpenSearch Service' }]]);
aws.loadManifest = async () => manifest;
aws.loadRegionList = async () => ({ [code]: ['ap-south-1'] });
aws.fetchServiceDefinition = async () => definition;
aws.enrichFieldsWithMetadata = async (_definition, fields) => fields;
const EstimateBuilder = require('../lib/aws/estimate-builder');
const { createHandlerHelpers } = require('../lib/mcp/handler-helpers');
const catalog = loadCatalog(path.join(__dirname, '../catalog/services'));
const helpers = createHandlerHelpers({ catalog });
const serverless = {
  region: 'ap-south-1',
  How_many_Indexing_OCUs: '1',
  How_many_Search_and_Query_OCUs: '1',
  How_big_is_the_index_data: { value: '1', unit: 'gb|NA' },
};

function lint(blob) {
  return canRehydrate({ savedBlob: blob, manifest,
    perServiceDefinitions: new Map([[code, definition]]), catalog });
}

test('serverless OpenSearch saves its OCU template without provisioned requirements', async () => {
  const estimate = new EstimateBuilder('Serverless replay', 'aws');
  const result = await helpers.addEntries(estimate, [{ service: code, config: serverless }]);
  assert.equal(result[0].success, true);
  assert.equal(result[0].partial, undefined, JSON.stringify(result));
  const blob = await estimate.toAWSPayload();
  const saved = Object.values(blob.services)[0];
  assert.equal(saved.estimateFor, 'elasticSearchService-serverlesss');
  assert.deepEqual(saved.calculationComponents.How_big_is_the_index_data, { value: '1', unit: 'gb|NA' });
  assert.equal(saved.calculationComponents.numberOfInstances, undefined);
  assert.equal(lint(blob).status, 'editable', JSON.stringify(lint(blob)));
});

test('OpenSearch ingestion selects its separate OCU template', async () => {
  const estimate = new EstimateBuilder('Ingestion', 'aws');
  const result = await helpers.addEntries(estimate, [{ service: code,
    config: { region: 'ap-south-1', How_many_Ingestion_OCUs: '2' } }]);
  assert.equal(result[0].partial, undefined, JSON.stringify(result));
  const blob = await estimate.toAWSPayload();
  assert.equal(Object.values(blob.services)[0].estimateFor, 'elasticSearchService-serverlesss-Ingestion');
  assert.equal(lint(blob).status, 'editable', JSON.stringify(lint(blob)));
});

test('provisioned OpenSearch still requires catalog storage inputs', async () => {
  const estimate = new EstimateBuilder('Provisioned missing storage', 'aws');
  const result = await helpers.addEntries(estimate, [{ service: code,
    config: { region: 'ap-south-1', columnFormIPM_1: { value: [] } } }]);
  assert.equal(result[0].partial, true);
  assert.ok(result[0].missing_required_fields.includes('numberOfInstances'));
  assert.ok(result[0].missing_required_fields.includes('storageType'));
  assert.equal(lint(await estimate.toAWSPayload()).status, 'required-input');
});

test('mixed OpenSearch templates are rejected before repair can add phantom nodes', async () => {
  const estimate = new EstimateBuilder('Mixed templates', 'aws');
  const result = await helpers.addEntries(estimate, [{ service: code,
    config: { ...serverless, numberOfInstances: '1', storageType: 'GP3' } }]);
  assert.match(result[0].error || '', /incompatible templates/i);
  assert.equal(Object.keys(estimate.services).length, 0);
});

test('catalog defaults for provisioned OpenSearch never enter serverless config', async () => {
  const scopedCatalog = new Map(catalog);
  scopedCatalog.set(code, { ...catalog.get(code), defaultFields: { numberOfInstances: '1' } });
  const estimate = new EstimateBuilder('Template defaults', 'aws');
  await createHandlerHelpers({ catalog: scopedCatalog }).addEntries(estimate,
    [{ service: code, config: serverless }]);
  const saved = Object.values((await estimate.toAWSPayload()).services)[0];
  assert.equal(saved.calculationComponents.numberOfInstances, undefined);
});

test('catalog hint still chooses among templates accepting the same fields', () => {
  const shared = { type: 'numericInput', id: 'requests' };
  const def = { templates: [
    { id: 'basic', cards: [{ inputSection: { components: [shared] } }] },
    { id: 'essentials', cards: [{ inputSection: { components: [shared] } }] },
  ] };
  assert.equal(new EstimateBuilder()._inferTemplateId(def, { requests: '50' }, 'essentials'), 'essentials');
});
