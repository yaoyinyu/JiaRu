param(
    [Parameter(Mandatory = $true)][string]$ShardReport,
    [Parameter(Mandatory = $true)][string]$SourceTriageReport,
    [string]$Output,
    [string]$VerifyReport
)

$ErrorActionPreference = 'Stop'

function Read-BoundJson([string]$Path, [string]$ExpectedHash) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "缺少绑定文件：$Path" }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedHash.ToLowerInvariant()) { throw "SHA-256漂移：$Path" }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -AsHashtable
}

$shardHash = '97da8ed76288b0e2887f352a232dfa92ea0fc3a19c427e38554499df18d8efe7'
$triageHash = 'fd89cb8bf3f59da09a7c700ae0280ac03ffb1043f58910f0a2a0a716804a3cee'
$shard = Read-BoundJson $ShardReport $shardHash
$triage = Read-BoundJson $SourceTriageReport $triageHash
if ($shard.shard.sourceImages -ne 20 -or $shard.shard.roiInstances -ne 116 -or
    $triage.counts.visualApprovedSourceImages -ne 0 -or $triage.counts.visualApprovedNails -ne 0) {
    throw '分片总量或初筛批准数漂移'
}
$reportHashes = [ordered]@{
    '002' = '3f47d32fa8f8f9324c14bb64af8a7b716039a5b0bf57bd2ebacfb464ae321202'
    '017' = 'dc7fb8f32898fd4f4aa40098c5c602e7b732935cb49b4911a9ab2b7fbd572820'
    '019' = 'a78055d9997d144f4cc6292844e1ef3a8696e8b184c1e4ecbb8350a38cdd9b1e'
    '020' = '57fff3b27463da9ed4cc54c725b3cec0099c673267ea4a9ef1d63107c054d1ea'
}
$rows = @()
$boundReports = @()
$groups = @()
$acceptedNails = 0
foreach ($key in $reportHashes.Keys) {
    $path = "model\reviews\cycle016-shard001-source$key-visual-audit-v1.json"
    $item = Read-BoundJson $path $reportHashes[$key]
    $sourceOrdinal = [int]$key
    $source = $shard.sourceImages[$sourceOrdinal - 1]
    if ($item.evidenceOk -ne $true -or
        $item.decision -ne 'one_source_visual_and_polygon_pass_full_split_still_prohibited' -or
        $item.source.ordinal -ne $sourceOrdinal -or
        $item.source.fileName -ne $source.sourceFileName -or
        $item.source.sourceGroup -ne $source.sourceGroup -or
        $item.inputs.shardReport.sha256 -ne $shardHash -or
        $item.inputs.sourceTriage.sha256 -ne $triageHash -or
        $item.counts.visibleNails -ne @($source.nails).Count -or
        $item.counts.originalResolutionVisualAcceptedNails -ne @($source.nails).Count -or
        $item.counts.polygonLegal -ne @($source.nails).Count -or
        $item.counts.pairwiseZeroOverlap -ne (@($source.nails).Count * (@($source.nails).Count - 1) / 2) -or
        $item.scope.trainingUse -ne 'prohibited_until_full_train_split_review_and_new_materialization' -or
        $item.scope.fullTrainSplitReviewComplete -ne $false) {
        throw "单图审核报告合同漂移：$key"
    }
    $script = $item.inputs.sourceScript
    if (-not (Test-Path -LiteralPath $script.path -PathType Leaf) -or
        (Get-FileHash -LiteralPath $script.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $script.sha256) {
        throw "审核脚本身份漂移：$key"
    }
    $groups += $source.sourceGroup
    $acceptedNails += $item.counts.originalResolutionVisualAcceptedNails
    $boundReports += [ordered]@{ path = (Resolve-Path -LiteralPath $path).Path; sha256 = $reportHashes[$key] }
    $rows += [ordered]@{
        sourceOrdinal = $sourceOrdinal
        sourceFileName = $source.sourceFileName
        sourceGroup = $source.sourceGroup
        acceptedNails = $item.counts.originalResolutionVisualAcceptedNails
        sourceImageSha256 = $source.sourceImage.sha256
        sourceLabelSha256 = $source.sourceLabel.sha256
    }
}
if (@($groups | Sort-Object -Unique).Count -ne 4 -or $acceptedNails -ne 24) {
    throw '来源组去重或批准甲面数漂移'
}
$result = [ordered]@{
    schemaVersion = 1
    evidenceOk = $true
    decision = 'four_source_visual_subset_pass_shard_and_training_still_pending'
    inputs = [ordered]@{
        sourceScript = [ordered]@{ path = $PSCommandPath; sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() }
        shardReport = [ordered]@{ path = (Resolve-Path -LiteralPath $ShardReport).Path; sha256 = $shardHash }
        sourceTriage = [ordered]@{ path = (Resolve-Path -LiteralPath $SourceTriageReport).Path; sha256 = $triageHash }
        reviewedSources = $boundReports
    }
    counts = [ordered]@{
        shardSourceImages = 20
        shardNailInstances = 116
        originalResolutionVisualAcceptedSourceImages = 4
        originalResolutionVisualAcceptedNails = $acceptedNails
        notYetVisuallyAcceptedSourceImages = 16
        notYetVisuallyAcceptedNails = 116 - $acceptedNails
        uniqueAcceptedSourceGroups = 4
        newlyTrainingApprovedImages = 0
    }
    reviewedSources = $rows
    scope = [ordered]@{
        shard001ReviewComplete = $false
        fullTrainSplitReviewComplete = $false
        trainingUse = 'prohibited_until_full_train_split_review_and_new_materialization'
        oldSnapshotAndHistoricalFailures = 'unchanged'
        protectedTestOrHoldoutUsedForSelection = $false
    }
}
$json = $result | ConvertTo-Json -Depth 100
if ($VerifyReport) {
    if (-not (Test-Path -LiteralPath $VerifyReport -PathType Leaf)) { throw "缺少待验报告：$VerifyReport" }
    if ((Get-Content -LiteralPath $VerifyReport -Raw).TrimEnd() -cne $json.TrimEnd()) {
        throw '分片部分视觉审核汇总重放不一致'
    }
    Write-Output 'verified_four_source_visual_subset_shard_pending'
} else {
    if (-not $Output) { throw '必须提供-Output或-VerifyReport' }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null
    Set-Content -LiteralPath $Output -Value $json -Encoding utf8
    Write-Output 'four_source_visual_subset_pass_shard_and_training_still_pending'
}
