"""模型置信度主导、RGB边缘加权的受限二值图割；只处理内存原像素。

能量为逐像素logit负对数先验（去公共常数）+四邻域对比度Potts项。
所有容量以4096量化，计算该整数能量的全局最小割；真值不是输入。
"""
import numpy as np
from scipy.ndimage import binary_dilation, binary_erosion
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import maximum_flow, breadth_first_order


def graph(rgb, logits, mask, radius=8, weight=1.0):
    if logits.dtype != np.float32 or logits.ndim != 2 or not np.isfinite(logits).all():
        raise ValueError('finite original float32 HW logits required')
    if rgb.dtype != np.uint8 or rgb.shape != (*logits.shape, 3) or min(logits.shape) < 1:
        raise ValueError('original RGB uint8 HWC required')
    if mask.dtype != np.bool_ or mask.shape != logits.shape or not np.array_equal(mask, logits >= 0):
        raise ValueError('mask must equal original zero-logit decode')
    if type(radius) is not int or not 1 <= radius <= 32 or not np.isfinite(weight) or not 0 <= weight <= 4:
        raise ValueError('invalid band or regularization')
    square = np.ones((3, 3), bool)
    inner = binary_erosion(mask, square, iterations=radius, border_value=0)
    outer = binary_dilation(mask, square, iterations=radius, border_value=0)
    variable = outer & ~inner
    index = np.full(mask.shape, -1, np.int32)
    n = int(variable.sum()); index[variable] = np.arange(n, dtype=np.int32)
    # 去掉两标签共同项，避免大量无关容量；与clipped-logit BCE有相同最优解。
    prior = np.clip(logits[variable].astype(np.float64), -8, 8)
    # 一个容量单位的最小先验，避免量化/零logit平局改变原解码约定。
    prior = np.where(prior >= 0, np.maximum(prior, 1 / 4096), np.minimum(prior, -1 / 4096))
    foreground_cost = np.maximum(-prior, 0)
    background_cost = np.maximum(prior, 0)
    color = rgb.astype(np.float64) / 255
    edges = []
    for first, second in [((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                          ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))]:
        diff = ((color[first] - color[second]) ** 2).sum(axis=2)
        edges.append((index[first], index[second], mask[first], mask[second], diff))
    edge_count = sum(e[4].size for e in edges)
    mean = sum(float(e[4].sum()) for e in edges) / max(1, edge_count)
    beta = 1 / max(2 * mean, 1e-12)
    sources = []; destinations = []; capacities = []
    for a, b, hard_a, hard_b, difference in edges:
        cost = weight * np.exp(-beta * difference)
        both = (a >= 0) & (b >= 0)
        sources.extend([a[both], b[both]]); destinations.extend([b[both], a[both]])
        capacities.extend([np.rint(cost[both] * 4096).astype(np.int64)] * 2)
        for current, neighbor, hard in [(a, b, hard_b), (b, a, hard_a)]:
            fixed = (current >= 0) & (neighbor < 0)
            for is_foreground, unary in [(True, background_cost), (False, foreground_cost)]:
                choose = fixed & (hard == is_foreground)
                np.add.at(unary, current[choose], cost[choose])
    nodes = np.arange(n, dtype=np.int32)
    sources.extend([np.full(n, n, np.int32), nodes])
    destinations.extend([nodes, np.full(n, n + 1, np.int32)])
    capacities.extend([np.rint(background_cost * 4096).astype(np.int64),
                       np.rint(foreground_cost * 4096).astype(np.int64)])
    network = coo_matrix((np.concatenate(capacities), (np.concatenate(sources), np.concatenate(destinations))),
                         shape=(n + 2, n + 2), dtype=np.int64).tocsr()
    network.eliminate_zeros()
    return network, index, inner, outer


def cut(network):
    source, sink = network.shape[0] - 2, network.shape[0] - 1
    flow = maximum_flow(network, source, sink, method='dinic')
    residual = network - flow.flow
    residual.data[residual.data <= 0] = 0; residual.eliminate_zeros()
    reachable = breadth_first_order(residual, source, directed=True, return_predecessors=False)
    foreground = np.zeros(network.shape[0], bool); foreground[reachable] = True
    if foreground[sink]: raise RuntimeError('non-maximal flow')
    rows, cols = network.nonzero()
    energy = int(np.asarray(network[rows, cols]).reshape(-1)[foreground[rows] & ~foreground[cols]].sum())
    if energy != flow.flow_value: raise RuntimeError('cut/flow duality failed')
    return foreground[:-2], energy


def refine(rgb, logits, *, presence_accepted, radius=8, weight=1.0):
    if type(presence_accepted) is not bool:
        raise ValueError('boolean presence required')
    # 拒识也检查实际RAW有限与尺寸，不能让错误被presence分支掩盖。
    if logits.dtype != np.float32 or logits.ndim != 2 or not np.isfinite(logits).all():
        raise ValueError('finite original float32 HW logits required')
    if rgb.dtype != np.uint8 or rgb.shape != (*logits.shape, 3):
        raise ValueError('aligned original RGB required')
    mask = logits >= 0
    if not presence_accepted: return np.zeros_like(mask), 'rejected', 0
    if not mask.any(): return mask.copy(), 'empty', 0
    network, index, inner, outer = graph(rgb, logits, mask, radius, weight)
    labels, energy = cut(network)
    result = mask.copy(); variable = index >= 0; result[variable] = labels[index[variable]]
    if not result[inner].all() or result[~outer].any(): raise RuntimeError('band lock failed')
    return result, 'refined', energy
