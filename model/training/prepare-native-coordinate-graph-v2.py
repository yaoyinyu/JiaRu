"""补齐新增主机输入的完整类型/形状验真；保留v1冻结构建器及产物。"""
import importlib.util
from pathlib import Path
import onnx

spec = importlib.util.spec_from_file_location('native_coordinate_original_builder', Path(__file__).with_name('prepare-native-coordinate-graph.py'))
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)


def verify(original, model, mapping):
    base.verify(original, model, mapping)
    _, expected = base.transform(original)
    if mapping != expected:
        raise ValueError('exact semantic endpoint mapping')
    for row, actual in zip(mapping, list(model.graph.input)[2:], strict=True):
        integer = row['field'] in ['lower', 'upper']
        size = f'native_{row["block"]}_{row["axis"]}'
        shape = [size] if integer else ([1, 1, size, 1] if row['axis'] == 'y' else [1, 1, 1, size])
        expected_input = onnx.helper.make_tensor_value_info(row['inputName'], onnx.TensorProto.INT64 if integer else onnx.TensorProto.FLOAT, shape)
        if actual.SerializeToString() != expected_input.SerializeToString():
            raise ValueError('complete host coordinate input type/shape')


def transform(original):
    model, mapping = base.transform(original)
    verify(original, model, mapping)
    return model, mapping
