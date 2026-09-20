#!/usr/bin/env python3
"""构建循环015真实素材首批累计入库声明（v3）。

v2更正（2026-09-19预标注复核）：0001甲数4→5（拇指完整入画，v1漏数）、
0004甲数5→4（拇指仅游离缘虚化可见）、0005甲数5→4（拇指未入画）、
0012甲数5→4（拇指按于瓶盖甲面不可见）；更正依据为守卫版YOLO预标注
overlay与原分辨率局部放大重读，v1声明与其审计报告保留作废证据。

v3更正（2026-09-19逐甲原分辨率放大复核）：0002整图PASS改排除——右下第三枚
甲面在2x放大复核下失焦严重，甲面轮廓与游离缘边界与皮肤模糊融合、无法在
原分辨率确认完整甲面轮廓（sharpEnoughForCompleteBoundary=False），v2声明
「轻度景深虚化但可完整确认」判定被推翻；按Goal硬规则「失焦到无法确认完整
甲面轮廓的源图必须在源图筛选阶段排除」整图排除，v2声明与审计保留作废证据。
该裁定同时消解0002三枚SAM候选的自交多边形问题（整图出清，无需后处理）。

输入：
- 只读盘点报告 real-material-inventory-v1.json（提供原始素材字节SHA-256与头尺寸）；
- 前序生成素材入库声明 generated-source-declaration-v9.json（43项合格逐字保留）。

行为：
1. 按12项PASS判定表把原始素材字节级复制到冻结副本目录（cycle015_real_NNNN_*）；
2. 组装累计声明：43项前序逐字 + 12项真实素材PASS + 2项排除（10/15，物理裁断/遮挡）；
3. 计算itemsSha256（canonical JSON）并写出声明。

不修改任何原始素材；副本为新建文件。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

SOURCE_ROOT = Path(r"E:\AI Project\Codex\JiaRu_image\真实素材\美甲图片素材")
COPY_ROOT = Path(r"E:\AI Project\Codex\JiaRu_image\真实素材\2026_9_19_cycle015_real_material_v1")
GROUP_PREFIX = "real-material:2026-09-19:cycle015"

PASS_CHECKS = {
    "allRequiredNailsFullyVisible": True,
    "noNailTouchesImageEdge": True,
    "sharpEnoughForCompleteBoundary": True,
    "noOcclusion": True,
    "noTextLogoOrWatermark": True,
    "anatomyPlausible": True,
    "notSuspectedAiGenerated": True,
}

# (原始文件, 组号, 冻结名, 甲数, visualProfile, notes, watermarkRegistration)
PASS_ITEMS = [
    ("1.jpg", "0001", "cycle015_real_0001_rosewood_squoval_knit.jpg", 5,
     "single hand rosewood-red squoval short nails emerging from cream knit sleeve, black background",
     "单手五甲（预标注复核更正：拇指自袖口上方伸出且甲面完整可见，v1终审漏数4→5），豆沙红方圆短甲完整清晰，米白粗针织袖，纯黑背景，无触边无遮挡无文字"),
    ("3.jpg", "0003", "cycle015_real_0003_nude_pink_squoval_florals.jpg", 4,
     "single hand nude-pink squoval nails resting before orange wax-flower sprigs, black background, gold chain ring",
     "单手四甲（拇指藏于花后为非应标甲面），裸粉方甲完整清晰，橙红腊花枝前景虚化不触甲面，金链戒，纯黑背景"),
    ("4.jpg", "0004", "cycle015_real_0004_nude_shimmer_white_rose.jpg", 4,
     "single hand nude shimmer short nails holding cream-white rose, pale grey-blue tulle background",
     "单手四甲（预标注复核更正：拇指强景深虚化仅游离缘可见、甲面主体不可见，v1终审误数5→4），食中无名小四枚裸粉细闪短甲完整清晰，持奶白玫瑰，浅灰蓝纱背景"),
    ("5.jpg", "0005", "cycle015_real_0005_pearl_pink_satin_lilac.jpg", 4,
     "single hand pearl-pink short nails resting on arm, lilac satin blouse, thin beaded ring",
     "单手四甲（预标注复核更正：拇指未入画，v1终审误数5→4，近景大甲面为离镜头近的无名指），淡粉珠光短甲完整清晰，丁香紫绸衬衫，细珠戒，低饱和柔和光影，无文字无水印"),
    ("6.jpg", "0006", "cycle015_real_0006_black_silver_glitter_givenchy.jpg", 6,
     "two hands black-silver glitter nails holding Givenchy sparkle-pill compact, dark sequin fabric",
     "双手六甲：右手四枚横列完整清晰，左手两枚完整清晰（左下侧位一枚不计入）；Givenchy四宫格产品logo按用户裁决登记并挂训练前消融义务",
     {"type": "brand product logo (Givenchy)", "position": "画面中上散粉盒正面中央",
      "description": "纪梵希白色四宫格标志印于黑色亮片散粉盒面，位于右手中指与无名指甲面后方、不覆盖任何甲面",
      "ablationRequiredBeforeTrainingUse": True}),
    ("7.jpg", "0007", "cycle015_real_0007_neon_lime_cateye_fist.jpg", 5,
     "single fist hand neon lime-yellow cat-eye squoval nails over dark charcoal fabric",
     "单手握拳五甲（含拇指），荧光黄绿猫眼方甲完整清晰，深灰织物背景，顶部小指甲面完整（远位略小）"),
    ("8.jpg", "0008", "cycle015_real_0008_nude_gold_french_palm.jpg", 5,
     "open palm nude-pink short nails with fine gold French line, beige trouser fabric background",
     "单手五甲（掌心向上），四指裸粉金边法式完整清晰；拇指甲面为近透明裸色，经2x放大复核根-尖-游离缘完整可确认（低对比非不可确认）"),
    ("9.jpg", "0009", "cycle015_real_0009_pink_ombre_almond_gems.jpg", 5,
     "single hand long almond pink-ombre nails with pink gem and pearl accents, chain-link rings, white knit cuff",
     "单手五甲（含拇指），粉渐变长杏仁甲完整清晰，无名指粉钻+珍珠饰，链条戒指，白色针织袖口，无触边"),
    ("12.jpg", "0010", "cycle015_real_0010_silver_chrome_melt_swirl.jpg", 5,
     "single hand silver chrome melt-design nails with nude squoval accents and black line art, grey knit cuff, silver open rings",
     "单手五甲（含拇指横位），银色液态金属风+裸底黑线手绘短甲完整清晰，灰毛衣袖口，银色开口戒"),
    ("16.jpg", "0011", "cycle015_real_0011_amber_calligraphy_coffin.jpg", 5,
     "single hand long coffin amber-jelly nails with black calligraphy brush strokes, grey ribbed knit sweater, fishnet background",
     "单手五甲，茶色琥珀透感棺形甲完整清晰，黑色书法笔画与小点装饰，顶部拇指侧视枚经2.5x放大复核根部无遮挡、根-尖完整，灰罗纹毛衣，渔网纹背景"),
    ("20.jpg", "0012", "cycle015_real_0012_mauve_leopard_chanel_lipglaze.jpg", 4,
     "single hand mauve matte nails with white-based leopard-print accent nails holding CHANEL lip glaze, wine velvet and pink fabric",
     "单手四甲（预标注复核更正：拇指按于瓶盖顶部、甲面朝向瓶体不可见，v1终审误数5→4），食中无名小四枚红棕哑光+白底豹纹印花组合甲完整清晰；CHANEL瓶身logo按用户裁决登记并挂训练前消融义务",
     {"type": "brand product logo (CHANEL)", "position": "唇釉瓶身黑色盖区",
      "description": "CHANEL白色小字印于唇釉瓶盖黑色区域，位于拇指与食指之间、不覆盖任何甲面",
      "ablationRequiredBeforeTrainingUse": True}),
]

# (原始文件, 排除组号, 检查覆盖, 排除原因)
EXCLUDE_ITEMS = [
    ("2.jpg", "excl-2",
     {"allRequiredNailsFullyVisible": True, "noNailTouchesImageEdge": True,
      "sharpEnoughForCompleteBoundary": False, "noOcclusion": True,
      "noTextLogoOrWatermark": True, "anatomyPlausible": True, "notSuspectedAiGenerated": True},
     "近摄特写三甲中右下第三枚经逐甲2x放大复核（review-crops/0002-nail2-crop.png）失焦严重，甲面轮廓与游离缘边界与皮肤模糊融合、原分辨率无法确认完整甲面轮廓；v2声明「轻度虚化可确认」判定被推翻；按Goal硬规则整图排除（另两枚甲面完好不改变整图判定）"),
    ("10.jpg", "excl-10",
     {"allRequiredNailsFullyVisible": False, "noNailTouchesImageEdge": False,
      "sharpEnoughForCompleteBoundary": True, "noOcclusion": True,
      "noTextLogoOrWatermark": True, "anatomyPlausible": True, "notSuspectedAiGenerated": True},
     "左下角绿色甲面被图像底边物理裁断、仅部分入画，无法产出完整像素级mask；按Goal核心要求整图排除（其余甲面完好不改变整图判定）"),
    ("15.jpg", "excl-15",
     {"allRequiredNailsFullyVisible": False, "noNailTouchesImageEdge": True,
      "sharpEnoughForCompleteBoundary": True, "noOcclusion": False,
      "noTextLogoOrWatermark": True, "anatomyPlausible": True, "notSuspectedAiGenerated": True},
     "右上另一手持粉色物体，其甲面被物体遮挡不完全可见，且整体暗光降低边界确认性；按Goal核心要求整图排除（中央主手五甲完好不改变整图判定）"),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--prior-declaration", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    prior = json.loads(Path(args.prior_declaration).read_text(encoding="utf-8"))
    by_name = {record["fileName"]: record for record in inventory["files"]}

    prior_items = prior["items"]
    prior_pass_count = sum(1 for item in prior_items if item.get("sourceGateDecision") == "pass")
    if prior_pass_count != 43:
        raise ValueError(f"前序声明合格条目数漂移：{prior_pass_count}")

    COPY_ROOT.mkdir(parents=True, exist_ok=True)
    new_items: list[dict[str, Any]] = []
    for source_name, group_tag, frozen_name, nails, profile, note, *rest in PASS_ITEMS:
        record = by_name.get(f"1/{source_name}")
        if record is None:
            raise ValueError(f"盘点报告缺少记录：1/{source_name}")
        origin = Path(record["path"])
        if sha256_file(origin) != record["sha256"]:
            raise ValueError(f"原始素材哈希漂移：{origin}")
        copy_path = COPY_ROOT / frozen_name
        if copy_path.exists():
            if sha256_file(copy_path) != record["sha256"]:
                raise ValueError(f"冻结副本已存在且哈希不一致：{copy_path}")
        else:
            shutil.copy2(origin, copy_path)
            if sha256_file(copy_path) != record["sha256"]:
                raise ValueError(f"冻结副本哈希不一致：{copy_path}")
        item: dict[str, Any] = {
            "fileName": frozen_name,
            "path": str(copy_path),
            "originPath": str(origin),
            "imageSha256": record["sha256"],
            "dimensions": [record["width"], record["height"]],
            "format": record["format"],
            "sourceGroup": f"{GROUP_PREFIX}:{group_tag}",
            "visualProfile": profile,
            "originalResolutionNotes": note,
            "fullyVisibleNails": nails,
            "sourceGateDecision": "pass",
            "originalResolutionChecks": dict(PASS_CHECKS),
            "trainingUse": "prohibited",
            "sourceReviewedAt": "2026-09-19",
        }
        if rest and rest[0] is not None:
            item["noTextLogoOrWatermark"] = False
            item["originalResolutionChecks"]["noTextLogoOrWatermark"] = False
            item["watermarkRegistration"] = rest[0]
        new_items.append(item)

    for source_name, group_tag, checks, reason in EXCLUDE_ITEMS:
        record = by_name.get(f"1/{source_name}")
        if record is None:
            raise ValueError(f"盘点报告缺少记录：1/{source_name}")
        origin = Path(record["path"])
        if sha256_file(origin) != record["sha256"]:
            raise ValueError(f"原始素材哈希漂移：{origin}")
        new_items.append(
            {
                "fileName": source_name,
                "path": str(origin),
                "originPath": str(origin),
                "imageSha256": record["sha256"],
                "dimensions": [record["width"], record["height"]],
                "format": record["format"],
                "sourceGroup": f"{GROUP_PREFIX}:{group_tag}",
                "visualProfile": "excluded at source gate, profile not applicable",
                "originalResolutionNotes": reason,
                "fullyVisibleNails": 0,
                "sourceGateDecision": "exclude",
                "exclusionReason": reason,
                "originalResolutionChecks": checks,
                "trainingUse": "prohibited",
                "sourceReviewedAt": "2026-09-19",
            }
        )

    items = prior_items + new_items
    declaration = {
        "schemaVersion": 1,
        "decision": "real_material_sources_reviewed_at_original_resolution",
        "createdAt": "2026-09-19",
        "reviewScale": "original-resolution",
        "reviewedBy": "WorkBuddy",
        "sourceType": "user-provided-real-material",
        "authorization": "standing-project-commercial-development-authorization",
        "role": "development-evaluation-extension",
        "trainingUse": "prohibited",
        "supplyChannelChange": {
            "directive": "user-directive-2026-09-19-disable-ai-generated-supply-use-real-material",
            "aiGeneratedSupplyDisabledGoingForward": True,
            "priorGeneratedItemsRetained": 43,
            "userUsabilityRuling": (
                "user-ruled-no-machine-filtering-and-all-provided-images-usable-2026-09-19; "
                "brand-logo items retained via registration with pre-training ablation debt; "
                "edge-cropped or occlusion-blocked nail images still excluded per goal core "
                "requirements because a complete pixel-level mask is physically impossible"
            ),
        },
        "priorFreeze": {
            "path": str(Path(args.prior_declaration).resolve()),
            "sha256": sha256_file(Path(args.prior_declaration)),
            "itemCount": len(prior_items),
        },
        "itemsSha256": canonical_sha256(items),
        "items": items,
    }

    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(declaration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pass_count = sum(1 for item in new_items if item["sourceGateDecision"] == "pass")
    print(
        json.dumps(
            {
                "ok": True,
                "priorItems": len(prior_items),
                "newPassItems": pass_count,
                "newExcludedItems": len(new_items) - pass_count,
                "newNails": sum(item["fullyVisibleNails"] for item in new_items),
                "totalItems": len(items),
                "declaration": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
