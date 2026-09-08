const { fetchCostFromDOM } = require('../lib/dom-cost');

const url = process.argv[2];
if (!url || !/^https:\/\/(?:calculator\.aws|pricing\.calculator\.aws\.eu)\//.test(url)) {
  process.stderr.write('A valid AWS Pricing Calculator URL is required.\n');
  process.exit(2);
}

fetchCostFromDOM(url)
  .then(result => {
    process.stdout.write(JSON.stringify({
      monthlyCost: result.monthlyCost,
      monthlyByService: Object.fromEntries(result.monthlyByService),
      configByService: Object.fromEntries(result.configByService),
    }));
  })
  .catch(error => {
    process.stderr.write(String(error && error.message || error));
    process.exit(1);
  });
