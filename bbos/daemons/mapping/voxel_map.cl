#pragma OPENCL EXTENSION cl_khr_int64_base_atomics     : enable
#pragma OPENCL EXTENSION cl_khr_int64_extended_atomics : enable
#pragma OPENCL EXTENSION cl_khr_global_int32_base_atomics     : enable
#pragma OPENCL EXTENSION cl_khr_global_int32_extended_atomics : enable

#define EMPTY_KEY64 0xffffffffffffffffUL

inline ulong voxel_key64(long i, long j, long k) {
    // pack signed 21 bits/axis: [-2^20 .. 2^20-1]
    return (((ulong)(i & 0x1FFFFF)) << 42) |
           (((ulong)(j & 0x1FFFFF)) << 21) |
           (((ulong)(k & 0x1FFFFF)) <<  0);
}

inline ulong hash64_u64(ulong x, ulong M) {
    x ^= x >> 33; x *= 0xff51afd7ed558ccdUL;
    x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53UL;
    x ^= x >> 33;
    return x % M;
}

__kernel void update_logodds_hash(
    __global const float4 *origins,
    __global const float4 *endpoints,
    __global const int    *sem_mask, // int32 semantic mask per voxel hit
    const float voxel_size,
    const int   max_steps,
    __global ulong *keys,   // 64-bit keys
    __global int   *values, // int32 log-odds
    __global int   *key_masks, // int32 mask value at each key
    const ulong M,
    const int  hit_inc,
    const int  miss_dec,
    const int  n_valid,
    const float decay_lambda,
    const float min_hit_scale
){
    const int gid = get_global_id(0);
    if (gid >= n_valid) return;
    const int mask = sem_mask[gid];
    const float3 o = (float3)(origins[gid].x,  origins[gid].y,  origins[gid].z);
    const float3 e = (float3)(endpoints[gid].x, endpoints[gid].y, endpoints[gid].z);

    const float3 v = e - o;
    const float   L = length(v);
    if (!isfinite(L) || L <= 0.0f) return;
    const float3 d = v / L;

    int steps_needed = (int)ceil(L / voxel_size) + 1;
    if (steps_needed > max_steps) steps_needed = max_steps;

    long ix = (long)floor(o.x / voxel_size);
    long iy = (long)floor(o.y / voxel_size);
    long iz = (long)floor(o.z / voxel_size);

    const long ix_end = (long)floor(e.x / voxel_size);
    const long iy_end = (long)floor(e.y / voxel_size);
    const long iz_end = (long)floor(e.z / voxel_size);

    const int step_x = (d.x > 0.0f) ? 1 : -1;
    const int step_y = (d.y > 0.0f) ? 1 : -1;
    const int step_z = (d.z > 0.0f) ? 1 : -1;

    float tMaxX = (d.x == 0.0f) ? INFINITY :
        ((step_x > 0 ? ((ix+1)*voxel_size - o.x) : (ix*voxel_size - o.x)) / d.x);
    float tMaxY = (d.y == 0.0f) ? INFINITY :
        ((step_y > 0 ? ((iy+1)*voxel_size - o.y) : (iy*voxel_size - o.y)) / d.y);
    float tMaxZ = (d.z == 0.0f) ? INFINITY :
        ((step_z > 0 ? ((iz+1)*voxel_size - o.z) : (iz*voxel_size - o.z)) / d.z);

    const float tDeltaX = (d.x == 0.0f) ? INFINITY : voxel_size / fabs(d.x);
    const float tDeltaY = (d.y == 0.0f) ? INFINITY : voxel_size / fabs(d.y);
    const float tDeltaZ = (d.z == 0.0f) ? INFINITY : voxel_size / fabs(d.z);

    // free-space
    for (int s = 0; s < steps_needed; ++s) {
        if (ix == ix_end && iy == iy_end && iz == iz_end) break;

        const ulong k = voxel_key64(ix, iy, iz);
        ulong h = hash64_u64(k, M);
        for (int attempt = 0; attempt < 64; ++attempt) {
            const ulong slot = (h + (ulong)attempt) % M;
            const ulong prev = atom_cmpxchg((volatile __global ulong*)&keys[slot],
                                            (ulong)EMPTY_KEY64, (ulong)k);
            if (prev == EMPTY_KEY64 || prev == k) {
                atomic_add((volatile __global int*)&values[slot], (int)miss_dec);
                atomic_xchg((volatile __global int*)&key_masks[slot], 0); 
                break;
            }
        }

        if (tMaxX < tMaxY && tMaxX < tMaxZ) { ix += step_x; tMaxX += tDeltaX; }
        else if (tMaxY < tMaxZ)             { iy += step_y; tMaxY += tDeltaY; }
        else                                 { iz += step_z; tMaxZ += tDeltaZ; }
    }

    // endpoint with decay
    float scale = exp(-L / fmax(decay_lambda, 1e-6f));
    if (scale < min_hit_scale) scale = min_hit_scale;
    const int scaled_hit = (int)rint((float)hit_inc * scale);

    const ulong k = voxel_key64(ix_end, iy_end, iz_end);
    ulong h = hash64_u64(k, M);
    for (int attempt = 0; attempt < 64; ++attempt) {
        const ulong slot = (h + (ulong)attempt) % M;
        const ulong prev = atom_cmpxchg((volatile __global ulong*)&keys[slot],
                                        (ulong)EMPTY_KEY64, (ulong)k);
        if (prev == EMPTY_KEY64 || prev == k) {
            atomic_add((volatile __global int*)&values[slot], (int)scaled_hit);
            atomic_xchg((volatile __global int*)&key_masks[slot], mask); 
            break;
        }
    }
}

__kernel void clamp_logodds(__global int *values, const int lo, const int hi) {
    const int gid = get_global_id(0);
    int v = values[gid];
    if (v < lo) values[gid] = lo;
    if (v > hi) values[gid] = hi;
}
