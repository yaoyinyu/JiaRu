param(
    [Parameter(Mandatory = $true)][string]$ShardReport,
    [string]$Output,
    [string]$VerifyReport
)

$ErrorActionPreference = 'Stop'

function Read-BoundJson([string]$Path, [string]$ExpectedHash) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "缺少绑定文件：$Path"
    }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedHash.ToLowerInvariant()) {
        throw "绑定文件SHA-256漂移：$Path"
    }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -AsHashtable
}

function Test-BoundFile($Binding) {
    if (-not (Test-Path -LiteralPath $Binding.path -PathType Leaf)) {
        throw "缺少证据文件：$($Binding.path)"
    }
    $actual = (Get-FileHash -LiteralPath $Binding.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Binding.sha256.ToLowerInvariant()) {
        throw "证据文件SHA-256漂移：$($Binding.path)"
    }
}

$expectedShardHash = '97da8ed76288b0e2887f352a232dfa92ea0fc3a19c427e38554499df18d8efe7'
$shard = Read-BoundJson $ShardReport $expectedShardHash
if ($shard.schemaVersion -ne 1 -or $shard.ok -ne $true -or
    $shard.decision -ne 'full_train_review_shard_pending_visual_decisions' -or
    $shard.shard.shard -ne 1 -or $shard.shard.sourceImages -ne 20 -or
    $shard.shard.roiInstances -ne 116 -or $shard.shard.sourceGroups -ne 20 -or
    @($shard.sourceImages).Count -ne 20) {
    throw '分片001报告合同漂移'
}
Test-BoundFile $shard.inputs.plan
$inventory = Read-BoundJson $shard.inputs.inventoryReport.path $shard.inputs.inventoryReport.sha256
if ($inventory.ok -ne $true -or $inventory.counts.trainSourceImages -ne 237 -or
    $inventory.counts.trainRoiInstances -ne 1428 -or $inventory.counts.reviewShards -ne 12) {
    throw '完整train盘点合同漂移'
}

$previousAuditPath = 'E:\AI Project\Codex\JiaRu_image\审核工作区\2026_9_23_cycle016_train_truth_review_v1\visual-audit-report-v1.json'
$previousAuditHash = '7f6d5e5449dcfe2bd57154127484060da5a70c207a428c40561c102da11f5399'
$previousAudit = Read-BoundJson $previousAuditPath $previousAuditHash
if ($previousAudit.evidenceOk -ne $true -or $previousAudit.trainingQualityPass -ne $false -or
    @($previousAudit.confirmed | Where-Object { $_.ordinal -eq 16 -and $_.status -eq 'source_exclude_confirmed' }).Count -ne 1) {
    throw '既有裁边源图裁决漂移'
}

# 仅记录原分辨率总览初筛，不给任何源图或mask训练批准。
$manual = @{
    1 = @('pending_every_nail_review', '总览未见确定的整图排除点；仍须逐甲查完整性、遗漏与污染。', @())
    2 = @('pending_every_nail_review', '四枚可见甲面需逐甲核边；总览不授予整图通过。', @())
    3 = @('needs_second_source_review', '左侧甲面与织物交界存在遮挡/污染疑点，需原图局部二审。', @(1))
    4 = @('needs_second_source_review', '顶部拇指甲只呈侧视窄条，需确认完整甲面是否可见。', @(5))
    5 = @('pending_every_nail_review', '双手及水印需逐甲检查，水印不得进入mask。', @())
    6 = @('needs_second_source_review', '左上侧视甲面轮廓难确认，需局部二审并核查相邻边界。', @(9))
    7 = @('pending_every_nail_review', '五甲及背景文字需逐甲复核。', @())
    8 = @('confirmed_label_rework', '第5枚拇指mask跨入皮包带并包含袋面纹理；原像素裁块可见缝线穿过mask。源图其余甲面仍待逐甲复核。', @(5))
    9 = @('needs_second_source_review', '顶部第5枚仅见极薄侧视甲面，需确认是否为应排除的局部露出甲。', @(5))
    10 = @('pending_every_nail_review', '五甲需逐甲核边及背景素材排除。', @())
    11 = @('needs_second_source_review', '最左侧第5枚只见局部甲面，需核实遮挡与源图资格。', @(5))
    12 = @('pending_every_nail_review', '低对比甲缘需逐甲复核，不能凭总览批准。', @())
    13 = @('needs_second_source_review', '顶部第5枚为侧视窄条，需核实完整甲面可见性。', @(5))
    14 = @('pending_every_nail_review', '五甲需逐甲核边。', @())
    15 = @('needs_second_source_review', '左侧拇指第5枚仅见侧视窄条，需核实完整甲面可见性。', @(5))
    16 = @('confirmed_source_exclude', '既有绑定视觉报告确认派生源图顶部甲面被画面边界裁断；整图排除，旧快照保持。', @(1, 3))
    17 = @('pending_every_nail_review', '双手十甲均需逐甲核边，不能凭总览批准。', @())
    18 = @('pending_every_nail_review', '透明低对比五甲均需逐甲核边。', @())
    19 = @('pending_every_nail_review', '延长甲及装饰需逐甲核边。', @())
    20 = @('pending_every_nail_review', '室外小目标五甲需逐甲核边。', @())
}

