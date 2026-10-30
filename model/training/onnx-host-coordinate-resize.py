"""主机float32坐标与末级分段插值；保留卷积、归一化、权重及可逆图证据。"""
import copy
import hashlib

import numpy as np
import onnx
from onnx import helper, numpy_helper

PREFIX = '__host_resize_v1_'
TARGETS = ['/Resize', '/Resize_1', '/Resize_2', '/Resize_3']
FACTORS = [(16, 8, 64), (8, 4, 64), (4, 2, 64), (2, 1, 32)]


def axis_coordinates(incoming, outgoing):
    """float32逆比例；乘加在float64精确计算后只舍入一次为float32。"""
    if not 1 <= incoming <= outgoing <= 1536:
        raise ValueError('native coordinate domain')
    ratio = np.float32(incoming / outgoing)
    position = np.maximum(((np.arange(outgoing, dtype=np.float64) + .5) * float(ratio) - .5).astype(np.float32), np.float32(0))
    floor = np.floor(position).astype(np.int64)
    lower = np.minimum(floor, incoming - 1)
    upper = np.minimum(lower + 1, incoming - 1)
    weight1 = (position - floor.astype(np.float32)).astype(np.float32)
    weights = np.stack([np.float32(1) - weight1, weight1])
    indices = np.stack([lower, upper])
    if not ((indices >= 0).all() and (indices < incoming).all() and np.array_equal(weights.sum(0), np.ones(outgoing, np.float32))):
        raise ValueError('coordinate bounds/weights')
    return indices, weights


