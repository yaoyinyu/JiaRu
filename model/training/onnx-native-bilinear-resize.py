"""按Torch原尺寸half-pixel坐标顺序展开双线性插值，保留其余图与权重。"""
import onnx
import numpy as np
from onnx import helper, numpy_helper


def rewrite_model(model, node_names=('/Resize', '/Resize_1')):
    if not node_names or len(set(node_names)) != len(node_names):
        raise ValueError('unique target Resize nodes required')
    nodes = {n.name: n for n in model.graph.node}
    if len(nodes) != len(model.graph.node) or any(name not in nodes for name in node_names):
        raise ValueError('missing or duplicate target nodes')
    before = onnx.ModelProto(); before.CopyFrom(model)
    original_initializers = len(model.graph.initializer)
    replaced = []; updated = []
    for index, node in enumerate(model.graph.node):
        if node.name not in node_names:
            updated.append(node); continue
        attrs = {a.name: helper.get_attribute_value(a) for a in node.attribute}
        if node.op_type != 'Resize' or node.domain or len(node.input) != 4 or node.input[1] or node.input[2] or not node.input[3] or len(node.output) != 1:
            raise ValueError('only native 2D Resize with explicit sizes supported')
        if attrs.get('mode') != b'linear' or attrs.get('coordinate_transformation_mode') != b'half_pixel' or attrs.get('antialias', 0) or attrs.get('exclude_outside', 0) or 'axes' in attrs:
            raise ValueError('unsupported Resize semantics')
        prefix = f'native_bilinear_{index}_'
        existing = {t for n in model.graph.node for t in (*n.input, *n.output)} | {v.name for v in model.graph.initializer}
        if any(t.startswith(prefix) for t in existing):
            raise ValueError('new tensor name collision')

        def constant(name, value, dtype):
            key = prefix + name
            model.graph.initializer.append(numpy_helper.from_array(np.asarray(value, dtype=dtype), name=key))
            return key

        def op(kind, inputs, name, **attributes):
            output = prefix + name
            updated.append(helper.make_node(kind, inputs, [output], name=output, **attributes))
            return output

        zero_i = constant('zero_i', 0, np.int64); one_i = constant('one_i', 1, np.int64)
        zero_f = constant('zero_f', 0, np.float32); half = constant('half', .5, np.float32)
        one_f = constant('one_f', 1, np.float32)
        shape = op('Shape', [node.input[0]], 'input_shape')

        def coordinates(axis, name, broadcast_axes):
            axis_ref = constant(name + '_axis', axis, np.int64)
            incoming = op('Gather', [shape, axis_ref], name + '_input_size', axis=0)
            outgoing = op('Gather', [node.input[3], axis_ref], name + '_output_size', axis=0)
            in_f = op('Cast', [incoming], name + '_input_float', to=onnx.TensorProto.FLOAT)
            out_f = op('Cast', [outgoing], name + '_output_float', to=onnx.TensorProto.FLOAT)
            ratio = op('Div', [in_f, out_f], name + '_ratio')
            indices = op('Range', [zero_i, outgoing, one_i], name + '_indices')
            indices_f = op('Cast', [indices], name + '_indices_float', to=onnx.TensorProto.FLOAT)
            centered = op('Add', [indices_f, half], name + '_centers')
            scaled = op('Mul', [ratio, centered], name + '_scaled')
            shifted = op('Sub', [scaled, half], name + '_shifted')
            coordinate = op('Max', [shifted, zero_f], name + '_coordinate')
            floor = op('Floor', [coordinate], name + '_floor')
            lower = op('Cast', [floor], name + '_lower_raw', to=onnx.TensorProto.INT64)
            last = op('Sub', [incoming, one_i], name + '_last')
            lower = op('Min', [lower, last], name + '_lower')
            upper = op('Min', [op('Add', [lower, one_i], name + '_next'), last], name + '_upper')
            lower_f = op('Cast', [lower], name + '_lower_float', to=onnx.TensorProto.FLOAT)
            weight = op('Sub', [coordinate, lower_f], name + '_lambda1')
            complement = op('Sub', [one_f, weight], name + '_lambda0')
            axes = constant(name + '_broadcast_axes', broadcast_axes, np.int64)
            return lower, upper, op('Unsqueeze', [complement, axes], name + '_weight0'), op('Unsqueeze', [weight, axes], name + '_weight1')

        y0, y1, wy0, wy1 = coordinates(2, 'y', [0, 1, 3])
        x0, x1, wx0, wx1 = coordinates(3, 'x', [0, 1, 2])
        top = op('Gather', [node.input[0], y0], 'top', axis=2)
        bottom = op('Gather', [node.input[0], y1], 'bottom', axis=2)
        a00 = op('Gather', [top, x0], 'a00', axis=3); a01 = op('Gather', [top, x1], 'a01', axis=3)
        a10 = op('Gather', [bottom, x0], 'a10', axis=3); a11 = op('Gather', [bottom, x1], 'a11', axis=3)
        top_value = op('Add', [op('Mul', [wx0, a00], 'top0'), op('Mul', [wx1, a01], 'top1')], 'top_value')
        bottom_value = op('Add', [op('Mul', [wx0, a10], 'bottom0'), op('Mul', [wx1, a11], 'bottom1')], 'bottom_value')
        top_part = op('Mul', [wy0, top_value], 'top_part'); bottom_part = op('Mul', [wy1, bottom_value], 'bottom_part')
        updated.append(helper.make_node('Add', [top_part, bottom_part], list(node.output), name=prefix + 'output'))
        replaced.append({'node': node.name, 'input': node.input[0], 'sizes': node.input[3], 'output': node.output[0],
                         'math': 'float32 input/output ratio; ratio*(destination+0.5)-0.5; clamp; separable bilinear', 'prefix': prefix})
    if set(n['node'] for n in replaced) != set(node_names):
        raise ValueError('target count mismatch')
    del model.graph.node[:]; model.graph.node.extend(updated)
    added_prefixes = tuple(r['prefix'] for r in replaced)
    if [n.SerializeToString() for n in model.graph.node if not n.name.startswith(added_prefixes)] != [n.SerializeToString() for n in before.graph.node if n.name not in node_names]:
        raise ValueError('non-Resize nodes changed')
    # 剥离仅新增常量并恢复目标节点后，其他图字节必须完全相同。
    restored = onnx.ModelProto(); restored.CopyFrom(model)
    del restored.graph.initializer[original_initializers:]
    del restored.graph.node[:]; restored.graph.node.extend(before.graph.node)
    if restored.SerializeToString() != before.SerializeToString():
        raise ValueError('non-Resize graph content changed')
    onnx.checker.check_model(model, full_check=True)
    return replaced
