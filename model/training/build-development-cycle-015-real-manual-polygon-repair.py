#!/usr/bin/env python3
"""构建循环015真实素材首批逐甲终审后的人工多边形返修（annotations v3）。

背景（2026-09-19逐甲原分辨率终审）：
- 52枚SAM候选中39枚PASS、13枚REWORK（边缘锯齿缺口/粘连尾巴/透明甲边界抖动/
  0011无名指过分割含指尖皮肤）。
- 按AGENTS.md允许路径（透明低对比或持续合并皮肤/邻指的甲可切换原分辨率
  人工多边形），对13枚REWORK以网格底图逐甲重测边界，人工绘制完整甲面多边形。

输入：
- sam-annotations-v2/annotations（v2 SAM候选，v1的0011噪声mask保留作废证据）；
- review-crops/manual-repair-grids/*.png（13张网格返修底图）。

行为：
1. 替换13枚指定多边形为人工测量点列（原图坐标）；
2. 每枚记录manualRepair元数据（原因、底图证据）；
3. 输出annotations v3 + 返修报告；
4. 0011-n4经两级修正：v3初版多边形误描到中指/无名指之间（几何审计v4
   暴露与n2的6308px²交叠后定位，作废）；v4初版重测多边形左/右/下三边
   浮出甲面（终审叠加图发现，作废）。终版以数值化边界检测（饱和度跳变
   +梯度+局部方差扫描）与多倍放大网格（25px精测/4倍尖端/3倍右下）定案；
   证据链见review-crops/0011-n4-25px-grid-25x.png、0011-n4-tip-4x.png、
   0011-n4-bottomright-3x.png，SAM v2尖端测量作独立互证。
产物始终是候选：不因人工绘制本身视为通过，仍需视觉复核+几何审计。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

# (图号, 甲id, 原因, 网格底图, 人工多边形点列[原图坐标])
MANUAL_POLYGONS: list[tuple[str, str, str, str, list[tuple[int, int]]]] = [
    ("0001", "n4", "右下游离缘下方尾巴状皮肤粘连", "0001-n4-repair-grid.png",
     [(480, 1718), (560, 1716), (620, 1722), (660, 1735), (700, 1762), (745, 1800), (790, 1852), (825, 1895), (852, 1928), (838, 1952), (800, 1978), (760, 1988), (700, 1992), (640, 1992), (580, 1985), (530, 1970), (480, 1945), (440, 1915), (412, 1875), (396, 1825), (390, 1775), (398, 1735), (420, 1715), (450, 1712)]),
    ("0003", "n2", "右侧缘锯齿缺口切进甲面", "0003-n2-repair-grid.png",
     [(1155, 1938), (1200, 1905), (1245, 1884), (1295, 1886), (1335, 1905), (1358, 1935), (1368, 1975), (1372, 2020), (1366, 2065), (1352, 2105), (1325, 2138), (1280, 2160), (1225, 2168), (1170, 2158), (1125, 2138), (1090, 2108), (1065, 2068), (1052, 2020), (1053, 1972), (1068, 1928), (1095, 1895), (1128, 1878)]),
    ("0003", "n4", "左上V形缺口漏覆盖甲面", "0003-n4-repair-grid.png",
     [(1720, 1613), (1780, 1590), (1845, 1580), (1888, 1594), (1906, 1622), (1910, 1662), (1898, 1702), (1878, 1738), (1820, 1772), (1750, 1793), (1680, 1796), (1630, 1775), (1602, 1738), (1592, 1692), (1600, 1648), (1622, 1615), (1665, 1598)]),
    ("0004", "n3", "右下碎片状粘连与缺口", "0004-n3-repair-grid.png",
     [(1090, 1528), (1160, 1500), (1245, 1486), (1315, 1490), (1362, 1512), (1388, 1562), (1396, 1620), (1380, 1680), (1310, 1728), (1230, 1758), (1150, 1772), (1085, 1762), (1040, 1728), (1022, 1672), (1020, 1608), (1032, 1560), (1058, 1532)]),
    ("0004", "n4", "左下V形缺口", "0004-n4-repair-grid.png",
     [(1180, 1970), (1265, 1950), (1345, 1947), (1410, 1952), (1448, 1972), (1466, 2012), (1468, 2058), (1448, 2100), (1385, 2135), (1310, 2152), (1245, 2150), (1195, 2138), (1155, 2112), (1122, 2080), (1106, 2040), (1102, 2000), (1118, 1968), (1150, 1958)]),
    ("0005", "n3", "下缘波浪状粘连凸出", "0005-n3-repair-grid.png",
     [(1035, 2298), (1092, 2280), (1145, 2278), (1185, 2290), (1208, 2308), (1228, 2348), (1238, 2392), (1226, 2440), (1180, 2468), (1120, 2482), (1068, 2480), (1028, 2460), (998, 2428), (978, 2392), (972, 2350), (984, 2315), (1010, 2298)]),
    ("0006", "n5", "右侧矩形锯齿缺口", "0006-n5-repair-grid.png",
     [(962, 750), (1020, 741), (1078, 739), (1108, 746), (1130, 776), (1142, 812), (1150, 852), (1150, 896), (1138, 936), (1118, 962), (1058, 986), (998, 996), (958, 990), (922, 972), (902, 942), (890, 900), (896, 852), (908, 806), (928, 772)]),
    ("0007", "n5", "左下锯齿缺口", "0007-n5-repair-grid.png",
     [(1075, 852), (1150, 838), (1222, 846), (1272, 870), (1290, 894), (1240, 938), (1190, 962), (1135, 984), (1080, 992), (1038, 970), (1020, 922), (1020, 878), (1040, 856)]),
    ("0008", "n5", "透明低对比甲下缘锯齿与右下尾巴越界", "0008-n5-repair-grid.png",
     [(1255, 488), (1300, 500), (1360, 503), (1430, 500), (1485, 494), (1525, 480), (1560, 452), (1588, 415), (1608, 362), (1618, 300), (1618, 232), (1602, 188), (1585, 183), (1555, 230), (1500, 285), (1445, 335), (1395, 388), (1330, 440), (1288, 470)]),
    ("0009", "n2", "左侧/右上/左下多处矩形锯齿", "0009-n2-repair-grid.png",
     [(1075, 878), (1122, 853), (1172, 844), (1215, 848), (1242, 864), (1258, 902), (1262, 952), (1250, 1002), (1222, 1052), (1185, 1092), (1135, 1118), (1078, 1130), (1028, 1124), (982, 1102), (952, 1066), (940, 1018), (946, 968), (962, 922), (990, 890), (1030, 870)]),
    ("0009", "n4", "左下锯齿缺口", "0009-n4-repair-grid.png",
     [(1518, 1612), (1565, 1615), (1625, 1606), (1682, 1608), (1726, 1620), (1746, 1652), (1750, 1692), (1736, 1730), (1678, 1758), (1618, 1772), (1558, 1770), (1515, 1752), (1492, 1722), (1478, 1682), (1482, 1638), (1498, 1615)]),
    ("0011", "n4", "无名指严重过分割：mask含整段指尖皮肤肉垫；v3初版多边形误描到中指/无名指之间（作废）；v4初版重测三边浮出甲面（作废）；终版经数值化边界检测+多倍放大网格定案：甲尖左缘x≈1002-1010（织物V<65→甲面S>100/V≈159饱和度锐利跳变，与SAM v2尖端1004-1016互证），上缘y≈1350@x1300，下缘沿甲襞线（与n2同约定，保持强阴影缘上方≥4px），右端沿甲小皮弧线（3倍图斑点纹理→平滑皮肤过渡，最右x≈1398@y1428）；证据0011-n4-25px-grid-25x.png + 0011-n4-tip-4x.png + 0011-n4-bottomright-3x.png", "0011-n4-25px-grid-25x.png",
     [(1010, 1388), (1080, 1368), (1150, 1359), (1250, 1352), (1300, 1350), (1336, 1348), (1362, 1368), (1380, 1392), (1396, 1414), (1398, 1428), (1385, 1445), (1360, 1458), (1300, 1462), (1200, 1460), (1100, 1450), (1040, 1447), (1010, 1444), (1002, 1420), (1004, 1402)]),
    ("0011", "n5", "定向重试拇指mask锯齿缺口（透明甲与皮肤交界震荡）", "0011-n5-repair-grid.png",
     [(1100, 258), (1150, 240), (1210, 218), (1280, 198), (1350, 185), (1412, 178), (1442, 182), (1452, 200), (1450, 228), (1435, 262), (1398, 292), (1340, 322), (1268, 345), (1205, 352), (1155, 342), (1120, 315), (1103, 285)]),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations-v2-dir", required=True)
    parser.add_argument("--grids-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    src_dir = Path(args.annotations_v2_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    grids_dir = Path(args.grids_dir)

    repairs: list[dict[str, Any]] = []
    repaired_files = 0
    for ann_path in sorted(src_dir.glob("*.json")):
        doc = json.loads(ann_path.read_text(encoding="utf-8"))
        targets = [(sub, nail, reason, grid, poly) for sub, nail, reason, grid, poly in MANUAL_POLYGONS if sub in doc["image"]["fileName"]]
        changed = False
        for sub, nail_id, reason, grid, poly in targets:
            target = next((a for a in doc["annotations"] if a["id"] == nail_id), None)
            if target is None:
                raise ValueError(f"{doc['image']['fileName']} 缺少 {nail_id}")
            grid_path = grids_dir / grid
            if not grid_path.is_file():
                raise ValueError(f"网格底图缺失：{grid_path}")
            target["polygon"] = [{"x": float(x), "y": float(y)} for x, y in poly]
            target["manualRepair"] = {
                "applied": True,
                "reason": reason,
                "gridEvidence": str(grid_path),
                "gridEvidenceSha256": sha256_file(grid_path),
                "vertexCount": len(poly),
                "reviewedAt": "2026-09-19",
                "reviewer": "WorkBuddy 逐甲原分辨率终审",
                "stillCandidateOnly": True,
            }
            repairs.append({"fileName": doc["image"]["fileName"], "nailId": nail_id, "reason": reason,
                            "gridEvidence": grid, "vertexCount": len(poly)})
            changed = True
        if changed:
            repaired_files += 1
            (out_dir / ann_path.name).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            (out_dir / ann_path.name).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    if len(repairs) != len(MANUAL_POLYGONS):
        raise ValueError(f"返修条目数不符：{len(repairs)} != {len(MANUAL_POLYGONS)}")

    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "manual_polygon_repair_candidate_only_not_training_truth",
        "trainingUse": "prohibited",
        "originalResolutionReviewRequired": True,
        "inputs": {
            "annotationsV2Dir": str(src_dir),
            "gridsDir": str(grids_dir),
        },
        "repairCount": len(repairs),
        "repairedFiles": repaired_files,
        "repairs": repairs,
        "policy": {
            "manualPolygonStillRequiresVisualReview": True,
            "manualPolygonStillRequiresGeometryAudit": True,
        },
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "repairCount": len(repairs), "repairedFiles": repaired_files,
                      "report": args.report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
