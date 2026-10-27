/**
 * AI 生图隐藏系统提示词（用户不可见）。
 *
 * 目的：底层生图模型对手部细节容易产生多指、缺指、手指粘连、手掌残缺、
 * 畸形、穿模、多只手等缺陷。发送请求时在用户提示词之前注入简短的手数量
 * 约束（前置），并在末尾附加完整解剖约束（后置），双保险约束模型输出
 * 解剖结构正确的手部，提升美甲场景的出图可用率。
 */

export const HAND_ANATOMY_SYSTEM_PROMPT =
  "手部生成必须满足以下全部要求：" +
  "一、手数量正常：描述中的动作决定手部数量——手持、手拿、手捏、手举、手指轻触等单手动作时，" +
  "画面中只出现一只手；手捧、手端、手托、双手合握、双手捧着等双手动作时，" +
  "画面中只出现两只手；绝对禁止第三只手。" +
  "手捧、手持、触摸道具（如茶杯、花束、糖果、手机等）时，" +
  "道具只能由画面中可见的这（两）只手接触，" +
  "严禁从画面外伸出额外的第三只手，也不得在画面内凭空出现多余的手。" +
  "二、手模型正常：手掌完整无残缺、无多余组织；手掌与手指比例协调、指关节位置正确；" +
  "不得出现畸形手、坏解剖、肢体变形、比例失调、肢体穿插穿模。" +
  "三、手形态正常：手部姿势自然放松，透视与光线正确；" +
  "双手场景中两只手轮廓清晰、彼此分离，不得交叠、粘连、融合或互相穿插；" +
  "两只手的皮肤、手指与指甲必须边界分明，不得混成一体。" +
  "四、手无穿模或被穿模：手与指甲、饰品、道具之间不得相互穿模、穿插或重叠变形；" +
  "场景物体不得穿过手部，手部也不得穿过场景物体。" +
  "五、手指数量正常：每只手必须且只能有五根手指（一根拇指与四根手指），" +
  "不多不少，绝对禁止第六根手指、七根手指或任何数量错误的手指。" +
  "六、手指状态正常：每只手恰好五根完整、清晰、独立、自然弯曲的手指（一根拇指与四根手指），" +
  "手指数量精确为五根、形态分明、互不粘连、不分叉；手指粗细长短比例自然协调。" +
  "七、手指关系正常：手指之间的位置与从属关系自然正确，不得交叉缠绕、互相穿插、重叠变形；" +
  "手指与手掌的连接关系正确，指关节位置正确。" +
  "八、场景遮挡正常：手部与场景元素（道具、衣物、背景物体等）的遮挡关系必须正确、合理、符合透视；" +
  "禁止错误的遮挡、物体从手部中间穿过、手部被场景错误裁切或穿透。" +
  "再次强调：每只手恰好五根手指（一根拇指与四根手指），" +
  "绝不出现第六根手指、七根手指或缺失的手指；" +
  "整个画面严禁出现第三只手、多余的手部、多余的手臂或任何多余的肢体。" +
  "严禁出现任何手部缺陷：多指、六指、七指、缺指、手指不全、手指粘连、手指分叉、手掌残缺、畸形手、坏解剖、肢体变形、比例失调、肢体穿插穿模、双手交叠、双手粘连、双手融合、手指交叉缠绕、手指互相穿插、双手边界模糊、多余的手、多余的手臂、第三只手。" +
  "禁止：NO extra fingers, NO sixth finger, NO missing fingers, NO four fingers, NO fused fingers, NO webbed fingers, NO extra hands, NO third hand, NO more than two hands, NO multiple hands, NO additional hands, NO duplicate hands, NO merged hands, NO overlapping hands, NO tangled fingers, NO interlocked fingers, NO conjoined hands, NO blurred hand boundaries, NO extra arms, NO clipping, NO interpenetration, deformed hand, mutated hand, bad anatomy, disfigured hand, malformed fingers, extra digits, missing digits, amputated hand, extra limbs, body horror, clipping artifacts.";

/** 美甲场景固定后缀（原有，保持向后兼容）。 */
export const AI_IMAGE_SCENE_SUFFIX =
  "nail art design on fingernails, manicure, close-up hand photo, beautiful, high detail";

/**
 * 图生图专用后缀（不可与 `AI_IMAGE_SCENE_SUFFIX` 混用）。
 *
 * `AI_IMAGE_SCENE_SUFFIX` 是文生图场景描述（"close-up hand photo, beautiful,
 * high detail"），在图生图里会被模型当成重新构图的指令——把参考图重绘成"手部
 * 特写"，从而改变取景、背景、光线与皮肤质感。图生图必须改用本后缀：只描述
 * 指甲上的设计，其余一律保持原样。
 */
