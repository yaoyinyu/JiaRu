param(
  [Parameter(Mandatory = $true)][string]$ImagePath,
  [Parameter(Mandatory = $true)][string]$OutputPath,
  [string]$Url = "http://localhost:3000/ar-tryon",
  [string]$Session = "nail-memory",
  [int]$Samples = 20,
  [int]$SettleMilliseconds = 400
)

$ErrorActionPreference = "Stop"
if ($Samples -lt 1) { throw "Samples must be positive" }
$resolvedImage = (Resolve-Path -LiteralPath $ImagePath).Path
$resolvedOutput = [IO.Path]::GetFullPath($OutputPath)
$outputDirectory = [IO.Path]::GetDirectoryName($resolvedOutput)
[IO.Directory]::CreateDirectory($outputDirectory) | Out-Null

$cli = @("--yes", "--package", "@playwright/cli", "playwright-cli", "--session", $Session)

function Invoke-PlaywrightCli([string[]]$Arguments) {
  $output = & npx.cmd @cli @Arguments 2>&1 | Out-String
  if ($LASTEXITCODE -ne 0) { throw "playwright-cli failed: $output" }
  return $output
}

function Get-LatestSnapshotText {
  return Invoke-PlaywrightCli @("snapshot")
}

function Get-BrowserMemory {
  $processes = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match "^(chrome|msedge)\.exe$" -and
    $_.CommandLine -match "(ms-playwright|playwright)"
  }
  $workingSet = 0L
  $privateBytes = 0L
  foreach ($item in $processes) {
    $process = Get-Process -Id $item.ProcessId -ErrorAction SilentlyContinue
    if ($process) {
      $workingSet += $process.WorkingSet64
      $privateBytes += $process.PrivateMemorySize64
    }
  }
  return @{
    processCount = @($processes).Count
    workingSetBytes = $workingSet
    privateBytes = $privateBytes
  }
}

function Parse-PageMemory([string]$Output) {
  $match = [regex]::Match(
    $Output,
    'usedJSHeapSize\\?"?:\s*(\d+).*?totalJSHeapSize\\?"?:\s*(\d+).*?jsHeapSizeLimit\\?"?:\s*(\d+)',
    [Text.RegularExpressions.RegexOptions]::Singleline
  )
  if (-not $match.Success) { throw "could not parse performance.memory: $Output" }
  return @{
    usedJSHeapBytes = [int64]$match.Groups[1].Value
    totalJSHeapBytes = [int64]$match.Groups[2].Value
    jsHeapLimitBytes = [int64]$match.Groups[3].Value
  }
}

$records = [Collections.Generic.List[object]]::new()
try {
  Invoke-PlaywrightCli @("open", $Url) | Out-Null
  $snapshot = Get-LatestSnapshotText
  $modeButtons = [regex]::Matches($snapshot, 'button "[^"]+" \[ref=(e\d+)\]')
  $textureRef = if ($modeButtons.Count -ge 3) { $modeButtons[2].Groups[1].Value } else { "" }
  if (-not $textureRef) { throw "texture mode button not found" }
  Invoke-PlaywrightCli @("click", $textureRef) | Out-Null

  for ($iteration = 1; $iteration -le $Samples; $iteration++) {
    $snapshot = Get-LatestSnapshotText
    $uploadControls = [regex]::Matches($snapshot, 'generic \[ref=(e\d+)\] \[cursor=pointer\]:')
    $uploadRef = if ($uploadControls.Count -gt 0) {
      $uploadControls[$uploadControls.Count - 1].Groups[1].Value
    } else { "" }
    if (-not $uploadRef) { throw "multi-texture upload control not found at iteration $iteration" }
    Invoke-PlaywrightCli @("click", $uploadRef) | Out-Null
    Invoke-PlaywrightCli @("upload", $resolvedImage) | Out-Null
    Start-Sleep -Milliseconds $SettleMilliseconds
    $resultSnapshot = ""
    for ($attempt = 1; $attempt -le 20; $attempt++) {
      $resultSnapshot = Get-LatestSnapshotText
      if ($resultSnapshot -match 'Model: [^"\r\n]+') { break }
      Start-Sleep -Milliseconds 250
    }
    $elapsed = [regex]::Match($resultSnapshot, 'Elapsed: (\d+) ms').Groups[1].Value
    $worker = [regex]::Match($resultSnapshot, 'Worker: (\d+) ms').Groups[1].Value
    $model = [regex]::Match($resultSnapshot, 'Model: ([^"\r\n]+)').Groups[1].Value.Trim()
    $backend = [regex]::Match($resultSnapshot, 'generic \[ref=e\d+\]: model / ([^\r\n]+)').Groups[1].Value.Trim()
    if (-not $elapsed -or -not $worker -or -not $model) {
      throw "recognition result missing at iteration $iteration"
    }

    $pageMemoryOutput = Invoke-PlaywrightCli @(
      "eval",
      "JSON.stringify({usedJSHeapSize:performance.memory.usedJSHeapSize,totalJSHeapSize:performance.memory.totalJSHeapSize,jsHeapSizeLimit:performance.memory.jsHeapSizeLimit})"
    )
    $pageMemory = Parse-PageMemory $pageMemoryOutput
    $browserMemory = Get-BrowserMemory
    $records.Add([ordered]@{
      iteration = $iteration
      elapsedMs = [double]$elapsed
      workerElapsedMs = [double]$worker
      modelVersion = $model
      backend = $backend
      usedJSHeapBytes = $pageMemory.usedJSHeapBytes
      totalJSHeapBytes = $pageMemory.totalJSHeapBytes
      jsHeapLimitBytes = $pageMemory.jsHeapLimitBytes
      browserProcessCount = $browserMemory.processCount
      browserWorkingSetBytes = $browserMemory.workingSetBytes
      browserPrivateBytes = $browserMemory.privateBytes
      recordedAt = [DateTimeOffset]::Now.ToString("o")
    })

    $closeRef = [regex]::Match($resultSnapshot, 'button "Close" \[ref=(e\d+)\]').Groups[1].Value
    if (-not $closeRef) { throw "picker close button not found at iteration $iteration" }
    Invoke-PlaywrightCli @("eval", "el => el.click()", $closeRef) | Out-Null
  }

  $report = [ordered]@{
    version = "nail-texture-recognition-memory/v1"
    profile = "desktop-chromium"
    url = $Url
    imagePath = $resolvedImage
    sampleCount = $records.Count
    samples = $records
  }
  [IO.File]::WriteAllText(
    $resolvedOutput,
    ($report | ConvertTo-Json -Depth 8),
    [Text.UTF8Encoding]::new($false)
  )
  $report | ConvertTo-Json -Depth 4
}
finally {
  try { Invoke-PlaywrightCli @("close") | Out-Null } catch { Write-Warning $_ }
}
