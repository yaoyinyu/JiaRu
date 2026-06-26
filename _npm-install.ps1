$ErrorActionPreference = "Continue"
Set-Location "E:\AI Project\ClaudeCode\JiaRu"
& npm install *>&1 | ForEach-Object { $_.ToString() } | Out-File "$env:TEMP\npm-install.txt" -Encoding utf8
Write-Host "Exit: $LASTEXITCODE"
