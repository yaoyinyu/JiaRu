param(
    [Parameter(Mandatory = $true)][string]$ShardReport,
    [string]$Output,
    [string]$VerifyReport
)

$ErrorActionPreference = 'Stop'

function Read-BoundJson([string]$Path, [string]$Hash) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "缺少绑定报告：$Path" }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash) {
        throw "绑定报告哈希漂移：$Path"
    }
    return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable
}

$shardHash = '97da8ed76288b0e2887f352a232dfa92ea0fc3a19c427e38554499df18d8efe7'
$priorHash = 'b588fa24b3cefd6d30f97e531a956bf47a6f9e99b7cf27f0c6ebb87484beaf04'
$secondHash = '586f90e9291572a9c28a9fec27745de12b03b67f188bf79361d132bc01091951'
$shard = Read-BoundJson $ShardReport $shardHash
$priorPath = 'model/reviews/cycle016-shard001-reviewed-subset-v1.json'
$secondPath = 'model/reviews/cycle016-shard001-source-second-review-v1.json'
$prior = Read-BoundJson $priorPath $priorHash
$second = Read-BoundJson $secondPath $secondHash
if ($shard.ok -ne $true -or $shard.shard.shard -ne 1 -or $shard.shard.sourceImages -ne 20 -or
    $shard.shard.roiInstances -ne 116 -or @($shard.sourceImages).Count -ne 20 -or
    $prior.evidenceOk -ne $true -or $prior.counts.originalResolutionVisualAcceptedSourceImages -ne 4 -or
    $prior.counts.originalResolutionVisualAcceptedNails -ne 24 -or
    $second.evidenceOk -ne $true -or $second.counts.sourceExcludePartialNail -ne 6 -or
    $second.counts.returnToEveryNailReview -ne 1 -or
    $second.inputs.shardReport.sha256 -ne $shardHash) { throw '上游分片、首批通过或源图二审合同漂移' }