export const AI_IMAGE_EDIT_SUFFIX =
  "only apply the described design on the nail surfaces that already exist in the reference photo; " +
  "keep the original composition, framing, crop, camera angle, perspective, background objects, props, " +
  "lighting direction and intensity, shadows, color temperature, white balance, depth of field and skin texture exactly as they are; " +
  "仅在参考图原有的指甲上呈现上述美甲设计，照片的构图、取景、画幅与裁剪、机位与透视、背景物件与道具、" +
  "光线方向与强度、阴影、色温与白平衡、景深与虚化、皮肤质感全部保持原样。";

/**
 * 场景/人物/道具/光线/肤质/风格类短语（命中即整句丢弃）。
 *
 * 依据：`src/lib/ai-style-prompts.ts` 的内置风格提示词是完整文生图场景描述
 * （"女性手部近景生活照"、"双手自然地捧着一个复古瓷茶杯"、"温暖、柔焦的
 * 美学光线，温馨的背景"、"精致美颜风格"）。这类句子在图生图里会直接命令
 * 模型重绘背景、道具与光线，实测会把参考图整幅换成"捧茶杯的温馨客厅"。
 * 仅靠系统提示词声明"忽略"不足以对抗具体正向描述，必须在发送前剥离。
 */
const SCENE_PHRASES = [
  "生活照", "照片", "镜头", "特写", "近景", "微距", "视角", "画面", "构图", "拍摄",
  "背景", "虚化", "光斑", "光线", "光影", "灯光", "阳光", "晨光", "午后", "逆光", "柔焦", "光效",
  "滤镜", "美颜", "美肤",
  "肌肤", "皮肤", "白皙", "细腻", "柔嫩", "光滑", "水润", "通透", "无瑕", "柔光",
  "风格照", "梦幻", "清新", "甜美", "温馨", "氛围",
  "双手", "单手", "手捧", "手拿", "手端", "手托", "捧着", "端着", "拿着", "举着", "握着", "夹着",
  "搭在", "翻开", "轻拂", "轻触", "轻托", "夹着", "托着", "撑在",
] as const;

/**
 * 从用户提示词中提取「指甲设计」部分：按句切分后丢弃场景/道具/光线/肤质句，
 * 只保留描述底色、图案、装饰与甲型的句子。
 *
 * 全部句子都被判定为场景时退回原提示词（避免把用户的简短设计词误删成空）。
 */
