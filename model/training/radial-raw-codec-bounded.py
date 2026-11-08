"""分行验证原尺寸径向RAW，保持既有NPZ字段和逐字节两头合同。"""
import hashlib
import json
import os
from pathlib import Path
import numpy as np


def _sha(array):
    digest = hashlib.sha256()
    if array.flags.c_contiguous:
        digest.update(memoryview(array).cast('B'))
    else:
        for start in range(0, len(array), 16):
            digest.update(memoryview(np.ascontiguousarray(array[start:start + 16])).cast('B'))
    return digest.hexdigest()


def save(path, mask, presence, radius, bins, distance, identity):
    if radius.dtype != np.float32 or radius.ndim != 1 or not np.isfinite(radius).all():
        raise ValueError('finite float32 radius required')
    if bins.dtype != np.int32 or bins.ndim != 2 or bins.size == 0:
        raise ValueError('nonempty int32 full native angle bins required')
    if distance.dtype != np.float32 or distance.shape != bins.shape:
        raise ValueError('aligned finite float32 native distance required')
    if presence.dtype != np.float32 or presence.shape != () or not np.isfinite(presence):
        raise ValueError('finite float32 scalar presence required')
    if mask.dtype != np.float32 or mask.shape != bins.shape:
        raise ValueError('finite float32 full native mask required')
    for start in range(0, bins.shape[0], 16):
        b, dist, actual = bins[start:start + 16], distance[start:start + 16], mask[start:start + 16]
        if b.min() < 0 or b.max() >= radius.size:
            raise ValueError('angle bin outside radius')
        if not np.isfinite(dist).all() or not np.isfinite(actual).all():
            raise ValueError('finite full native values required')
        rebuilt = np.ascontiguousarray(radius[b] - dist)
        # 比较存储字节，保留正负零等IEEE差异；额外副本最多16行。
        if not np.array_equal(rebuilt.view(np.uint8), np.ascontiguousarray(actual).view(np.uint8)):
            raise ValueError('full native RAW byte reconstruction mismatch')
    metadata = dict(version=1, identity=identity, shape=list(mask.shape), dtype='float32',
                    maskBytes=mask.nbytes, maskSha256=_sha(mask), presenceSha256=_sha(presence),
                    binsSha256=_sha(bins), distanceSha256=_sha(distance), radiusSha256=_sha(radius))
    encoded = np.frombuffer((json.dumps(metadata, ensure_ascii=False, sort_keys=True,
                                       separators=(',', ':')) + '\n').encode('utf-8'), dtype=np.uint8)
    with Path(path).open('xb') as stream:
        np.savez_compressed(stream, radius=radius, rawPresence=presence, metadata=encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return metadata
