import assert from "node:assert/strict";
import test from "node:test";
import {
  AI_IMAGE_EDIT_SUFFIX,
  AI_IMAGE_SCENE_SUFFIX,
  HAND_ANATOMY_SYSTEM_PROMPT,
  HAND_COUNT_PREFIX,
  IMAGE_EDIT_PREFIX,
  IMAGE_EDIT_SYSTEM_PROMPT,
  assembleAiImageEditPrompt,
  assembleAiImagePrompt,
  extractNailDesign,
} from "../src/lib/ai-hand-anatomy-prompt.ts";

test("assembleAiImagePrompt orders prefix, user prompt, suffix, then hidden system prompt", () => {
  const user = "粉色的樱花美甲";
  const assembled = assembleAiImagePrompt(user);
  const prefixIndex = assembled.indexOf(HAND_COUNT_PREFIX);
  const userIndex = assembled.indexOf(user);
  const suffixIndex = assembled.indexOf(AI_IMAGE_SCENE_SUFFIX);
  const systemIndex = assembled.indexOf(HAND_ANATOMY_SYSTEM_PROMPT);
  assert.ok(prefixIndex === 0, "hand-count prefix must come first");
  assert.ok(userIndex > prefixIndex, "user prompt must follow the prefix");
  assert.ok(suffixIndex > userIndex, "scene suffix must follow user prompt");
  assert.ok(systemIndex > suffixIndex, "system prompt must follow suffix");
  assert.ok(assembled.endsWith(HAND_ANATOMY_SYSTEM_PROMPT));
});

test("assembleAiImagePrompt covers all hand defect constraints", () => {
  for (const keyword of [
    "描述中的动作决定手部数量",
    "单手动作",
    "双手动作",
    "手捧、手端、手托",
    "绝对禁止第三只手",
    "必须且只能有五根手指",
    "不多不少",
    "第六根手指",
    "七根手指",
    "手指分叉",
    "六指",
    "七指",
    "NO extra fingers",
    "NO sixth finger",
    "NO missing fingers",
    "NO four fingers",
    "NO fused fingers",
    "NO webbed fingers",
    "严禁从画面外伸出额外的第三只手",
    "再次强调",
    "第三只手",
    "多余的手",
    "多余的手臂",
    "五根完整",
    "手指数量精确为五根",
    "手掌完整无残缺",
    "两只手轮廓清晰",
    "不得交叠、粘连、融合或互相穿插",
    "双手交叠",
    "双手粘连",
    "双手融合",
    "手指交叉缠绕",
    "手指互相穿插",
    "双手边界模糊",
    "NO merged hands",
    "NO overlapping hands",
    "NO tangled fingers",
    "NO interlocked fingers",
    "NO conjoined hands",
    "NO blurred hand boundaries",
    "不得相互穿模",
    "多指",
    "缺指",
    "手指不全",
    "手指粘连",
    "手掌残缺",
    "畸形手",
    "坏解剖",
    "NO extra hands",
    "NO third hand",
    "NO more than two hands",
    "NO multiple hands",
    "NO additional hands",
    "NO duplicate hands",
    "NO extra arms",
    "extra fingers",
    "missing fingers",
    "fused fingers",
    "deformed hand",
    "mutated hand",
    "bad anatomy",
    "clipping artifacts",
  ]) {
    assert.ok(
      HAND_ANATOMY_SYSTEM_PROMPT.includes(keyword),
      `system prompt must contain: ${keyword}`
    );
  }
});

test("assembleAiImagePrompt is deterministic", () => {
  const user = "紫色渐变长甲";
  assert.equal(assembleAiImagePrompt(user), assembleAiImagePrompt(user));
});

