Set-Location "E:\AI Project\ClaudeCode\JiaRu"
node node_modules/eslint/bin/eslint.js . 2>&1 | Out-File -FilePath "$env:TEMP\eslint-out2.txt" -Encoding utf8
Write-Host "Exit: $LASTEXITCODE"
