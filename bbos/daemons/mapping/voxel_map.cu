// CUDA port of update_logodds_hash + clamp_logodds
// Suitable for PyCUDA's SourceModule

#include <math_constants.h>   // CUDART_INF_F
#include <math_functions.h>   // isfinite, expf, rintf, etc.

#define EMPTY_KEY64 0xffffffffffffffffULL

// pack signed 21 bits/axis: [-2^20 .. 2^20-1]
__device__ __forceinline__
unsigned long long voxel_key64(long long i, long long j, long long k) {
    return (((unsigned long long)(i & 0x1FFFFF)) << 42) |
           (((unsigned long long)(j & 0x1FFFFF)) << 21) |
           (((unsigned long long)(k & 0x1FFFFF)) <<  0);
}

__device__ __forceinline__
unsigned long long hash64_u64(unsigned long long x, unsigned long long M) {
    x ^= x >> 33; x *= 0xff51afd7ed558ccdULL;
    x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ULL;
    x ^= x >> 33;
    return x % M;
}

extern "C" __global__
void update_logodds_hash(
    const float4 * __restrict__ origins,
    const float4 * __restrict__ endpoints,
    const float voxel_size,
    const int   max_steps,
    unsigned long long * __restrict__ keys,   // 64-bit keys
    int   * __restrict__ values,              // int32 log-odds
    const unsigned long long M,
    const int  hit_inc,
    const int  miss_dec,
    const int  n_valid,
    const float decay_lambda,
    const float min_hit_scale
){
    const int gid = threadIdx.x + blockIdx.x * blockDim.x;
    if (gid >= n_valid) return;

    const float3 o = make_float3(origins[gid].x,  origins[gid].y,  origins[gid].z);
    const float3 e = make_float3(endpoints[gid].x, endpoints[gid].y, endpoints[gid].z);

    const float3 v = make_float3(e.x - o.x, e.y - o.y, e.z - o.z);
    const float   L = sqrtf(v.x*v.x + v.y*v.y + v.z*v.z);
    if (!isfinite(L) || L <= 0.0f) return;
    const float3 d = make_float3(v.x / L, v.y / L, v.z / L);

    int steps_needed = (int)ceilf(L / voxel_size) + 1;
    if (steps_needed > max_steps) steps_needed = max_steps;

    long long ix = (long long)floorf(o.x / voxel_size);
    long long iy = (long long)floorf(o.y / voxel_size);
    long long iz = (long long)floorf(o.z / voxel_size);

    const long long ix_end = (long long)floorf(e.x / voxel_size);
    const long long iy_end = (long long)floorf(e.y / voxel_size);
    const long long iz_end = (long long)floorf(e.z / voxel_size);

    const int step_x = (d.x > 0.0f) ? 1 : -1;
    const int step_y = (d.y > 0.0f) ? 1 : -1;
    const int step_z = (d.z > 0.0f) ? 1 : -1;

    float tMaxX = (d.x == 0.0f) ? CUDART_INF_F :
        ((step_x > 0 ? ((ix+1)*voxel_size - o.x) : (ix*voxel_size - o.x)) / d.x);
    float tMaxY = (d.y == 0.0f) ? CUDART_INF_F :
        ((step_y > 0 ? ((iy+1)*voxel_size - o.y) : (iy*voxel_size - o.y)) / d.y);
    float tMaxZ = (d.z == 0.0f) ? CUDART_INF_F :
        ((step_z > 0 ? ((iz+1)*voxel_size - o.z) : (iz*voxel_size - o.z)) / d.z);

    const float tDeltaX = (d.x == 0.0f) ? CUDART_INF_F : voxel_size / fabsf(d.x);
    const float tDeltaY = (d.y == 0.0f) ? CUDART_INF_F : voxel_size / fabsf(d.y);
    const float tDeltaZ = (d.z == 0.0f) ? CUDART_INF_F : voxel_size / fabsf(d.z);

    // free-space updates
    for (int s = 0; s < steps_needed; ++s) {
        if (ix == ix_end && iy == iy_end && iz == iz_end) break;

        const unsigned long long k = voxel_key64(ix, iy, iz);
        unsigned long long h = hash64_u64(k, M);
        // linear probing with a small cap (64)
        for (int attempt = 0; attempt < 64; ++attempt) {
            const unsigned long long slot = (h + (unsigned long long)attempt) % M;
            const unsigned long long prev = atomicCAS(&keys[slot], (unsigned long long)EMPTY_KEY64, k);
            if (prev == EMPTY_KEY64 || prev == k) {
                atomicAdd(&values[slot], (int)miss_dec);
                break;
            }
        }

        if (tMaxX < tMaxY && tMaxX < tMaxZ) { ix += step_x; tMaxX += tDeltaX; }
        else if (tMaxY < tMaxZ)             { iy += step_y; tMaxY += tDeltaY; }
        else                                { iz += step_z; tMaxZ += tDeltaZ; }
    }

    // endpoint with distance-based decay
    {
        float scale = expf(-L / fmaxf(decay_lambda, 1e-6f));
        if (scale < min_hit_scale) scale = min_hit_scale;
        const int scaled_hit = (int)rintf((float)hit_inc * scale);

        const unsigned long long k = voxel_key64(ix_end, iy_end, iz_end);
        unsigned long long h = hash64_u64(k, M);
        for (int attempt = 0; attempt < 64; ++attempt) {
            const unsigned long long slot = (h + (unsigned long long)attempt) % M;
            const unsigned long long prev = atomicCAS(&keys[slot], (unsigned long long)EMPTY_KEY64, k);
            if (prev == EMPTY_KEY64 || prev == k) {
                atomicAdd(&values[slot], (int)scaled_hit);
                break;
            }
        }
    }
}

// Direct port (assumes launch size == len(values))
extern "C" __global__
void clamp_logodds(int *values, const int lo, const int hi) {
    const int gid = threadIdx.x + blockIdx.x * blockDim.x;
    int v = values[gid];
    if (v < lo) values[gid] = lo;
    if (v > hi) values[gid] = hi;
}

// Safer variant with bound check (optional)
extern "C" __global__
void clamp_logodds_n(int *values, const int lo, const int hi, const int n) {
    const int gid = threadIdx.x + blockIdx.x * blockDim.x;
    if (gid >= n) return;
    int v = values[gid];
    if (v < lo) values[gid] = lo;
    if (v > hi) values[gid] = hi;
}