test("assembleAiImageEditPrompt keeps reference image, changes only nails", () => {
  const user = "银色亮片渐变";
  const assembled = assembleAiImageEditPrompt(user);
  const prefixIndex = assembled.indexOf(IMAGE_EDIT_PREFIX);
  const userIndex = assembled.indexOf(user);
  const suffixIndex = assembled.indexOf(AI_IMAGE_EDIT_SUFFIX);
  const systemIndex = assembled.indexOf(IMAGE_EDIT_SYSTEM_PROMPT);
  assert.ok(prefixIndex === 0, "image-edit prefix must come first");
  assert.ok(userIndex > prefixIndex, "user prompt must follow the prefix");
  assert.ok(suffixIndex > userIndex, "edit suffix must follow user prompt");
  assert.ok(systemIndex > suffixIndex, "image-edit system prompt must follow suffix");
  assert.ok(assembled.endsWith(IMAGE_EDIT_SYSTEM_PROMPT));
  // 图生图前缀必须要求以参考图为唯一基准、保持结构、只改指甲
  assert.ok(IMAGE_EDIT_PREFIX.includes("以用户上传的参考图为唯一基准"));
  assert.ok(IMAGE_EDIT_PREFIX.includes("保持手部数量"));
  assert.ok(IMAGE_EDIT_PREFIX.includes("只针对参考图中可见的指甲区域进行美甲修改"));
  // 内置风格提示词自带"生活照/捧着茶杯/柔焦光线/美颜风格"等场景描述，图生图必须先声明忽略
  assert.ok(IMAGE_EDIT_PREFIX.includes("一律忽略"));
  assert.ok(IMAGE_EDIT_PREFIX.includes("只提取其中的美甲设计信息"));
  // 图生图路径不得使用文生图系统提示词（第二套独立）
  assert.ok(!assembled.includes(HAND_ANATOMY_SYSTEM_PROMPT));
  // 图生图路径不得携带文生图场景后缀：它是"重新构图成手部特写"的指令来源
  assert.ok(
    !assembled.includes(AI_IMAGE_SCENE_SUFFIX),
    "image-edit prompt must not reuse the text-to-image scene suffix"
  );
  assert.ok(!assembled.includes("close-up hand photo"));
  // 确定性
  assert.equal(assembleAiImageEditPrompt(user), assembleAiImageEditPrompt(user));
});

test("extractNailDesign strips built-in style scene sentences before image editing", () => {
  const stylePrompt =
    "展现甜美少女风美甲的女性手部近景生活照。浅粉色底色、白色法式指尖的短杏仁甲。" +
    "装饰有精致的3D白色树脂蝴蝶结、手工点缀的微型白珍珠和细微的银色星星闪粉。" +
    "双手自然地捧着一个复古瓷茶杯。温暖、柔焦的美学光线，温馨的背景。" +
    "带有柔光细节的自然手部肌肤，精致美颜风格。";
  const design = extractNailDesign(stylePrompt);
  for (const kept of ["浅粉色底色", "白色法式指尖的短杏仁甲", "3D白色树脂蝴蝶结", "银色星星闪粉"]) {
    assert.ok(design.includes(kept), `design sentence must be kept: ${kept}`);
  }
  for (const dropped of ["生活照", "捧着", "瓷茶杯", "柔焦", "背景", "肌肤", "美颜"]) {
    assert.ok(!design.includes(dropped), `scene sentence must be stripped: ${dropped}`);
  }
  // 纯设计输入原样保留
  assert.equal(extractNailDesign("银色亮片渐变"), "银色亮片渐变");
  // 组装的图生图提示词里不得再出现内置场景句
  const assembled = assembleAiImageEditPrompt(stylePrompt);
  assert.ok(!assembled.includes("复古瓷茶杯"));
  assert.ok(!assembled.includes("温馨的背景"));
  assert.ok(assembled.includes("浅粉色底色"));
});

test("AI_IMAGE_EDIT_SUFFIX pins composition, background, lighting and skin", () => {
  for (const keyword of [
    "only apply the described design on the nail surfaces that already exist",
    "keep the original composition, framing, crop, camera angle, perspective",
    "background objects, props",
    "lighting direction and intensity",
    "color temperature, white balance",
    "depth of field",
    "skin texture",
    "构图、取景、画幅与裁剪",
    "机位与透视",
    "背景物件与道具",
    "光线方向与强度",
    "色温与白平衡",
    "景深与虚化",
    "皮肤质感",
  ]) {
    assert.ok(
      AI_IMAGE_EDIT_SUFFIX.includes(keyword),
      `image-edit suffix must contain: ${keyword}`
    );
  }
  assert.ok(!AI_IMAGE_EDIT_SUFFIX.includes("close-up hand photo"));
  assert.ok(!AI_IMAGE_EDIT_SUFFIX.includes("beautiful"));
});

