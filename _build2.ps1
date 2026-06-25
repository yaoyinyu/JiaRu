Set-Location "E:\AI Project\ClaudeCode\JiaRu"
node node_modules/next/dist/bin/next build 2>&1 | Out-File -FilePath "$env:TEMP\next-build2.txt" -Encoding utf8
Write-Host "Exit: $LASTEXITCODE"