def coordinates(h, w):
    """16个输入：每个Resize各两轴的[lower,upper]与[weight0,weight1]。"""
    result, rows = {}, []
    for k, (source, target, channels) in enumerate(FACTORS):
        for axis, dim in [('y', h), ('x', w)]:
            indices, weights = axis_coordinates(dim // source, dim // target)
            original_indices, original_weights = indices.copy(), weights.copy()
            if k == 3:
                length = dim
                positions = (np.concatenate([np.arange(length*j//4-1, length*(j+1)//4+1) for j in range(4)]) if axis == 'y' else np.arange(-1, length+1))
                valid = (positions >= 0) & (positions < length)
                clipped = positions.clip(0, length-1)
                indices = indices[:, clipped]
                weights = weights[:, clipped] * valid[None, :]
                if axis == 'y':
                    restored_i = np.concatenate([indices[:, length*j//4+2*j+1:length*(j+1)//4+2*j+1] for j in range(4)], axis=1)
                    restored_w = np.concatenate([weights[:, length*j//4+2*j+1:length*(j+1)//4+2*j+1] for j in range(4)], axis=1)
                else:
                    restored_i, restored_w = indices[:, 1:-1], weights[:, 1:-1]
                if not np.array_equal(restored_i, original_indices) or not np.array_equal(restored_w, original_weights):
                    raise ValueError('complete coordinate inverse mapping')
            for field, value in [('indices', indices), ('weights', weights)]:
                name = PREFIX + f'{k}_{axis}_{field}'
                result[name] = np.ascontiguousarray(value)
            rows.append(dict(resize=k, axis=axis, incoming=dim//source, outgoing=dim//target, packedLength=indices.shape[1],
                             indicesSha256=hashlib.sha256(indices.tobytes()).hexdigest(), weightsSha256=hashlib.sha256(weights.tobytes()).hexdigest(),
                             completeOriginalPositions=dim//target, lowerUpperInBounds=True, interiorWeightsSumOne=True, inverseExact=True,
                             paddingWeightsZero=k == 3))
    return result, rows


def transform(original):
    if [v.name for v in original.graph.input] != ['candidate']:
        raise ValueError('frozen candidate interface')
    nodes = {n.name: n for n in original.graph.node}
    if len(nodes) != len(original.graph.node) or any(t not in nodes for t in TARGETS):
        raise ValueError('unique four Resize nodes')
    model = copy.deepcopy(original)
    for k in range(4):
        for axis in ['y', 'x']:
            for field, dtype in [('indices', onnx.TensorProto.INT64), ('weights', onnx.TensorProto.FLOAT)]:
                model.graph.input.append(helper.make_tensor_value_info(PREFIX+f'{k}_{axis}_{field}', dtype, [2, f'coord_{k}_{axis}']))
    last = nodes[TARGETS[-1]]
    consumers = [n for n in original.graph.node if last.output[0] in n.input]
    if len(consumers) != 1 or consumers[0].op_type != 'Concat' or helper.get_attribute_value(consumers[0].attribute[0]) != 1:
        raise ValueError('last resize sole channel concat')
    concat = consumers[0]
    if concat.input[0] != last.output[0]:
        raise ValueError('resize first concat operand')
    skip = concat.input[1]
    users = [n for n in original.graph.node if concat.output[0] in n.input]
    if sorted(n.op_type for n in users) != ['Pad', 'Shape']:
        raise ValueError('partitioned decoder shape/pad only')
    pad = next(n for n in users if n.op_type == 'Pad')
    shape_node = next(n for n in users if n.op_type == 'Shape')
    slabs = [n for n in original.graph.node if pad.output[0] in n.input]
    if len(slabs) != 4 or any(n.op_type != 'Slice' or len(n.input) != 5 for n in slabs):
        raise ValueError('four exact halo slabs')
    slab_names = {n.name: j for j, n in enumerate(slabs)}
    initial_count = len(model.graph.initializer)
    if any(n.name.startswith(PREFIX) for n in original.graph.node) or any(v.name.startswith(PREFIX) for v in original.graph.initializer):
        raise ValueError('prefix collision')
    out, edits = [], []
    serial = 0

    def constant(name, value, dtype=np.int64):
        key = PREFIX + name
        if any(v.name == key for v in model.graph.initializer):
            return key
        model.graph.initializer.append(numpy_helper.from_array(np.asarray(value, dtype), name=key))
        return key

    def op(kind, inputs, label, output=None, **attrs):
        nonlocal serial
        serial += 1
        key = PREFIX + f'{serial}_{label}'
        target = output or key
        out.append(helper.make_node(kind, inputs, [target], name=key, **attrs))
        return target

    zero = constant('zero', 0)
    one = constant('one', 1)
    axes2 = constant('axes2', [2])
    axes1 = constant('axes1', [1])
    axes0 = constant('axes0', [0])
    weight_axes = {'y': constant('weight_y_axes', [0, 1, 3]), 'x': constant('weight_x_axes', [0, 1, 2])}

    def fields(k, axis, start=None, end=None):
        values = []
        for field in ['indices', 'weights']:
            source = PREFIX + f'{k}_{axis}_{field}'
            for side, side_ref in [(0, zero), (1, one)]:
                value = op('Gather', [source, side_ref], f'{k}_{axis}_{field}_{side}', axis=0)
                if start is not None:
                    value = op('Slice', [value, start, end, axes0, constant('step', [1])], 'coordinate_slab')
                if field == 'weights':
                    value = op('Unsqueeze', [value, weight_axes[axis]], 'weight_broadcast')
                values.append(value)
        return values

    def interpolate(k, source, output=None, start=None, end=None):
        y0, y1, wy0, wy1 = fields(k, 'y', start, end)
        x0, x1, wx0, wx1 = fields(k, 'x')
        top = op('Gather', [source, y0], 'top', axis=2)
        bottom = op('Gather', [source, y1], 'bottom', axis=2)
        a00 = op('Gather', [top, x0], 'a00', axis=3)
        a01 = op('Gather', [top, x1], 'a01', axis=3)
        a10 = op('Gather', [bottom, x0], 'a10', axis=3)
        a11 = op('Gather', [bottom, x1], 'a11', axis=3)
        tv = op('Add', [op('Mul', [wx0, a00], 'a00w'), op('Mul', [wx1, a01], 'a01w')], 'top_value')
        bv = op('Add', [op('Mul', [wx0, a10], 'a10w'), op('Mul', [wx1, a11], 'a11w')], 'bottom_value')
        return op('Add', [op('Mul', [wy0, tv], 'top_part'), op('Mul', [wy1, bv], 'bottom_part')], 'interpolated', output)

    for index, node in enumerate(original.graph.node):
        changed = node.name in TARGETS or node.name in slab_names or node.name in [concat.name, pad.name, shape_node.name]
        if changed:
            edits.append(dict(index=index, originalHex=node.SerializeToString().hex()))
        if node.name in TARGETS:
            k = TARGETS.index(node.name)
            attrs = {a.name: helper.get_attribute_value(a) for a in node.attribute}
            if node.op_type != 'Resize' or attrs != dict(coordinate_transformation_mode=b'half_pixel', cubic_coeff_a=-.75, mode=b'linear', nearest_mode=b'floor'):
                raise ValueError('frozen bilinear half_pixel attributes')
            if k < 3:
                interpolate(k, node.input[0], node.output[0])
        elif node.name in [concat.name, pad.name]:
            continue
        elif node.name == shape_node.name:
            op('Shape', [skip], 'skip_shape', node.output[0])
        elif node.name in slab_names:
            j = slab_names[node.name]
            # 原Slice界限位于已pad域；还原到未pad域并保留整张图的边缘零填充。
            start = node.input[1]
            end = node.input[2]
            shift = constant(f'shift_{j}', [2*j])
            cs = op('Add', [start, shift], 'packed_start')
            ce = op('Add', [end, shift], 'packed_end')
            resized = interpolate(3, last.input[0], start=cs, end=ce)
            ss = start if j == 0 else op('Sub', [start, constant('ones', [1])], 'skip_start')
            se = op('Sub', [end, constant('ones' if j == 3 else 'twos', [1] if j == 3 else [2])], 'skip_end')
            # 对内部块保留前后各一行；end=bound+2，未pad域尾界为bound+1。
            if j < 3:
                se = op('Sub', [end, constant('ones', [1])], 'skip_end_halo')
            skip_slab = op('Slice', [skip, ss, se, axes2, constant('step', [1])], 'skip_slab')
            pads = constant(f'skip_pads_{j}', [0, 0, int(j == 0), 1, 0, 0, int(j == 3), 1])
            padded = op('Pad', [skip_slab, pads, constant('float_zero', 0, np.float32)], 'skip_padded')
            op('Concat', [resized, padded], 'joined_slab', node.output[0], axis=1)
        else:
            out.append(copy.deepcopy(node))
    del model.graph.node[:]
    model.graph.node.extend(out)
    proof = dict(originalSha256=hashlib.sha256(original.SerializeToString()).hexdigest(), originalInputs=len(original.graph.input),
                 originalInitializers=initial_count, edits=edits, addedInputCount=16, fourResizeNames=TARGETS,
                 streamedDecoderSlabs=[n.name for n in slabs], changedNonResizeConsumers=[concat.name, pad.name, shape_node.name, *slab_names],
                 originalInitializerBytesUnchanged=True, fusedArithmeticNotGuaranteed=True)
    if restore(model, proof).SerializeToString() != original.SerializeToString():
        raise ValueError('reconstruction_mismatch')
    onnx.checker.check_model(model, full_check=True)
    return model, proof


def restore(model, proof):
    restored = copy.deepcopy(model)
    keep = iter(n for n in model.graph.node if not n.name.startswith(PREFIX))
    edits = {r['index']: onnx.NodeProto.FromString(bytes.fromhex(r['originalHex'])) for r in proof['edits']}
    count = sum(not n.name.startswith(PREFIX) for n in model.graph.node) + len(edits)
    nodes = [edits[i] if i in edits else copy.deepcopy(next(keep)) for i in range(count)]
    del restored.graph.node[:]
    restored.graph.node.extend(nodes)
    del restored.graph.input[proof['originalInputs']:]
    del restored.graph.initializer[proof['originalInitializers']:]
    return restored
