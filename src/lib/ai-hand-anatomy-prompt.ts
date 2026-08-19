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
  "以用户上传的参考图为唯一基准：保持手部数量、每只手恰好五根手指、手部姿势、手掌形状、肤色、服装与背景完全不变，只针对参考图中可见的指甲区域进行美甲修改。以下内容为美甲设计描述：";

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
  "二、修改范围：唯一允许修改的区域是指甲——在参考图每枚可见指甲上绘制用户描述的美甲设计（底色、花纹、装饰、甲型效果只体现在指甲区域）；禁止新增或删除指甲，禁止改变指甲的数量、大小与位置。" +
  "三、基本条件正常（底线）：修改过程中手指数量保持每只手恰好五根，不得出现多指、缺指、手指粘连、手指畸形、额外的手、第三只手或任何手部缺陷；手部与道具、场景不得相互穿模。" +
  "四、原样保留：指甲以外的所有内容必须原样保留、禁止任何改动——手部数量与每只手五根手指的结构、手部姿势与动作手势、手掌与手指轮廓、皮肤纹理与肤质肤色、血管、汗毛、服装与配饰（戒指、手链、手表等）、道具、背景场景、光线与阴影、构图与拍摄角度、画面中的其它任何物体与身体部位。" +
  "五、禁止事项：重新绘制手部、改变手势或动作、改变手指数量、多指、缺指、手指粘连、手指畸形、额外的手、第三只手、多余的手臂、改变服装配饰、改变背景场景、改变肤色或皮肤纹理、改变光照阴影、移动或增减画面物体、整体风格重绘、把美甲设计应用到指甲以外的区域、在指甲周围产生新的笔触或涂抹。" +
  "NO extra fingers, NO missing fingers, NO fused fingers, NO webbed fingers, NO extra hands, NO third hand, " +
  "NO extra arms, NO changing pose, NO changing gesture, NO changing skin texture, NO changing skin color, " +
  "NO changing clothing, NO changing accessories, NO changing background, NO changing lighting, NO changing composition, " +
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
 * 参考图保持前置约束 → 用户提示词 → 美甲场景后缀 → 第二套图生图系统提示词（用户不可见）。
 * 第二套系统提示词与文生图完全独立：保持参考图的场景、动作、皮肤纹理等
 * 一切细节不变，只修改指甲区域。
 */
export function assembleAiImageEditPrompt(userPrompt: string): string {
  return `${IMAGE_EDIT_PREFIX}${userPrompt}, ${AI_IMAGE_SCENE_SUFFIX}. ${IMAGE_EDIT_SYSTEM_PROMPT}`;
}