test("IMAGE_EDIT_SYSTEM_PROMPT is a dedicated second system prompt for reference-image editing", () => {
  // 核心要求：以参考图为底图、只改指甲、其余细节原样保留
  for (const keyword of [
    "唯一底图",
    "禁止重新生成整幅画面",
    "唯一允许修改的区域是指甲",
    "美甲设计（底色、花纹、装饰、甲型效果只体现在指甲区域）",
    "原样保留",
    "手部姿势与动作手势",
    "皮肤纹理与肤质肤色",
    "服装与配饰",
    "背景场景",
    "光线与阴影",
    "构图与拍摄角度",
    "改变手势或动作",
    "改变背景场景",
    "改变肤色或皮肤纹理",
    "整体风格重绘",
    "NO changing pose",
    "NO changing skin texture",
    "NO changing background",
    "NO style transfer of the whole image",
    "only edit the nails",
    // 着重强调：以参考图为基准做针对性修改
    "唯一基准",
    "针对性",
    "一律忽略",
    "它们描述的是另一幅画面，不是本图的修改依据",
    "针对参考图中实际存在的内容进行",
    "禁止新增或删除指甲",
    "禁止改变指甲的数量、大小与位置",
    "NO adding nails",
    "NO removing nails",
    "all edits must be targeted and based on the reference image",
    // 保底：基本条件正常（手指以参考图实际可见为准、无畸形、无穿模）
    "基本条件正常",
    "手指数量严格以参考图实际可见为准",
    "不得增减、补全或重排",
    "手部与道具、场景不得相互穿模",
    // 环境元素严格保留：画幅、色温、景深、禁止美化
    "画幅与裁剪比例",
    "色温与白平衡",
    "改变景深或虚化背景",
    "禁止美化与重绘",
    "禁止磨皮、美颜、锐化、HDR、滤镜、色彩分级、风格迁移、背景虚化或替换、重新打光、重新构图、重新取景",
    "NO recomposing, NO reframing, NO cropping change, NO aspect-ratio change",
    "NO relighting, NO white-balance shift",
    "NO skin smoothing, NO beautify filter, NO background blur, NO background replacement",
    "NO adding or removing background objects",
  ]) {
    assert.ok(
      IMAGE_EDIT_SYSTEM_PROMPT.includes(keyword),
      `image-edit system prompt must contain: ${keyword}`
    );
  }
  // 与文生图系统提示词完全独立（不共享、不包含对方主体）
  assert.notEqual(IMAGE_EDIT_SYSTEM_PROMPT, HAND_ANATOMY_SYSTEM_PROMPT);
  assert.ok(!IMAGE_EDIT_SYSTEM_PROMPT.includes("描述中的动作决定手部数量"));
});

test("HAND_ANATOMY_SYSTEM_PROMPT covers the eight hand-fidelity dimensions", () => {
  // 用户要求的第一套八类维度：手数量/手模型/手形态/无穿模/手指数量/手指状态/手指关系/场景遮挡
  for (const keyword of [
    "一、手数量正常",
    "二、手模型正常",
    "三、手形态正常",
    "四、手无穿模或被穿模",
    "五、手指数量正常",
    "六、手指状态正常",
    "七、手指关系正常",
    "八、场景遮挡正常",
    "场景物体不得穿过手部",
    "手部也不得穿过场景物体",
    "手指之间的位置与从属关系自然正确",
    "遮挡关系必须正确、合理、符合透视",
    "手部被场景错误裁切或穿透",
    "NO clipping",
    "NO interpenetration",
  ]) {
    assert.ok(
      HAND_ANATOMY_SYSTEM_PROMPT.includes(keyword),
      `text-to-image system prompt must contain: ${keyword}`
    );
  }
});

test("两套提示词互斥：系统按是否上传参考图仅启用其中一套，绝不同时发送", () => {
  const user = "银色亮片渐变";
  const textAssembled = assembleAiImagePrompt(user);
  const editAssembled = assembleAiImageEditPrompt(user);
  // 第一套（文生图）只含第一套内容，不得包含第二套任何片段
  assert.ok(textAssembled.includes(HAND_COUNT_PREFIX));
  assert.ok(textAssembled.includes(HAND_ANATOMY_SYSTEM_PROMPT));
  assert.ok(!textAssembled.includes(IMAGE_EDIT_PREFIX), "text path must not contain the image-edit prefix");
  assert.ok(!textAssembled.includes(IMAGE_EDIT_SYSTEM_PROMPT), "text path must not contain the image-edit system prompt");
  // 第二套（图生图）只含第二套内容，不得包含第一套任何片段
  assert.ok(editAssembled.includes(IMAGE_EDIT_PREFIX));
  assert.ok(editAssembled.includes(IMAGE_EDIT_SYSTEM_PROMPT));
  assert.ok(!editAssembled.includes(HAND_COUNT_PREFIX), "image-edit path must not contain the hand-count prefix");
  assert.ok(!editAssembled.includes(HAND_ANATOMY_SYSTEM_PROMPT), "image-edit path must not contain the text-to-image system prompt");
});
