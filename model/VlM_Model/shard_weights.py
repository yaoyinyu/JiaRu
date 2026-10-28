"""手写 safetensors 分片器：绕开 safetensors.get_tensor（该调用在 9.66 GB 单文件上
会触发 0xC0000005），改用 mmap + torch.frombuffer 直接切分。一次性工具。
"""

from __future__ import annotations

import json
import mmap
import struct
import sys
from pathlib import Path

import torch
from safetensors.torch import save_file

SRC = Path(sys.argv[1])
DST = Path(sys.argv[2])
MAX_BYTES = int(sys.argv[3]) if len(sys.argv) > 3 else 2_400_000_000

DTYPES = {
    "BF16": torch.bfloat16,
    "F16": torch.float16,
    "F32": torch.float32,
    "I64": torch.int64,
    "I32": torch.int32,
    "U8": torch.uint8,
    "BOOL": torch.bool,
}

DST.mkdir(parents=True, exist_ok=True)

with open(SRC, "rb") as fh:
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    header_len = struct.unpack("<Q", mm[:8])[0]
    header = json.loads(mm[8 : 8 + header_len])
    base = 8 + header_len
    header.pop("__metadata__", None)

    groups: list[list[str]] = [[]]
    current = 0
    for key, info in header.items():
        start, end = info["data_offsets"]
        if current + (end - start) > MAX_BYTES and groups[-1]:
            groups.append([])
            current = 0
        groups[-1].append(key)
        current += end - start

    print(f"{len(header)} 个张量 -> {len(groups)} 片", flush=True)

    index = {"metadata": {"format": "pt"}, "weight_map": {}}
    for i, group in enumerate(groups):
        name = f"model-{i + 1:05d}-of-{len(groups):05d}.safetensors"
        tensors = {}
        for key in group:
            info = header[key]
            start, end = info["data_offsets"]
            dtype = DTYPES[info["dtype"]]
            count = (end - start) // torch.tensor([], dtype=dtype).element_size()
            view = torch.frombuffer(mm, dtype=dtype, count=count, offset=base + start)
            tensors[key] = view.reshape(info["shape"]).clone()
        save_file(tensors, str(DST / name), metadata={"format": "pt"})
        total = sum(t.numel() * t.element_size() for t in tensors.values())
        for key in group:
            index["weight_map"][key] = name
        print(f"  {name}  {len(tensors):4d} 张量  {total / 2**30:.2f} GiB", flush=True)
        del tensors
    mm.close()

(DST / "model.safetensors.index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
print("索引已写入", flush=True)
