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

function Check-Binding($Binding) {
    if (-not (Test-Path -LiteralPath $Binding.path -PathType Leaf)) { throw "缺少绑定文件：$($Binding.path)" }
    if ((Get-FileHash -LiteralPath $Binding.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Binding.sha256.ToLowerInvariant()) {
        throw "绑定文件哈希漂移：$($Binding.path)"
    }
}

$shardHash = '97da8ed76288b0e2887f352a232dfa92ea0fc3a19c427e38554499df18d8efe7'
$priorHash = 'd32d7480d9a51cf52ed415da3a9c46b9b4d0da80b8f99366b1ce5fe77ada8ba3'
$source10Hash = 'ac0f2ae5150abddfd043973353bd74c4fc2a52c3fb4dac7037d6ada80b2ac8d3'
$shard = Read-BoundJson $ShardReport $shardHash
$priorPath = 'model/reviews/cycle016-shard001-reviewed-subset-v2.json'
$newPassPath = 'model/reviews/cycle016-shard001-source010-visual-audit-v1.json'
$prior = Read-BoundJson $priorPath $priorHash
$source10 = Read-BoundJson $newPassPath $source10Hash
if ($shard.ok -ne $true -or $shard.shard.shard -ne 1 -or $shard.shard.sourceImages -ne 20 -or
    $shard.shard.roiInstances -ne 116 -or @($shard.sourceImages).Count -ne 20 -or
    $prior.evidenceOk -ne $true -or $prior.decision -ne 'seven_visual_pass_seven_source_exclude_six_pending_no_training' -or
    $prior.counts.visualAcceptedSourceImages -ne 7 -or $prior.counts.visualAcceptedNails -ne 39 -or
    $prior.counts.sourceExcludedImages -ne 7 -or $prior.counts.sourceExcludedOldLabelNails -ne 40 -or
    $prior.counts.pendingSourceImages -ne 6 -or $prior.counts.pendingOldLabelNails -ne 37 -or
    $source10.evidenceOk -ne $true -or $source10.source.ordinal -ne 10 -or
    $source10.source.fileName -ne $shard.sourceImages[9].sourceFileName -or
    $source10.source.sourceGroup -ne $shard.sourceImages[9].sourceGroup -or
    $source10.source.sourceImage.sha256 -ne $shard.sourceImages[9].sourceImage.sha256 -or
    $source10.source.sourceLabel.sha256 -ne $shard.sourceImages[9].sourceLabel.sha256 -or
    $source10.decision -ne 'one_source_visual_and_polygon_pass_full_split_still_prohibited' -or
    $source10.counts.originalResolutionVisualAcceptedNails -ne 5 -or
    $source10.counts.polygonLegal -ne 5 -or $source10.counts.pairwiseZeroOverlap -ne 10 -or
    $source10.scope.trainingUse -ne 'prohibited_until_full_train_split_review_and_new_materialization') {
    throw '分片、旧汇总或序号10逐甲审核合同漂移'
}
foreach ($binding in @($source10.inputs.sourceScript, $source10.inputs.visualDecisions)) { Check-Binding $binding }

$manual = [ordered]@{
    '001' = @('source_exclude_incomplete_visible_nail', @(9), '第9枚上方拇指甲被相邻手指挡住，仅露侧缘局部；整图排除。')
    '003' = @('source_exclude_fabric_occlusion', @(5), '二审时第1枚完整，但全图逐甲复核发现第5枚左拇指被针织物遮盖，旧mask包含织物纹理；整图排除，保留二审记录。')
    '005' = @('source_exclude_unlabeled_partial_thumb', @(), '右侧拇指背面仅露极小甲缘且未标注，完整甲面不可确认；整图排除。')
    '008' = @('label_rework_multiple_nails', @(1,2,5), '第1/2枚旧mask漏掉完整可见甲根，第5枚旧mask越过甲尖覆盖皮包带和缝线；整图保持返修且禁训。')
    '018' = @('label_rework_low_contrast_edges', @(2,3), '透明低对比甲的第2/3枚旧mask在甲尖及侧缘内缩且锯齿化，完整可见甲面未被覆盖；整图返修且禁训。')
}

$acceptedOrdinals = @($prior.acceptedSources | ForEach-Object { [int]$_.sourceOrdinal }) + @(10)
$excludedOrdinals = @($prior.excludedSources | ForEach-Object { [int]$_.sourceOrdinal }) + @(1,3,5)
$reworkOrdinals = @(8,18)
if (@($acceptedOrdinals + $excludedOrdinals + $reworkOrdinals | Sort-Object -Unique).Count -ne 20 -or
    10 -in @($prior.acceptedSources | ForEach-Object { [int]$_.sourceOrdinal }) -or
    @($prior.pendingSources | ForEach-Object { [int]$_.sourceOrdinal } | Sort-Object) -join ',' -ne '1,3,5,8,10,18') {
    throw '旧待审六图与新处置清单不一致或重复'
}
$rows = @()
$passNails = 0
$excludeOldNails = 0
$reworkOldNails = 0
foreach ($source in $shard.sourceImages) {
    $ordinal = [int]$source.ordinal
    $oldNails = @($source.nails).Count
    if ($ordinal -in $acceptedOrdinals) {
        $state = 'visual_polygon_pass_pending_full_split'
        $reason = '单图原分辨率视觉与polygon审核报告通过；整片和全split仍待完成。'
        $passNails += $oldNails
        $focus = @()
    } elseif ($ordinal -in $excludedOrdinals) {
        $state = 'source_exclude'
        $excludeOldNails += $oldNails
        $key = '{0:d3}' -f $ordinal
        if ($manual.Contains($key)) {
            $reason = $manual[$key][2]
            $focus = @($manual[$key][1])
        } else {
            $old = @($prior.excludedSources | Where-Object { $_.sourceOrdinal -eq $ordinal })
            if ($old.Count -ne 1 -or $old[0].oldLabelNails -ne $oldNails) { throw "旧排除源图身份漂移：$ordinal" }
            $reason = $old[0].reason
            $focus = @()
        }
    } elseif ($ordinal -in $reworkOrdinals) {
        $state = 'label_rework'
        $reworkOldNails += $oldNails
        $key = '{0:d3}' -f $ordinal
        $reason = $manual[$key][2]
        $focus = @($manual[$key][1])
    } else {
        throw "源图缺少处置：$ordinal"
    }
    $focusBindings = @()
    foreach ($index in $focus) {
        $nail = @($source.nails | Where-Object { $_.truthIndex -eq $index })
        if ($nail.Count -ne 1) { throw "焦点真值序号漂移：$ordinal/$index" }
        Check-Binding $nail[0].nativeOverlay
        $focusBindings += [ordered]@{ truthIndex = $index; nativeOverlay = $nail[0].nativeOverlay }
    }
    if ($manual.Contains(('{0:d3}' -f $ordinal))) {
        Check-Binding $source.sourceImage
        Check-Binding $source.sourceLabel
        Check-Binding $source.overview
    }
    $rows += [ordered]@{
        ordinal = $ordinal
        sourceFileName = $source.sourceFileName
        sourceGroup = $source.sourceGroup
        sourceImageSha256 = $source.sourceImage.sha256
        sourceLabelSha256 = $source.sourceLabel.sha256
        oldLabelNails = $oldNails
        disposition = $state
        reason = $reason
        focusEvidence = $focusBindings
        trainingUse = 'prohibited'
    }
}
if (@($rows | Where-Object disposition -eq 'visual_polygon_pass_pending_full_split').Count -ne 8 -or
    $passNails -ne 44 -or @($rows | Where-Object disposition -eq 'source_exclude').Count -ne 10 -or
    $excludeOldNails -ne 62 -or @($rows | Where-Object disposition -eq 'label_rework').Count -ne 2 -or
    $reworkOldNails -ne 10 -or $passNails + $excludeOldNails + $reworkOldNails -ne 116 -or
    @($rows.sourceGroup | Sort-Object -Unique).Count -ne 20) {
    throw '20图/116枚旧标注数量守恒或来源组互斥漂移'
}
$result = [ordered]@{
    schemaVersion = 1
    evidenceOk = $true
    decision = 'all_shard_sources_disposed_two_label_reworks_pending_no_training'
    inputs = [ordered]@{
        sourceScript = [ordered]@{ path = $PSCommandPath; sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() }
        shardReport = [ordered]@{ path = (Resolve-Path -LiteralPath $ShardReport).Path; sha256 = $shardHash }
        priorSubset = [ordered]@{ path = (Resolve-Path -LiteralPath $priorPath).Path; sha256 = $priorHash }
        newSource10VisualReport = [ordered]@{ path = (Resolve-Path -LiteralPath $newPassPath).Path; sha256 = $source10Hash }
    }
    counts = [ordered]@{
        sourceImages = 20
        oldLabelNails = 116
        visualPolygonPassSources = 8
        visualPolygonPassNails = $passNails
        sourceExcludedImages = 10
        sourceExcludedOldLabelNails = $excludeOldNails
        labelReworkImages = 2
        labelReworkOldLabelNails = $reworkOldNails
        undecidedSourceImages = 0
        newlyTrainingApprovedImages = 0
    }
    sourceDispositions = $rows
    scope = [ordered]@{
        fullShardSourceDispositionsCovered = $true
        fullShardCleanTruthComplete = $false
        fullTrainSplitApproved = $false
        oldTrainSnapshotAndHistoricalFailures = 'unchanged'
        protectedTestOrHoldoutUsedForSelection = $false
        ordinal7WatermarkAblation = 'required_before_training'
        ordinal8And18MaskRepair = 'pending_original_resolution_visual_and_polygon_review'
    }
}
$json = $result | ConvertTo-Json -Depth 100
if ($VerifyReport) {
    if (-not (Test-Path -LiteralPath $VerifyReport -PathType Leaf)) { throw "缺少待验报告：$VerifyReport" }
    if ((Get-Content -LiteralPath $VerifyReport -Raw -Encoding UTF8).TrimEnd() -cne $json.TrimEnd()) {
        throw '分片001全源图处置报告重放不一致'
    }
    Write-Output 'verified_all_shard_sources_disposed_two_label_reworks_pending_no_training'
} else {
    if (-not $Output) { throw '必须提供-Output或-VerifyReport' }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null
    Set-Content -LiteralPath $Output -Value $json -Encoding UTF8
    Write-Output 'all_shard_sources_disposed_two_label_reworks_pending_no_training'
}
