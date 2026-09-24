param(
    [Parameter(Mandatory = $true)][string]$TriageReport,
    [string]$Output,
    [string]$VerifyReport
)

$ErrorActionPreference = 'Stop'

function Read-BoundJson([string]$Path, [string]$ExpectedHash) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "缺少绑定报告：$Path" }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedHash) { throw "报告哈希漂移：$Path" }
    return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable
}

function Check-Binding($Binding) {
    if (-not (Test-Path -LiteralPath $Binding.path -PathType Leaf)) { throw "缺少绑定文件：$($Binding.path)" }
    $actual = (Get-FileHash -LiteralPath $Binding.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Binding.sha256.ToLowerInvariant()) { throw "文件哈希漂移：$($Binding.path)" }
}

$triageHash = 'fd89cb8bf3f59da09a7c700ae0280ac03ffb1043f58910f0a2a0a716804a3cee'
$triage = Read-BoundJson $TriageReport $triageHash
if ($triage.evidenceOk -ne $true -or $triage.counts.reviewedSourceOverviews -ne 20 -or
    $triage.counts.boundNativeOverlays -ne 116 -or
    $triage.counts.statuses.needs_second_source_review -ne 7 -or
    @($triage.sourceTriage).Count -ne 20) { throw '初筛报告合同漂移' }
$shard = Read-BoundJson $triage.inputs.shardReport.path $triage.inputs.shardReport.sha256
if ($shard.ok -ne $true -or $shard.shard.shard -ne 1 -or
    $shard.shard.sourceImages -ne 20 -or $shard.shard.roiInstances -ne 116) {
    throw '分片报告合同漂移'
}

# 原图及焦点叠加图均已按原像素检查；只有完整甲面可确认时才回到逐甲队列。
$manual = @{
    3 = @('return_to_every_nail_review', '原图与第1枚原像素叠加图显示甲根、两侧与甲尖可见；织物紧邻但未遮盖该枚甲面。仍须审核本图全部5甲。', 1)
    4 = @('source_exclude_partial_nail', '第5枚拇指仅露出狭窄侧面，完整甲面宽度与近端边界不可确认；整图排除。', 5)
    6 = @('source_exclude_partial_nail', '第9枚只见拇指弯曲侧缘的彩色窄带，完整甲面主体不可见；整图排除。', 9)
    9 = @('source_exclude_partial_nail', '第5枚仅见指尖上缘极薄彩色侧面，完整甲面与甲根不可确认；整图排除。', 5)
    11 = @('source_exclude_partial_nail', '第5枚左侧甲面被相邻手指遮挡，仅有不规则局部露出；整图排除。', 5)
    13 = @('source_exclude_partial_nail', '第5枚顶部甲面只呈狭窄侧视窄条，完整甲面主体及近端边界不可确认；整图排除。', 5)
    15 = @('source_exclude_partial_nail', '第5枚左侧拇指仅有边缘窄条可见，甲面主体朝向画面外；整图排除。', 5)
}

$rows = @()
foreach ($ordinal in @(3,4,6,9,11,13,15)) {
    $old = @($triage.sourceTriage | Where-Object { $_.ordinal -eq $ordinal })
    $source = @($shard.sourceImages | Where-Object { $_.ordinal -eq $ordinal })
    if ($old.Count -ne 1 -or $source.Count -ne 1 -or
        $old[0].decision -ne 'needs_second_source_review' -or
        $old[0].sourceFileName -ne $source[0].sourceFileName -or
        $old[0].sourceGroup -ne $source[0].sourceGroup -or
        $old[0].sourceImage.sha256 -ne $source[0].sourceImage.sha256) {
        throw "二审源图身份漂移：$ordinal"
    }
    $focus = $manual[$ordinal][2]
    if (@($old[0].focusTruthIndices).Count -ne 1 -or $old[0].focusTruthIndices[0] -ne $focus) {
        throw "初审焦点序号漂移：$ordinal"
    }
    $nail = @($source[0].nails | Where-Object { $_.truthIndex -eq $focus })
    if ($nail.Count -ne 1) { throw "缺少焦点甲面：$ordinal/$focus" }
    foreach ($binding in @($source[0].sourceImage, $source[0].sourceLabel, $source[0].overview, $nail[0].nativeOverlay)) {
        Check-Binding $binding
    }
    $rows += [ordered]@{
        ordinal = $ordinal
        sourceFileName = $source[0].sourceFileName
        sourceGroup = $source[0].sourceGroup
        sourceImage = $source[0].sourceImage
        sourceLabel = $source[0].sourceLabel
        overview = $source[0].overview
        focusTruthIndex = $focus
        focusNativeOverlay = $nail[0].nativeOverlay
        nailCount = @($source[0].nails).Count
        decision = $manual[$ordinal][0]
        reason = $manual[$ordinal][1]
        everyNailVisualApproval = $false
        trainingUse = 'prohibited'
    }
}
if (@($rows | Where-Object { $_.decision -eq 'source_exclude_partial_nail' }).Count -ne 6 -or
    @($rows | Where-Object { $_.decision -eq 'return_to_every_nail_review' }).Count -ne 1) {
    throw '二审分布漂移'
}
$result = [ordered]@{
    schemaVersion = 1
    evidenceOk = $true
    decision = 'second_source_review_six_excluded_one_pending_every_nail'
    inputs = [ordered]@{
        sourceScript = [ordered]@{ path = $PSCommandPath; sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() }
        sourceTriage = [ordered]@{ path = (Resolve-Path -LiteralPath $TriageReport).Path; sha256 = $triageHash }
        shardReport = $triage.inputs.shardReport
    }
    counts = [ordered]@{
        secondReviewedSourceImages = 7
        sourceExcludePartialNail = 6
        returnToEveryNailReview = 1
        newlyVisualApprovedSourceImages = 0
        newlyTrainingApprovedSourceImages = 0
    }
    sourceDecisions = $rows
    scope = [ordered]@{
        existingSourceExcludeOrdinal16 = 'unchanged'
        existingLabelReworkOrdinal8 = 'unchanged'
        existingFourSourceTwentyFourNailVisualPass = 'unchanged'
        historicalTrainingSnapshotAndFailures = 'unchanged'
        protectedRoleUsedForSelection = $false
        fullShardEveryNailReviewComplete = $false
        fullTrainSplitApproved = $false
    }
}
$json = $result | ConvertTo-Json -Depth 100
if ($VerifyReport) {
    if (-not (Test-Path -LiteralPath $VerifyReport -PathType Leaf)) { throw "缺少待验报告：$VerifyReport" }
    $recorded = (Get-Content -LiteralPath $VerifyReport -Raw -Encoding UTF8).TrimEnd()
    if ($recorded -cne $json.TrimEnd()) { throw '源图二审报告重放不一致' }
    Write-Output 'verified_second_source_review_six_excluded_one_pending_every_nail'
} else {
    if (-not $Output) { throw '必须提供-Output或-VerifyReport' }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null
    Set-Content -LiteralPath $Output -Value $json -Encoding utf8
    Write-Output 'second_source_review_six_excluded_one_pending_every_nail'
}
