param(
    [Parameter(Mandatory = $true)][string]$ShardReport,
    [Parameter(Mandatory = $true)][string]$SourceTriageReport,
    [Parameter(Mandatory = $true)][string]$VisualDecisions,
    [string]$Output,
    [string]$VerifyReport
)

$ErrorActionPreference = 'Stop'
$Culture = [Globalization.CultureInfo]::InvariantCulture

function Read-BoundJson([string]$Path, [string]$ExpectedHash) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "缺少绑定文件：$Path" }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ExpectedHash -and $actual -ne $ExpectedHash.ToLowerInvariant()) { throw "SHA-256漂移：$Path" }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -AsHashtable
}

function Test-BoundFile($Binding) {
    if (-not (Test-Path -LiteralPath $Binding.path -PathType Leaf)) { throw "缺少证据文件：$($Binding.path)" }
    if ((Get-FileHash -LiteralPath $Binding.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Binding.sha256.ToLowerInvariant()) {
        throw "证据文件SHA-256漂移：$($Binding.path)"
    }
}

function Cross([double[]]$a, [double[]]$b, [double[]]$c) {
    return ($b[0] - $a[0]) * ($c[1] - $a[1]) - ($b[1] - $a[1]) * ($c[0] - $a[0])
}

function On-Segment([double[]]$a, [double[]]$b, [double[]]$p) {
    $eps = 1e-12
    return ([Math]::Abs((Cross $a $b $p)) -le $eps -and
        $p[0] -ge [Math]::Min($a[0], $b[0]) - $eps -and $p[0] -le [Math]::Max($a[0], $b[0]) + $eps -and
        $p[1] -ge [Math]::Min($a[1], $b[1]) - $eps -and $p[1] -le [Math]::Max($a[1], $b[1]) + $eps)
}

function Segments-Intersect([double[]]$a, [double[]]$b, [double[]]$c, [double[]]$d) {
    $eps = 1e-12
    $o1 = Cross $a $b $c
    $o2 = Cross $a $b $d
    $o3 = Cross $c $d $a
    $o4 = Cross $c $d $b
    if (($o1 * $o2 -lt -$eps) -and ($o3 * $o4 -lt -$eps)) { return $true }
    if ([Math]::Abs($o1) -le $eps -and (On-Segment $a $b $c)) { return $true }
    if ([Math]::Abs($o2) -le $eps -and (On-Segment $a $b $d)) { return $true }
    if ([Math]::Abs($o3) -le $eps -and (On-Segment $c $d $a)) { return $true }
    if ([Math]::Abs($o4) -le $eps -and (On-Segment $c $d $b)) { return $true }
    return $false
}

function Point-In-Polygon([double[]]$point, [object[]]$points) {
    $inside = $false
    $j = $points.Count - 1
    for ($i = 0; $i -lt $points.Count; $i++) {
        $a = $points[$i]
        $b = $points[$j]
        if ((($a[1] -gt $point[1]) -ne ($b[1] -gt $point[1])) -and
            ($point[0] -lt (($b[0] - $a[0]) * ($point[1] - $a[1]) / ($b[1] - $a[1]) + $a[0]))) {
            $inside = -not $inside
        }
        $j = $i
    }
    return $inside
}

function Parse-Polygon([string]$Line, [int]$Index) {
    $tokens = @($Line.Trim() -split '\s+')
    if ($tokens.Count -lt 7 -or (($tokens.Count - 1) % 2) -ne 0 -or $tokens[0] -ne '0') {
        throw "非法YOLO polygon行：$Index"
    }
    $points = @()
    for ($i = 1; $i -lt $tokens.Count; $i += 2) {
        $x = [double]::Parse($tokens[$i], $Culture)
        $y = [double]::Parse($tokens[$i + 1], $Culture)
        if (-not [double]::IsFinite($x) -or -not [double]::IsFinite($y) -or
            $x -lt 0 -or $x -gt 1 -or $y -lt 0 -or $y -gt 1) {
            throw "polygon坐标越界：$Index"
        }
        $points += ,([double[]]@($x, $y))
    }
    $area2 = 0.0
    $n = $points.Count
    for ($i = 0; $i -lt $n; $i++) {
        $j = ($i + 1) % $n
        $a = $points[$i]
        $b = $points[$j]
        if ([Math]::Abs($a[0] - $b[0]) + [Math]::Abs($a[1] - $b[1]) -lt 1e-10) {
            throw "polygon零长度边：$Index"
        }
        $area2 += $a[0] * $b[1] - $b[0] * $a[1]
    }
    if ([Math]::Abs($area2) / 2 -le 1e-6) { throw "polygon面积过小：$Index" }
    for ($i = 0; $i -lt $n; $i++) {
        $nextI = ($i + 1) % $n
        for ($j = $i + 1; $j -lt $n; $j++) {
            $nextJ = ($j + 1) % $n
            if ($j -eq $nextI -or ($i -eq 0 -and $j -eq $n - 1)) { continue }
            if (Segments-Intersect $points[$i] $points[$nextI] $points[$j] $points[$nextJ]) {
                throw "polygon自交：$Index/$i/$j"
            }
        }
    }
    $xs = @($points | ForEach-Object { $_[0] })
    $ys = @($points | ForEach-Object { $_[1] })
    return [ordered]@{
        vertexCount = $n
        normalizedArea = [Math]::Abs($area2) / 2
        points = $points
        bbox = @(
            ($xs | Measure-Object -Minimum).Minimum,
            ($ys | Measure-Object -Minimum).Minimum,
            ($xs | Measure-Object -Maximum).Maximum,
            ($ys | Measure-Object -Maximum).Maximum
        )
    }
}

$expectedShardHash = '97da8ed76288b0e2887f352a232dfa92ea0fc3a19c427e38554499df18d8efe7'
$expectedTriageHash = 'fd89cb8bf3f59da09a7c700ae0280ac03ffb1043f58910f0a2a0a716804a3cee'
$shard = Read-BoundJson $ShardReport $expectedShardHash
$triage = Read-BoundJson $SourceTriageReport $expectedTriageHash
$decisions = Read-BoundJson $VisualDecisions $null
if ($shard.shard.shard -ne 1 -or $shard.shard.sourceImages -ne 20 -or $shard.shard.roiInstances -ne 116 -or
    $triage.decision -ne 'source_overview_triage_only_pending_every_nail_review' -or
    $triage.counts.visualApprovedSourceImages -ne 0 -or $triage.counts.visualApprovedNails -ne 0 -or
    $decisions.schemaVersion -ne 1 -or $decisions.shardReportSha256 -ne $expectedShardHash -or
    $decisions.sourceOrdinal -lt 1 -or $decisions.sourceOrdinal -gt 20 -or
    $decisions.sourceDecision -ne 'visual_accept_pending_full_split' -or
    $decisions.trainingUse -ne 'prohibited_until_full_train_split_review_and_new_materialization') {
    throw '分片、初筛或视觉决策合同漂移'
}
$ordinal = [int]$decisions.sourceOrdinal
$source = $shard.sourceImages[$ordinal - 1]
$triageRow = $triage.sourceTriage[$ordinal - 1]
$nailCount = @($source.nails).Count
if ($source.ordinal -ne $ordinal -or $triageRow.ordinal -ne $ordinal -or
    $triageRow.decision -ne 'pending_every_nail_review' -or
    $source.sourceFileName -ne $decisions.sourceFileName -or
    $source.sourceGroup -ne $decisions.sourceGroup -or
    $source.sourceImage.sha256 -ne $decisions.sourceImageSha256 -or
    $source.sourceLabel.sha256 -ne $decisions.sourceLabelSha256 -or
    $nailCount -lt 1 -or @($decisions.nails).Count -ne $nailCount -or
    $decisions.visibleNailCount -ne $nailCount -or $decisions.observedMissingNails -ne 0 -or
    $decisions.observedDuplicateMasks -ne 0 -or $decisions.observedImageEdgeCroppedNails -ne 0 -or
    $decisions.observedSkinClothingBackgroundMaskContamination -ne 0) {
    throw '源图身份或完整甲面视觉合同漂移'
}
Test-BoundFile $source.sourceImage
Test-BoundFile $source.sourceLabel
Test-BoundFile $source.overview
$lines = @(Get-Content -LiteralPath $source.sourceLabel.path | Where-Object { $_.Trim() })
if ($lines.Count -ne $nailCount) { throw '逐甲polygon数量漂移' }
$polygons = @()
for ($i = 0; $i -lt $nailCount; $i++) {
    $nail = $source.nails[$i]
    $review = $decisions.nails[$i]
    if ($nail.truthIndex -ne $i + 1 -or $review.truthIndex -ne $i + 1 -or
        $nail.roiId -ne $review.roiId -or $review.decision -ne 'visual_accept_full_visible_nail') {
        throw "逐甲索引、身份或视觉裁决漂移：$($i + 1)"
    }
    Test-BoundFile $nail.nativeOverlay
    $polygons += ,(Parse-Polygon $lines[$i] ($i + 1))
}
$bboxSeparated = 0
$exactGeometryChecked = 0
for ($i = 0; $i -lt $nailCount; $i++) {
    for ($j = $i + 1; $j -lt $nailCount; $j++) {
        $a = $polygons[$i].bbox
        $b = $polygons[$j].bbox
        if ($a[2] -lt $b[0] -or $b[2] -lt $a[0] -or $a[3] -lt $b[1] -or $b[3] -lt $a[1]) {
            $bboxSeparated++
            continue
        }
        $exactGeometryChecked++
        $pa = $polygons[$i].points
        $pb = $polygons[$j].points
        for ($edgeA = 0; $edgeA -lt $pa.Count; $edgeA++) {
            for ($edgeB = 0; $edgeB -lt $pb.Count; $edgeB++) {
                if (Segments-Intersect $pa[$edgeA] $pa[(($edgeA + 1) % $pa.Count)] $pb[$edgeB] $pb[(($edgeB + 1) % $pb.Count)]) {
                    throw "polygon边段相交：$($i + 1)/$($j + 1)"
                }
            }
        }
        if ((Point-In-Polygon $pa[0] $pb) -or (Point-In-Polygon $pb[0] $pa)) {
            throw "polygon包含交叠：$($i + 1)/$($j + 1)"
        }
    }
}
$result = [ordered]@{
    schemaVersion = 1
    evidenceOk = $true
    decision = 'one_source_visual_and_polygon_pass_full_split_still_prohibited'
    inputs = [ordered]@{
        sourceScript = [ordered]@{ path = $PSCommandPath; sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() }
        shardReport = [ordered]@{ path = (Resolve-Path -LiteralPath $ShardReport).Path; sha256 = $expectedShardHash }
        sourceTriage = [ordered]@{ path = (Resolve-Path -LiteralPath $SourceTriageReport).Path; sha256 = $expectedTriageHash }
        visualDecisions = [ordered]@{ path = (Resolve-Path -LiteralPath $VisualDecisions).Path; sha256 = (Get-FileHash -LiteralPath $VisualDecisions -Algorithm SHA256).Hash.ToLowerInvariant() }
    }
    source = [ordered]@{
        ordinal = $ordinal
        fileName = $source.sourceFileName
        sourceGroup = $source.sourceGroup
        sourceImage = $source.sourceImage
        sourceLabel = $source.sourceLabel
        overview = $source.overview
        nativeOverlays = @($source.nails | ForEach-Object { $_.nativeOverlay })
    }
    counts = [ordered]@{
        visibleNails = $nailCount
        labelPolygons = $lines.Count
        polygonLegal = $nailCount
        bboxSeparatedPairs = $bboxSeparated
        exactPolygonDisjointPairs = $exactGeometryChecked
        pairwiseZeroOverlap = $nailCount * ($nailCount - 1) / 2
        originalResolutionVisualAcceptedNails = $nailCount
        originalResolutionVisualAcceptedSources = 1
    }
    polygonAudit = @($polygons | ForEach-Object { [ordered]@{ vertexCount = $_.vertexCount; normalizedArea = $_.normalizedArea; bbox = $_.bbox } })
    scope = [ordered]@{
        onlyOneSourceImageReviewed = $true
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
        throw '单图视觉与几何审核报告重放不一致'
    }
    Write-Output 'verified_one_source_visual_and_polygon_pass_full_split_still_prohibited'
} else {
    if (-not $Output) { throw '必须提供-Output或-VerifyReport' }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null
    Set-Content -LiteralPath $Output -Value $json -Encoding utf8
    Write-Output 'one_source_visual_and_polygon_pass_full_split_still_prohibited'
}
