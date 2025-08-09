from bbos import Reader, Config

import cv2
import numpy as np
import inspect
import turbojpeg
from turbojpeg import decompress, decompress_to, PF
CFG = Config('stereo')
with Reader('camera.jpeg') as r:
    img = np.array((CFG.width*CFG.height*3*2))
    while True:
        if r.ready():
            decompress_to(r.data['jpeg'], img, PF.RGB)