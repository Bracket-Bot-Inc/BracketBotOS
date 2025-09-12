# /// script
# dependencies = [
#   "bbos",
#   "numpy",
#   "rerun-sdk",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
import rerun as rr
from bbos import Writer, Reader, Config, Type
import numpy as np
import heapq
import time
from pathlib import Path
import math

CFG_M = Config('mapping')
CFG_drive = Config('drive')

LOOKAHEAD_DIST = 0.3
KP = 0.5
V = 0.2

# ---------- Smoothing utilities ----------
def astar_local(start, goal, obstacles, plan_radius, inflate_radius, cell_size=1.0):
    """
    A* with footprint-aware (C-space) checks.
      - start, goal: metric (x,y)
      - obstacles: metric (x,y) cell centers
      - plan_radius: meters around start (square window)
      - inflate_radius: robot radius + margin, meters
      - cell_size: meters per grid cell
    Returns: list of metric (x,y) waypoints (cell centers)
    """

    # --- metric <-> cell
    def to_cell(p):   return (int(math.floor(p[0]/cell_size)),
                              int(math.floor(p[1]/cell_size)))
    def to_metric(c): return ((c[0]+0.5)*cell_size, (c[1]+0.5)*cell_size)

    start_cell, goal_cell = to_cell(start), to_cell(goal)
    obs_cells = {to_cell(o) for o in obstacles}

    # planning window (valid cells)
    b = int(math.ceil(plan_radius/cell_size))
    cx0, cy0 = start_cell
    valid = {(x,y) for x in range(cx0-b, cx0+b+1)
                    for y in range(cy0-b, cy0+b+1)}

    # free = valid minus obstacle centers
    free = valid - obs_cells
    if not free:
        return []

    # precompute disk offsets for footprint
    r_cells = int(math.ceil(inflate_radius / cell_size))
    disk_offsets = [
        (ox, oy)
        for ox in range(-r_cells, r_cells+1)
        for oy in range(-r_cells, r_cells+1)
        if ox*ox + oy*oy <= r_cells*r_cells
    ]
    def is_cell_safe(c):
        return all((c[0]+ox, c[1]+oy) in free for ox,oy in disk_offsets)

    # snap GOAL to nearest safe cell (in meters) before planning
    if not is_cell_safe(goal_cell):
        safe_cells = [c for c in valid if is_cell_safe(c)]
        if not safe_cells:
            return []
        # choose the one closest in metric space to the true goal
        goal_cell = min(safe_cells,
                        key=lambda c: math.hypot(to_metric(c)[0]-goal[0],
                                                to_metric(c)[1]-goal[1]))

    safe = {c for c in free if all((c[0]+ox, c[1]+oy) in free for ox,oy in disk_offsets)}
    # neighbor generator (8-connected, no corner-cutting)
    moves = [(1,0),(-1,0),(0,1),(0,-1),
             (1,1),(-1,1),(1,-1),(-1,-1)]

    def neighbors(s):
        x, y = s
        for dx, dy in [(1,0),(-1,0),(0,1),(0,-1),
                    (1,1),(-1,1),(1,-1),(-1,-1)]:
            n = (x+dx, y+dy)
            if n not in valid:
                continue
            # check footprint disk
            if n in safe:
                yield n

    # octile heuristic for 8-connected grid
    def h(a,b):
        dx, dy = abs(a[0]-b[0]), abs(a[1]-b[1])
        D, D2 = 1.0, math.sqrt(2.0)
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)

    # --- A*
    openq = [(h(start_cell, goal_cell), 0.0, start_cell)]
    came_from = {start_cell: None}
    g = {start_cell: 0.0}

    while openq:
        _, cost, u = heapq.heappop(openq)
        if u == goal_cell:
            # reconstruct
            path = []
            while u is not None:
                path.append(to_metric(u))
                u = came_from[u]
            return path[::-1]

        for v in neighbors(u):
            step = math.sqrt(2.0) if (v[0]-u[0] and v[1]-u[1]) else 1.0
            new_cost = cost + step
            if v not in g or new_cost < g[v]:
                g[v] = new_cost
                heapq.heappush(openq, (new_cost + h(v, goal_cell), new_cost, v))
                came_from[v] = u

    # fallback: path to explored cell closest to TRUE goal (meters)
    if g:
        closest = min(g.keys(),
                      key=lambda c: math.hypot(to_metric(c)[0]-goal[0],
                                               to_metric(c)[1]-goal[1]))
        path = []
        while closest is not None:
            path.append(to_metric(closest))
            closest = came_from.get(closest)
        return path[::-1]

    return []

def main():
    with Writer("drive.ctrl",Type("drive_ctrl")) as w_drive, \
         Reader("localizer.pose") as r_pose, \
         Writer("nav.path",Type("nav_path")) as w_path, \
         Reader("nav.goal") as r_goal, \
         Reader("mapping.voxels") as r_voxels:
        pos = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        v, w = 0, 0
        goal = None
        while True:
            if r_pose.ready():
                pos = np.array([r_pose.data['x'], r_pose.data['y'], r_pose.data['theta']], dtype=np.float32)
                if goal is None:
                    goal = pos[:2]
            if r_voxels.ready():
                obstacles = CFG_M.unpack_keys(r_voxels.data['keys'][(CFG_M.normalize(r_voxels.data['logodds']) > 0.75)])
                mask2d = (obstacles[:, 2] < 1) & (obstacles[:,2] >= 0.3)
                obstacles = obstacles[mask2d][:, :2]
                #explorer = LocalExplorer(obstacles, cfg)
                #v, w, path = explorer.plan_step(pos)
                if np.linalg.norm(goal - pos[:2]) >= 0.1:
                    path = astar_local(tuple(pos[:2].tolist()), tuple(goal.tolist()), obstacles, 2, CFG_drive.robot_width, CFG_M.voxel_size)
                    n = min(round(LOOKAHEAD_DIST / CFG_M.voxel_size), len(path) - 1)
                    dx, dy = path[n][0] - pos[0], path[n][1] - pos[1]
                    hx, hy = -math.sin(pos[2]), math.cos(pos[2])
                    norm = math.hypot(dx, dy)
                    if norm < 0.01:  # Too close to target
                        v, w = 0, 0
                        continue
                    tx, ty = dx / norm, dy / norm
                    cross = hx * ty - hy * tx  # sin(angle)
                    dot = hx * tx + hy * ty     # cos(angle)
                    err = math.atan2(cross, dot)
                    w = -KP * err  # negative because positive w turns left, but positive err means target is to the right
                    v = V * max(0.0, dot)  # only move forward if facing somewhat towards target
                else:
                    v, w = 0, 0
            w_drive['twist'] = np.array([v, w], dtype=np.float32)

if __name__ == "__main__":
    main()