export function extractNailDesign(userPrompt: string): string {
  const sentences = userPrompt
    .split(/(?<=[。；;！!？?\n])/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
  const design = sentences.filter(
    (sentence) => !SCENE_PHRASES.some((phrase) => sentence.includes(phrase))
  );
  const joined = design.join("").replace(/[。；;！!？?\s]+$/u, "").trim();
  return joined || userPrompt.trim();
}

/**
 * 前置手数量约束（简短、醒目）。部分生图模型对提示词开头的约束更敏感，
 * 因此在用户提示词之前注入一句最短的手数量与手指数约束；完整约束仍附在末尾。
 */
export const HAND_COUNT_PREFIX =
  "画面中只能出现一只手（单手场景）或最多两只手（双手场景），绝对禁止第三只手；每只手恰好五根手指，不多不少。以下内容为主题描述：";

/**
 * 图生图（参考图）前置约束：以用户上传的参考图为唯一基准，保持手部数量、
 * 姿势与结构完全不变，只针对参考图中可见的指甲区域进行美甲修改。
 * 参考图可能是一只手或两只手，不重新规定数量。
 */
export const IMAGE_EDIT_PREFIX =
  "以用户上传的参考图为唯一基准：保持手部数量、参考图中实际可见的手指数量与形态、手部姿势、手掌形状、肤色、服装与背景完全不变，" +
  "不得为凑数补全、删减或重排被裁切、遮挡或出画的手指与指甲，只针对参考图中可见的指甲区域进行美甲修改，" +
  "不得改变构图、取景、画幅、机位与光线。" +
  "下列描述中若出现拍摄场景、画面类型、人物、道具、手势、背景、光线、滤镜或美肤等语句（如“生活照”“特写镜头”“手部近景”“捧着茶杯”“柔焦光线”“背景虚化”“美颜风格”），" +
  "一律忽略，不得据此改变参考图，只提取其中的美甲设计信息（底色、花纹、装饰、甲型）。以下内容为美甲设计描述：";

/**
 * 图生图（参考图）隐藏系统提示词——第二套系统提示词。
 *
 * 仅在用户上传参考图（走图生图）时启用，与文生图的 HAND_ANATOMY_SYSTEM_PROMPT
 * 完全独立。在保证基本条件正常（五指、无畸形、无穿模）的前提下，着重强调
 * 以用户上传的参考图为唯一基准进行针对性修改：唯一允许修改的区域是指甲，
 * 其余一切细节（场景、动作、皮肤纹理等）原样保留、禁止任何改动。
 */
export const IMAGE_EDIT_SYSTEM_PROMPT =
  "以用户上传的参考图为唯一底图和唯一基准，仅在其上做针对性的局部修改，禁止重新生成整幅画面。" +
  "一、基准唯一性：参考图中的手部数量、每只手的五根手指、每枚指甲的数量、大小、位置、形态与朝向、手部姿势、皮肤与场景全部以参考图为准；所有修改都必须针对参考图中实际存在的内容进行。" +
  "用户描述中涉及拍摄场景、画面类型、人物、道具、手势、背景、光线、滤镜与美肤的语句一律忽略——它们描述的是另一幅画面，不是本图的修改依据；只采纳其中关于指甲底色、花纹、装饰与甲型的内容。" +
  "二、修改范围：唯一允许修改的区域是指甲——在参考图每枚可见指甲上绘制用户描述的美甲设计（底色、花纹、装饰、甲型效果只体现在指甲区域）；禁止新增或删除指甲，禁止改变指甲的数量、大小与位置。" +
  "三、基本条件正常（底线）：手指数量严格以参考图实际可见为准，不得增减、补全或重排；不得出现多指、缺指、手指粘连、手指畸形、额外的手、第三只手或任何手部缺陷；手部与道具、场景不得相互穿模。" +
  "四、原样保留：指甲以外的所有内容必须原样保留、禁止任何改动——手部数量与手指结构、手部姿势与动作手势、手掌与手指轮廓、皮肤纹理与肤质肤色、血管、汗毛、服装与配饰（戒指、手链、手表等）、道具、背景场景及其数量位置材质与颜色（桌面、布料、植物、家具、墙面等）、光线与阴影（方向、强度）、色温与白平衡、景深与虚化、构图与拍摄角度、画幅与裁剪比例、画面中的其它任何物体与身体部位。" +
  "五、禁止事项：重新绘制手部、改变手势或动作、改变手指数量、多指、缺指、手指粘连、手指畸形、额外的手、第三只手、多余的手臂、改变服装配饰、改变背景场景、改变肤色或皮肤纹理、改变光照阴影、改变色温与白平衡、改变景深或虚化背景、改变画幅与裁剪、移动或增减画面物体、整体风格重绘、把美甲设计应用到指甲以外的区域、在指甲周围产生新的笔触或涂抹。" +
  "六、禁止美化与重绘：禁止磨皮、美颜、锐化、HDR、滤镜、色彩分级、风格迁移、背景虚化或替换、重新打光、重新构图、重新取景、改变画幅比例；除指甲区域外，任何位置都不得出现新的笔触、纹理、高光或阴影变化。" +
  "NO extra fingers, NO missing fingers, NO fused fingers, NO webbed fingers, NO extra hands, NO third hand, " +
  "NO extra arms, NO changing pose, NO changing gesture, NO changing skin texture, NO changing skin color, " +
  "NO changing clothing, NO changing accessories, NO changing background, NO changing lighting, NO changing composition, " +
  "NO recomposing, NO reframing, NO cropping change, NO aspect-ratio change, NO relighting, NO white-balance shift, " +
  "NO color grading, NO skin smoothing, NO beautify filter, NO background blur, NO background replacement, NO HDR, NO sharpening pass, " +
  "NO adding or removing background objects, " +
  "NO style transfer of the whole image, NO regenerating the hand, NO redrawing the scene, NO adding nails, NO removing nails, " +
  "only edit the nails; all edits must be targeted and based on the reference image.";

/**
 * 组装发送给生图模型的完整提示词（文生图）：
 * 前置手数量约束 → 用户提示词 → 美甲场景后缀 → 隐藏系统提示词（用户不可见）。
 */
export function assembleAiImagePrompt(userPrompt: string): string {
  return `${HAND_COUNT_PREFIX}${userPrompt}, ${AI_IMAGE_SCENE_SUFFIX}. ${HAND_ANATOMY_SYSTEM_PROMPT}`;
}

/**
 * 组装发送给生图模型的完整提示词（图生图，带参考图）：
 * 参考图保持前置约束 → 用户提示词 → 图生图专用后缀 → 第二套图生图系统提示词（用户不可见）。
 *
 * 注意：本条路径**不得**拼接 `AI_IMAGE_SCENE_SUFFIX`——那是文生图的场景描述
 * （"close-up hand photo, beautiful, high detail"），会把参考图当成重新构图的
 * 指令，导致背景、取景、光线与皮肤质感被重绘。
 */
export function assembleAiImageEditPrompt(userPrompt: string): string {
  return `${IMAGE_EDIT_PREFIX}${extractNailDesign(userPrompt)}, ${AI_IMAGE_EDIT_SUFFIX} ${IMAGE_EDIT_SYSTEM_PROMPT}`;
}
