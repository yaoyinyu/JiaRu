"""仅替换16个坐标端点为主机输入；逆变换必须精确恢复原图所有字节。"""
import copy
import hashlib
import onnx

FIELDS = ['lower', 'upper', 'weight0', 'weight1']


def transform(original):
    if [v.name for v in original.graph.input] != ['candidate', 'resizeRatios']:
        raise ValueError('original ordered native inputs')
    if [v.name for v in original.graph.output] != ['mask_logits', 'presence_logit']:
        raise ValueError('original ordered two heads')
    model = copy.deepcopy(original)
    nodes = {n.name: n for n in original.graph.node}
    producers = {out: (i, n) for i, n in enumerate(original.graph.node) for out in n.output}
    mapping = []
    for block in ['dec2', 'dec1']:
        conv = nodes[f'/{block}/{block}.0/Conv']
        concat = producers[conv.input[0]][1]
        last = producers[concat.input[0]][1]
        prefix = last.name.removesuffix('output')
        if concat.op_type != 'Concat' or last.op_type != 'Add' or not prefix.startswith('native_bilinear_'):
            raise ValueError('actual separable resize topology')
        for axis in ['y', 'x']:
            for field in FIELDS:
                target = prefix + axis + '_' + field
                index, old = producers[target]
                if len(old.output) != 1 or old.domain:
                    raise ValueError('single standard coordinate endpoint')
                name = f'nativeCoord_{block}_{axis}_{field}'
                integer = field in ['lower', 'upper']
                size = f'native_{block}_{axis}'
                shape = [size] if integer else ([1, 1, size, 1] if axis == 'y' else [1, 1, 1, size])
                model.graph.node[index].CopyFrom(onnx.helper.make_node('Identity', [name], [target], name=old.name))
                model.graph.input.append(onnx.helper.make_tensor_value_info(name, onnx.TensorProto.INT64 if integer else onnx.TensorProto.FLOAT, shape))
                mapping.append({'index': index, 'nodeName': old.name, 'target': target, 'inputName': name,
                                'block': block, 'axis': axis, 'field': field, 'shape': shape,
                                'originalNodeSha256': hashlib.sha256(old.SerializeToString()).hexdigest()})
    verify(original, model, mapping)
    return model, mapping


def verify(original, model, mapping):
    if len(mapping) != 16 or len(model.graph.input) != 18:
        raise ValueError('complete two-scale coordinate inputs')
    stripped = copy.deepcopy(model)
    for row, new_input in zip(mapping, list(model.graph.input)[2:], strict=True):
        index = row['index']; before = original.graph.node[index]
        expected = onnx.helper.make_node('Identity', [row['inputName']], [row['target']], name=before.name)
        if model.graph.node[index].SerializeToString() != expected.SerializeToString() or new_input.name != row['inputName']:
            raise ValueError('only frozen coordinate node replacement')
        if hashlib.sha256(before.SerializeToString()).hexdigest() != row['originalNodeSha256']:
            raise ValueError('original coordinate node byte binding')
        stripped.graph.node[index].CopyFrom(before)
    del stripped.graph.input[2:]
    if stripped.SerializeToString() != original.SerializeToString():
        raise ValueError('complete graph reverse byte reconstruction_mismatch')
    onnx.checker.check_model(model)