$rows = @()
$nailTotal = 0
for ($ordinal = 1; $ordinal -le 20; $ordinal++) {
    $source = $shard.sourceImages[$ordinal - 1]
    if ($source.ordinal -ne $ordinal -or $source.sourceFileName -ne $inventory.sourceImages[$ordinal - 1].sourceFileName) {
        throw "分片/总账序号或源图身份不一致：$ordinal"
    }
    Test-BoundFile $source.sourceImage
    Test-BoundFile $source.sourceLabel
    Test-BoundFile $source.overview
    $nails = @($source.nails)
    $nailTotal += $nails.Count
    foreach ($nail in $nails) {
        Test-BoundFile $nail.nativeOverlay
    }
    $entry = $manual[$ordinal]
    if ($null -eq $entry) { throw "缺少源图初筛决策：$ordinal" }
    foreach ($index in $entry[2]) {
        if (@($nails | Where-Object { $_.truthIndex -eq $index }).Count -ne 1) {
            throw "焦点甲面序号不存在：$ordinal/$index"
        }
    }
    $rows += [ordered]@{
        ordinal = $ordinal
        sourceFileName = $source.sourceFileName
        sourceGroup = $source.sourceGroup
        sourceImage = $source.sourceImage
        sourceLabel = $source.sourceLabel
        overview = $source.overview
        nailCount = $nails.Count
        decision = $entry[0]
        reason = $entry[1]
        focusTruthIndices = @($entry[2])
        fullSourceVisualApproval = $false
        everyNailVisualApproval = $false
    }
}
if ($nailTotal -ne 116 -or @($rows.sourceGroup | Sort-Object -Unique).Count -ne 20) {
    throw '分片实例数或来源组数漂移'
}
$counts = [ordered]@{}
foreach ($state in @('pending_every_nail_review', 'needs_second_source_review', 'confirmed_label_rework', 'confirmed_source_exclude')) {
    $counts[$state] = @($rows | Where-Object { $_.decision -eq $state }).Count
}
if ($counts.pending_every_nail_review -ne 11 -or $counts.needs_second_source_review -ne 7 -or
    $counts.confirmed_label_rework -ne 1 -or $counts.confirmed_source_exclude -ne 1) {
    throw '初筛分布漂移'
}
$result = [ordered]@{
    schemaVersion = 1
    evidenceOk = $true
    decision = 'source_overview_triage_only_pending_every_nail_review'
    inputs = [ordered]@{
        sourceScript = [ordered]@{ path = $PSCommandPath; sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() }
        shardReport = [ordered]@{ path = (Resolve-Path -LiteralPath $ShardReport).Path; sha256 = $expectedShardHash }
        fullTrainInventory = $shard.inputs.inventoryReport
        previousFixed32VisualAudit = [ordered]@{ path = $previousAuditPath; sha256 = $previousAuditHash }
    }
    counts = [ordered]@{
        reviewedSourceOverviews = 20
        boundNativeOverlays = $nailTotal
        visualApprovedSourceImages = 0
        visualApprovedNails = 0
        statuses = $counts
    }
    sourceTriage = $rows
    scope = [ordered]@{
        originalResolutionSourceOverviewReviewOnly = $true
        everyNailOriginalResolutionReviewComplete = $false
        fullTrainSplitApproved = $false
        trainingUse = 'unchanged'
        historicalMetricsAndFailures = 'unchanged'
        protectedTestOrHoldoutUsedForSelection = $false
        moreTrainingBeforeFullSplitAudit = 'prohibited'
    }
}
$json = $result | ConvertTo-Json -Depth 100
if ($VerifyReport) {
    if (-not (Test-Path -LiteralPath $VerifyReport -PathType Leaf)) { throw "缺少待验报告：$VerifyReport" }
    $recorded = (Get-Content -LiteralPath $VerifyReport -Raw).TrimEnd()
    if ($recorded -cne $json.TrimEnd()) { throw '源图初筛报告重放不一致' }
    Write-Output 'verified_source_overview_triage_pending_every_nail_review'
} else {
    if (-not $Output) { throw '必须提供-Output或-VerifyReport' }
    $parent = Split-Path -Parent $Output
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Set-Content -LiteralPath $Output -Value $json -Encoding utf8
    Write-Output 'source_overview_triage_only_pending_every_nail_review'
}
