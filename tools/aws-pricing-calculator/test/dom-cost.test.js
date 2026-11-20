const assert = require('node:assert/strict');
const test = require('node:test');
const { summarizeDetailedRows } = require('../lib/dom-cost');

test('retains each EC2 configuration summary while keeping the service subtotal', () => {
  const { monthlyByService, configByService } = summarizeDetailedRows([
    ['Amazon EC2', '0.00 USD', '80.00 USD', 'App nodes', 'Mumbai', '2 m6i.large'],
    ['Amazon EC2', '0.00 USD', '12.00 USD', 'Migration runner', 'Mumbai', '1 m6i.large'],
    ['Amazon EC2', '0.00 USD', '8.00 USD', 'Load generator', 'Mumbai', '1 t3.medium'],
    ['AWS Lambda', '0.00 USD', '5.00 USD', 'Lambda', 'Mumbai', '800 requests'],
  ]);
  assert.equal(monthlyByService.get('Amazon EC2'), 100);
  assert.equal(configByService.get('Amazon EC2'), 'App nodes: 2 m6i.large\nMigration runner: 1 m6i.large\nLoad generator: 1 t3.medium');
  assert.equal(configByService.get('AWS Lambda'), '800 requests');
});
