"""同尺寸ROI确定性避开已注册角标；只接收候选几何，不接收真值。"""
import math

POLICY = {
    'version': 1,
    'scope': 'development_input_geometry_only_registered_marker_metadata_not_production_marker_detection',
    'cropSize': 'preserve_original_width_height_context045',
    'anchor': 'native_candidate_box_union_original_roi_visible_coarse_mask_bbox',
    'obstacles': 'registered_marker_boxes_expanded10_clamped_to_image',
    'objective': 'minimum_integer_dx_squared_plus_dy_squared',
    'tieBreak': 'L1_absdy_dy_dx_newtop_newleft',
    'noIntersection': 'original_crop_byte_geometry_unchanged',
    'infeasible': 'explicit_unreachable_no_resize_no_empty_target_no_coarse_fallback',
    'truthCoordinatesAllowed': False,
}


def overlap_area(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _rect(box, width, height):
    if len(box) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) and int(v) == v for v in box):
        raise ValueError('integer native rectangle required')
    x0, y0, x1, y1 = map(int, box)
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError('native rectangle outside image or empty')
    return x0, y0, x1, y1


def translate_crop(crop, anchor_box, marker_halos, width, height):
    """精确求整像素平移最小值；半开矩形边界接触允许，正面积交叠禁止。"""
    if not isinstance(width, int) or not isinstance(height, int) or min(width, height) < 1:
        raise ValueError('positive integer image size required')
    crop = _rect(crop, width, height)
    anchor = _rect(anchor_box, width, height)
    halos = [_rect(b, width, height) for b in marker_halos]
    if not any(overlap_area(crop, h) for h in halos):
        return {'decision': 'unchanged', 'cropBox': list(crop), 'translation': [0, 0]}
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    # 保留候选框和原裁片可见粗mask；不读取真值决定位置。
    lo_x, hi_x = max(0, anchor[2] - cw), min(width - cw, anchor[0])
    lo_y, hi_y = max(0, anchor[3] - ch), min(height - ch, anchor[1])
    if lo_x > hi_x or lo_y > hi_y:
        return {'decision': 'unreachable', 'cropBox': None, 'translation': None}
    clamp_x = lambda x: min(max(x, lo_x), hi_x)
    clamp_y = lambda y: min(max(y, lo_y), hi_y)
    # 可行域是矩形域减去若干开矩形。最近点的每个坐标只能在
    # 原点投影、域边或障碍边上；笛卡尔积覆盖全部最优候选。
    xs = {lo_x, hi_x, clamp_x(crop[0])}
    ys = {lo_y, hi_y, clamp_y(crop[1])}
    for h in halos:
        xs.update((clamp_x(h[0] - cw), clamp_x(h[2])))
        ys.update((clamp_y(h[1] - ch), clamp_y(h[3])))
    feasible = []
    for x in xs:
        for y in ys:
            box = (x, y, x + cw, y + ch)
            if any(overlap_area(box, h) for h in halos):
                continue
            dx, dy = x - crop[0], y - crop[1]
            rank = (dx * dx + dy * dy, abs(dx) + abs(dy), abs(dy), dy, dx, y, x)
            feasible.append((rank, box, dx, dy))
    if not feasible:
        return {'decision': 'unreachable', 'cropBox': None, 'translation': None}
    _, box, dx, dy = min(feasible)
    return {'decision': 'translated', 'cropBox': list(box), 'translation': [dx, dy]}
