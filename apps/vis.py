from bbos.registry import get_type, get_cfg
from bbos.shm import Reader
from bbos.time import Rate

from datetime import datetime
import taichi as ti
import numpy as np
from PIL import Image
from pathlib import Path

CFG = get_cfg("CFG_camera_stereo_OV9281")
ti.init(arch=ti.opengl)

W, H = CFG.width, CFG.height
screen_res = (W + 10, H + 10)

img = ti.Vector.field(3, dtype=ti.f32, shape=(W, H))
screen = ti.Vector.field(3, dtype=ti.f32, shape=screen_res)
zoom = ti.field(dtype=ti.f32, shape=())
offset = ti.Vector.field(2, dtype=ti.f32, shape=())

zoom[None] = 1.0
offset[None] = ti.Vector([W / 2, H / 2])


@ti.kernel
def init_image():
    for i, j in img:
        img[i, j] = ti.Vector([ti.random(), ti.random(), ti.random()])


@ti.kernel
def render():
    for i, j in screen:
        cx, cy = screen_res[0] * 0.5, screen_res[1] * 0.5
        u = (i - cx) / zoom[None] + offset[None][0]
        v = (j - cy) / zoom[None] + offset[None][1]
        xi = int(ti.floor(u))
        yi = int(ti.floor(v))
        if 0 <= xi < W and 0 <= yi < H:
            screen[i, j] = img[xi, yi]
        else:
            screen[i, j] = ti.Vector([0.0, 0.0, 0.0])


def main():
    with Reader("/camera_stereo", get_type("camera_stereo_OV9281")) as reader:
        init_image()
        gui = ti.GUI("Pan + Zoom Pixel Viewer", res=screen_res)

        prev_cursor = ti.Vector([0.0, 0.0])

        data = None
        saved = []

        while gui.running:
            cursor = ti.Vector(gui.get_cursor_pos()) * screen_res

            # --- Mouse drag pan ---
            if gui.get_event(ti.GUI.LMB):
                prev_cursor = cursor
            elif gui.is_pressed(ti.GUI.LMB):
                delta = cursor - prev_cursor
                offset[None] -= delta / zoom[None]
                prev_cursor = cursor

            # --- Update/save image ---
            if gui.is_pressed(ti.GUI.SPACE):
                _, data = reader.get()
                new_img = data
                img.from_numpy(
                    (data['stereo'].astype(np.float32) / 255.0).transpose(
                        1, 0, 2))
            if gui.is_pressed('s'):
                if data is not None:
                    if not saved or data['timestamp'] != saved[-1]['timestamp']:
                        saved.append(data.copy())
                        print(f'added sample #{len(saved)}')
            if gui.is_pressed('c'):
                saved = []
            if gui.is_pressed('q'):
                break

            # --- Zoom on cursor ---
            if gui.is_pressed('+') or gui.is_pressed('='):
                factor = 1.05
            elif gui.is_pressed('-') or gui.is_pressed('_'):
                factor = 1 / 1.05
            else:
                factor = 1.0

            if factor != 1.0:
                before = (cursor - ti.Vector(screen_res) *
                          0.5) / zoom[None] + offset[None]
                zoom[None] *= factor
                after = (cursor - ti.Vector(screen_res) *
                         0.5) / zoom[None] + offset[None]
                offset[None] += before - after

            render()
            gui.set_image(screen)
            gui.show()

        if saved:
            folder = Path('cache')
            folder.mkdir(parents=True, exist_ok=True)
            start = max(
                (int(f.name[5:8]) for f in list(folder.rglob("*.jpg"))),
                default=0) + 1
            for i, sample in enumerate(saved):
                Image.fromarray(sample['stereo'][:, :CFG.width // 2]).save(
                    folder / f"frame{start + i:03d}_camera0.jpg",
                    format="JPEG")
                Image.fromarray(sample['stereo'][:, CFG.width // 2:]).save(
                    folder / f"frame{start + i:03d}_camera1.jpg",
                    format="JPEG")
            print(f'saved samples to {folder}')


if __name__ == "__main__":
    main()
