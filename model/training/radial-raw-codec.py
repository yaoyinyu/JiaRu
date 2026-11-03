"""半径场两头RAW无损捕获：写入前证明全原尺寸输出字节可重建。"""
import hashlib
import json
import os
from pathlib import Path
import numpy as np


def _sha(value):
    return hashlib.sha256(value.tobytes()).hexdigest()


def _validate(radius, bins, distance, presence):
    if radius.dtype != np.float32 or radius.ndim != 1 or not np.isfinite(radius).all():
        raise ValueError('finite float32 radius required')
    if bins.dtype != np.int32 or bins.ndim != 2 or bins.size == 0:
        raise ValueError('nonempty int32 full native angle bins required')
    if distance.dtype != np.float32 or distance.shape != bins.shape or not np.isfinite(distance).all():
        raise ValueError('aligned finite float32 native distance required')
    if bins.min() < 0 or bins.max() >= radius.size:
        raise ValueError('angle bin outside radius')
    if presence.dtype != np.float32 or presence.shape != () or not np.isfinite(presence):
        raise ValueError('finite float32 scalar presence required')


def save(path, mask, presence, radius, bins, distance, identity):
    _validate(radius, bins, distance, presence)
    if mask.dtype != np.float32 or mask.shape != bins.shape or not np.isfinite(mask).all():
        raise ValueError('finite float32 full native mask required')
    rebuilt = radius[bins] - distance
    if rebuilt.tobytes() != mask.tobytes():
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


def read(path, bins, distance, identity):
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != {'radius', 'rawPresence', 'metadata'}:
            raise ValueError('unexpected radial RAW fields')
        radius = archive['radius'].copy()
        presence = archive['rawPresence'].copy()
        encoded = archive['metadata']
        if encoded.dtype != np.uint8 or encoded.ndim != 1:
            raise ValueError('invalid RAW metadata encoding')
        metadata = json.loads(encoded.tobytes())
    _validate(radius, bins, distance, presence)
    mask = radius[bins] - distance
    expected = dict(version=1, identity=identity, shape=list(mask.shape), dtype='float32',
                    maskBytes=mask.nbytes, maskSha256=_sha(mask), presenceSha256=_sha(presence),
                    binsSha256=_sha(bins), distanceSha256=_sha(distance), radiusSha256=_sha(radius))
    if metadata != expected:
        raise ValueError('radial RAW identity, coordinates or full-head hash mismatch')
    return mask, presence, radius
