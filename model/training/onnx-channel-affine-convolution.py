"""将明确指定的逐通道Mul/Add改为1×1分组卷积，参数原位值不变且完整图可逆。"""
import copy
import hashlib
import importlib.util
from pathlib import Path

import numpy as np
import onnx
from onnx import helper, numpy_helper

s = importlib.util.spec_from_file_location('channel_affine_static', Path(__file__).with_name('onnx-materialize-static-unsqueeze.py'))
static = importlib.util.module_from_spec(s)
s.loader.exec_module(static)


def transform(model, node_names):
    if not node_names or len(set(node_names)) != len(node_names):
        raise ValueError('explicit unique affine Add nodes required')
    by_name = {n.name: n for n in model.graph.node}
    by_output = {x: n for n in model.graph.node for x in n.output}
    indices = {n.name: i for i,n in enumerate(model.graph.node)}
    initial = {v.name: hashlib.sha256(v.SerializeToString()).hexdigest() for v in model.graph.initializer}
    replacements, removed, added, records = {}, set(), [], []
    for ordinal, name in enumerate(node_names):
        add = by_name[name]
        if add.op_type != 'Add' or len(add.input) != 2 or len(add.output) != 1:
            raise ValueError('explicit affine Add required')
        mul = by_output[add.input[0]]
        if mul.op_type != 'Mul' or len(mul.input) != 2 or len(mul.output) != 1:
            raise ValueError('affine Mul producer required')
        consumers = [n.name for n in model.graph.node if mul.output[0] in n.input]
        if consumers != [add.name] or any(v.name == mul.output[0] for v in model.graph.output):
            raise ValueError('affine intermediate must have one consumer and no external output')
        vectors = []
        for value in [mul.input[1], add.input[1]]:
            unsqueeze = by_output[value]
            if unsqueeze.op_type != 'Unsqueeze' or len(unsqueeze.input) != 2:
                raise ValueError('immutable parameter Unsqueeze required')
            vector, _ = static.static_value(model, unsqueeze.input[0])
            axes, _ = static.static_value(model, unsqueeze.input[1])
            if vector.dtype != np.float32 or vector.ndim != 1 or len(vector) not in [16,32,64] or not np.isfinite(vector).all():
                raise ValueError('finite native channel affine parameters required')
            if axes.dtype != np.int64 or axes.tolist() != [1,2]:
                raise ValueError('original channel broadcasting axes')
            vectors.append(vector)
        gamma, beta = vectors
        if gamma.shape != beta.shape:
            raise ValueError('gamma/beta channel mismatch')
        prefix = f'channel_affine_conv_v1_{ordinal}_'
        if any(n.name.startswith(prefix) for n in model.graph.node) or any(v.name.startswith(prefix) for v in model.graph.initializer):
            raise ValueError('prefix collision')
        weight = numpy_helper.from_array(gamma.reshape(len(gamma),1,1,1).copy(), name=prefix+'weight')
        bias = numpy_helper.from_array(beta.copy(), name=prefix+'bias')
        assert weight.raw_data == gamma.tobytes() and bias.raw_data == beta.tobytes()
        conv = helper.make_node('Conv', [mul.input[0],weight.name,bias.name], list(add.output), name=prefix+'Conv',
                                group=len(gamma), kernel_shape=[1,1], strides=[1,1], pads=[0,0,0,0], dilations=[1,1])
        if mul.name in removed or add.name in removed:
            raise ValueError('overlapping affine targets')
        removed.update([mul.name,add.name])
        replacements[add.name] = conv
        added.extend([weight,bias])
        records.append(dict(addNode=name,mulNode=mul.name,channels=len(gamma),replacementNode=conv.name,
                            originals=[dict(index=indices[n.name],hex=n.SerializeToString().hex()) for n in [mul,add]],
                            replacementHex=conv.SerializeToString().hex(),
                            addedInitializers={v.name:hashlib.sha256(v.SerializeToString()).hexdigest() for v in [weight,bias]},
                            gammaBytesSha256=hashlib.sha256(gamma.tobytes()).hexdigest(),betaBytesSha256=hashlib.sha256(beta.tobytes()).hexdigest()))
    result = copy.deepcopy(model)
    nodes = [copy.deepcopy(replacements[n.name]) if n.name in replacements else copy.deepcopy(n) for n in model.graph.node if n.name not in removed or n.name in replacements]
    del result.graph.node[:]
    result.graph.node.extend(nodes)
    result.graph.initializer.extend(added)
    proof = dict(records=records,originalInitializerHashes=initial,parameterValuesPreserved=True,
                 equivalence='per-channel gamma*x+beta; floating-point kernel parity requires full runtime validation',
                 signedZeroStorageIdentityClaimed=False)
    assert restore(result,proof).SerializeToString() == model.SerializeToString()
    onnx.checker.check_model(result,full_check=True)
    return result,proof


def restore(model, proof):
    result = copy.deepcopy(model)
    replacements = {r['replacementNode']:r for r in proof['records']}
    names = {k:v for r in proof['records'] for k,v in r['addedInitializers'].items()}
    assert set(replacements) == {n.name for n in result.graph.node if n.name.startswith('channel_affine_conv_v1_')}
    for n in result.graph.node:
        if n.name in replacements:
            assert n.SerializeToString().hex() == replacements[n.name]['replacementHex']
    nodes = [copy.deepcopy(n) for n in result.graph.node if n.name not in replacements]
    originals = [x for r in proof['records'] for x in r['originals']]
    for x in sorted(originals,key=lambda v:v['index']):
        n = onnx.NodeProto()
        n.ParseFromString(bytes.fromhex(x['hex']))
        nodes.insert(x['index'],n)
    del result.graph.node[:]
    result.graph.node.extend(nodes)
    constants = []
    found = set()
    for v in result.graph.initializer:
        sha = hashlib.sha256(v.SerializeToString()).hexdigest()
        if v.name in names:
            assert sha == names[v.name]
            found.add(v.name)
        else:
            assert sha == proof['originalInitializerHashes'][v.name]
            constants.append(copy.deepcopy(v))
    assert found == set(names) and {v.name for v in constants} == set(proof['originalInitializerHashes'])
    del result.graph.initializer[:]
    result.graph.initializer.extend(constants)
    return result