$newReportHashes = [ordered]@{
    '007' = '41928aea9fb27071b5d6e69b1ff95540ce49ae00d36050dea2e48c6f150a3b8a'
    '012' = '0c36cd83dac44dee72f72c87ea5176b28125d22198e627c746e872eb91fba2db'
    '014' = 'cedf5905c2b7d244619092f367c20712c94142ceb4f169c37bfb3facf67981b1'
}
$accepted = @()
$newBindings = @()
foreach ($row in $prior.reviewedSources) {
    $ordinal = [int]$row.sourceOrdinal
    $s = $shard.sourceImages[$ordinal - 1]
    if ($s.ordinal -ne $ordinal -or $row.sourceFileName -ne $s.sourceFileName -or
        $row.sourceGroup -ne $s.sourceGroup -or $row.acceptedNails -ne @($s.nails).Count -or
        $row.sourceImageSha256 -ne $s.sourceImage.sha256 -or $row.sourceLabelSha256 -ne $s.sourceLabel.sha256) {
        throw "首批通过源图身份漂移：$ordinal"
    }
    $accepted += $row
}
foreach ($ordinal in @(7,12,14)) {
    $key = '{0:d3}' -f $ordinal
    $path = "model/reviews/cycle016-shard001-source$key-visual-audit-v1.json"
    $report = Read-BoundJson $path $newReportHashes[$key]
    $s = $shard.sourceImages[$ordinal - 1]
    if ($report.evidenceOk -ne $true -or
        $report.decision -ne 'one_source_visual_and_polygon_pass_full_split_still_prohibited' -or
        $report.source.ordinal -ne $ordinal -or $report.source.fileName -ne $s.sourceFileName -or
        $report.source.sourceGroup -ne $s.sourceGroup -or
        $report.source.sourceImage.sha256 -ne $s.sourceImage.sha256 -or
        $report.source.sourceLabel.sha256 -ne $s.sourceLabel.sha256 -or
        $report.counts.originalResolutionVisualAcceptedNails -ne @($s.nails).Count -or
        $report.counts.polygonLegal -ne @($s.nails).Count -or
        $report.counts.pairwiseZeroOverlap -ne (@($s.nails).Count * (@($s.nails).Count - 1) / 2) -or
        $report.scope.trainingUse -ne 'prohibited_until_full_train_split_review_and_new_materialization') {
        throw "新增单图通过报告合同漂移：$ordinal"
    }
    foreach ($binding in @($report.inputs.sourceScript, $report.inputs.visualDecisions)) {
        if (-not (Test-Path -LiteralPath $binding.path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $binding.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $binding.sha256) {
            throw "新增单图审核脚本或决策漂移：$ordinal"
        }
    }
    $newBindings += [ordered]@{ path = (Resolve-Path -LiteralPath $path).Path; sha256 = $newReportHashes[$key] }
    $accepted += [ordered]@{
        sourceOrdinal = $ordinal
        sourceFileName = $s.sourceFileName
        sourceGroup = $s.sourceGroup
        acceptedNails = $report.counts.originalResolutionVisualAcceptedNails
        sourceImageSha256 = $s.sourceImage.sha256
        sourceLabelSha256 = $s.sourceLabel.sha256
    }
}
$excluded = @()
foreach ($row in $second.sourceDecisions | Where-Object { $_.decision -eq 'source_exclude_partial_nail' }) {
    $ordinal = [int]$row.ordinal
    $s = $shard.sourceImages[$ordinal - 1]
    if ($s.ordinal -ne $ordinal -or $row.sourceFileName -ne $s.sourceFileName -or
        $row.sourceGroup -ne $s.sourceGroup -or $row.nailCount -ne @($s.nails).Count -or
        $row.trainingUse -ne 'prohibited') { throw "二审排除源图身份漂移：$ordinal" }
    $excluded += [ordered]@{ sourceOrdinal = $ordinal; oldLabelNails = $row.nailCount; reason = $row.reason }
}
$previousExclude = $shard.sourceImages[15]
if ($previousExclude.ordinal -ne 16 -or @($previousExclude.nails).Count -ne 5) {
    throw '既有序号16裁边排除身份漂移'
}
$excluded += [ordered]@{ sourceOrdinal = 16; oldLabelNails = 5; reason = '既有绑定视觉报告确认源图顶部甲面被画面裁断' }
$acceptedOrdinals = @($accepted | ForEach-Object { [int]$_.sourceOrdinal })
$excludedOrdinals = @($excluded | ForEach-Object { [int]$_.sourceOrdinal })
if (@($acceptedOrdinals + $excludedOrdinals | Sort-Object -Unique).Count -ne 14 -or
    @($accepted | ForEach-Object { $_.sourceGroup } | Sort-Object -Unique).Count -ne 7) {
    throw '通过/排除源图交叠或来源组重复'
}
$pending = @($shard.sourceImages | Where-Object { $_.ordinal -notin $acceptedOrdinals -and $_.ordinal -notin $excludedOrdinals } |
    ForEach-Object { [ordered]@{ sourceOrdinal = $_.ordinal; sourceFileName = $_.sourceFileName; oldLabelNails = @($_.nails).Count } })
$acceptedNails = 0
foreach ($row in $accepted) { $acceptedNails += [int]$row.acceptedNails }
$excludedNails = 0
foreach ($row in $excluded) { $excludedNails += [int]$row.oldLabelNails }
$pendingNails = 0
foreach ($row in $pending) { $pendingNails += [int]$row.oldLabelNails }
if (@($accepted).Count -ne 7 -or $acceptedNails -ne 39 -or
    @($excluded).Count -ne 7 -or $excludedNails -ne 40 -or
    @($pending).Count -ne 6 -or $pendingNails -ne 37 -or
    $acceptedNails + $excludedNails + $pendingNails -ne 116) {
    throw "分片数量守恒或预期审核分布漂移：accepted=$(@($accepted).Count)/$acceptedNails excluded=$(@($excluded).Count)/$excludedNails pending=$(@($pending).Count)/$pendingNails"
}
$result = [ordered]@{
    schemaVersion = 2
    evidenceOk = $true
    decision = 'seven_visual_pass_seven_source_exclude_six_pending_no_training'
    inputs = [ordered]@{
        sourceScript = [ordered]@{ path = $PSCommandPath; sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() }
        shardReport = [ordered]@{ path = (Resolve-Path -LiteralPath $ShardReport).Path; sha256 = $shardHash }
        priorVisualSubset = [ordered]@{ path = (Resolve-Path -LiteralPath $priorPath).Path; sha256 = $priorHash }
        sourceSecondReview = [ordered]@{ path = (Resolve-Path -LiteralPath $secondPath).Path; sha256 = $secondHash }
        newVisualReports = $newBindings
    }
    counts = [ordered]@{
        shardSourceImages = 20
        shardOldLabelNails = 116
        visualAcceptedSourceImages = 7
        visualAcceptedNails = $acceptedNails
        sourceExcludedImages = 7
        sourceExcludedOldLabelNails = $excludedNails
        pendingSourceImages = 6
        pendingOldLabelNails = $pendingNails
        newlyTrainingApprovedImages = 0
    }
    acceptedSources = @($accepted | Sort-Object sourceOrdinal)
    excludedSources = @($excluded | Sort-Object sourceOrdinal)
    pendingSources = $pending
    scope = [ordered]@{
        ordinal8MultipleMaskRework = 'pending_independent_original_resolution_repair'
        ordinal7WatermarkAblation = 'pending_before_training'
        fullShardEveryNailReviewComplete = $false
        fullTrainSplitApproved = $false
        trainingUse = 'prohibited_until_full_train_split_review_and_new_materialization'
        historicalMetricsAndFailures = 'unchanged'
        protectedTestOrHoldoutUsedForSelection = $false
    }
}
$json = $result | ConvertTo-Json -Depth 100
if ($VerifyReport) {
    if (-not (Test-Path -LiteralPath $VerifyReport -PathType Leaf)) { throw "缺少待验报告：$VerifyReport" }
    if ((Get-Content -LiteralPath $VerifyReport -Raw -Encoding UTF8).TrimEnd() -cne $json.TrimEnd()) {
        throw '分片001视觉审核汇总v2重放不一致'
    }
    Write-Output 'verified_seven_visual_pass_seven_source_exclude_six_pending_no_training'
} else {
    if (-not $Output) { throw '必须提供-Output或-VerifyReport' }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null
    Set-Content -LiteralPath $Output -Value $json -Encoding UTF8
    Write-Output 'seven_visual_pass_seven_source_exclude_six_pending_no_training'
}
