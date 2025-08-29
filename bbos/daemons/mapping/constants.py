from bbos.registry import *
from bbos.tf import *
import numpy as np


@register
class mapping:
    voxel_size = 0.1
    max_steps = 32   # cap steps per ray
    M = 1 << 21      # hash table slots
    hit_inc = int(0.85 * 1000)   # +850
    miss_dec = int(-0.4 * 1000)  # -400
    max_logodds = hit_inc * 10
    min_logodds = miss_dec * 10
    decay_lambda = 2.0
    min_hit = 0.1
    @staticmethod
    def unpack_keys(keys: np.ndarray):
        keys = keys.astype(np.uint64).ravel()
        # extract 21-bit fields
        i = (keys >> 42) & 0x1FFFFF
        j = (keys >> 21) & 0x1FFFFF
        k = (keys >>  0) & 0x1FFFFF
        # convert to signed (−2^20 .. 2^20−1)
        i = i.astype(np.int64); j = j.astype(np.int64); k = k.astype(np.int64)
        i[i & 0x100000 != 0] -= 0x200000
        j[j & 0x100000 != 0] -= 0x200000
        k[k & 0x100000 != 0] -= 0x200000

        ijk = np.stack([i, j, k], axis=1).astype(np.float32)
        return (ijk + 0.5) * mapping.voxel_size


@realtime(ms=100)
def mapping_voxels():
    return [
        ("keys", np.uint64, (mapping.M,)),
        ("logodds", np.int32, (mapping.M,)),
    ]