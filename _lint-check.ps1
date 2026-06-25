Set-Location "E:\AI Project\ClaudeCode\JiaRu"
npx eslint . 2>&1 | Out-File -FilePath "$env:TEMP\eslint-out.txt" -Encoding utf8
Write-Host "Exit: $LASTEXITCODE"
