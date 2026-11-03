"""每个成功优化步独占持久化完整状态，避免替换被读取锁定的文件。"""
import os
from pathlib import Path
import random
import numpy as np
import torch


def save(path, model, optimizer, rng, cursor, counts, plan):
    path = Path(path)
    state = dict(model=model.state_dict(), optimizer=optimizer.state_dict(),
                 numpyRng=rng.bit_generator.state, pythonRng=random.getstate(),
                 torchRng=torch.get_rng_state(),
                 cudaRng=torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
                 cursor=cursor, counts=counts, plan=plan)
    with path.open('xb') as stream:
        torch.save(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def restore(path, model, optimizer, rng, expected_plan):
    state = torch.load(path, map_location='cpu', weights_only=False)
    if state['plan'] != expected_plan:
        raise ValueError('checkpoint plan mismatch')
    model.load_state_dict(state['model'], strict=True)
    optimizer.load_state_dict(state['optimizer'])
    rng.bit_generator.state = state['numpyRng']
    random.setstate(state['pythonRng'])
    torch.set_rng_state(state['torchRng'])
    if state['cudaRng']:
        torch.cuda.set_rng_state_all(state['cudaRng'])
    return state['cursor'], state['counts']
