"""主机坐标直接连接全部消费者，移除Identity中转；逐字节逆变换保持原图。"""
import copy
import importlib.util
from pathlib import Path
import onnx

spec = importlib.util.spec_from_file_location('strict_native_coordinate_identity_builder', Path(__file__).with_name('prepare-native-coordinate-graph-v2.py'))
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)


def build(original):
    identity, endpoints = base.transform(original)
    by_index = {r['index']: r for r in endpoints}
    by_target = {r['target']: r['inputName'] for r in endpoints}
    model = copy.deepcopy(identity)
    keep, sites = [], []
    for index, node in enumerate(identity.graph.node):
        if index in by_index:
            continue
        value = copy.deepcopy(node)
        for j, name in enumerate(node.input):
            if name in by_target:
                value.input[j] = by_target[name]
                sites.append({'originalNodeIndex': index, 'inputIndex': j, 'target': name, 'hostInput': by_target[name]})
        keep.append(value)
    del model.graph.node[:]
    model.graph.node.extend(keep)
    return model, {'endpoints': endpoints, 'consumerSites': sites}


def verify(original, model, mapping):
    _, expected = build(original)
    if mapping != expected:
        raise ValueError('exact direct coordinate consumer mapping')
    endpoints = {r['index']: r for r in mapping['endpoints']}
    if len(endpoints) != 16 or len(model.graph.node) != len(original.graph.node) - 16:
        raise ValueError('only16 coordinate identities removed')
    sites = {(r['originalNodeIndex'], r['inputIndex']): r for r in mapping['consumerSites']}
    reverse = copy.deepcopy(model)
    nodes = []
    actual = iter(model.graph.node)
    for index, before in enumerate(original.graph.node):
        if index in endpoints:
            row = endpoints[index]
            nodes.append(onnx.helper.make_node('Identity', [row['inputName']], [row['target']], name=before.name))
        else:
            node = copy.deepcopy(next(actual))
            for j, name in enumerate(node.input):
                row = sites.get((index, j))
                if row:
                    if name != row['hostInput']:
                        raise ValueError('direct host coordinate consumer')
                    node.input[j] = row['target']
            nodes.append(node)
    del reverse.graph.node[:]
    reverse.graph.node.extend(nodes)
    base.verify(original, reverse, mapping['endpoints'])
    onnx.checker.check_model(model)


def transform(original):
    model, mapping = build(original)
    verify(original, model, mapping)
    return model, mapping
