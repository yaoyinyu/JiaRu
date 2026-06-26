Set-Location "E:\AI Project\ClaudeCode\JiaRu"
npm uninstall "@mediapipe/camera_utils" "@mediapipe/drawing_utils" ngrok 2>&1 | Out-File "$env:TEMP\npm-uninstall.txt" -Encoding utf8
Write-Host "Exit: $LASTEXITCODE"
