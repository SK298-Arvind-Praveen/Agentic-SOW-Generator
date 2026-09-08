$ErrorActionPreference = "Stop"

$runtimeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $runtimeRoot
try {
    npm ci
    npx playwright install chromium
    npx esbuild ./mcp-server.js --bundle --platform=node `
        --outfile=./dist/mcp-server.js --format=cjs --minify `
        --external:@aws-sdk/client-dynamodb --external:@aws-sdk/lib-dynamodb
    Write-Host "AWS Pricing Calculator runtime is ready."
}
finally {
    Pop-Location
}
