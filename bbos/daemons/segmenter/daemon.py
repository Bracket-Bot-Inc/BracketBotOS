# Must be set before importing numpy/cv2
import os
from bracketbot_ai import Segmenter
from bbos import Writer, Config, Type, Reader
import numpy as np
import cv2

def main():
    CFG = Config('segmenter')
    CFG_D = Config('depth')
    seg = Segmenter(CFG.model_name, device=-1, classes=CFG.classes)
    with Writer('segmenter.mask', Type('segmenter_mask')) as w_mask, \
         Reader('camera.rect') as r_rect:
        mask = w_mask._buf.copy()
        mask = np.zeros((CFG_D.height_D, CFG_D.width_D), dtype=np.uint16)
        while True:
            if r_rect.ready():
                res = seg(r_rect.data['rect'], conf=CFG.conf, iou=CFG.iou, classes=CFG.segment_only, mask_threshold=CFG.mask_threshold)
                #cv2.imwrite("test_result.jpg", res.plot())
                if len(res) > 0:
                    seg_cls = res.boxes[:, -1].astype(np.uint16)
                    mask = CFG.combine_masks(res.masks, seg_cls)
                else:
                    mask = np.zeros((CFG_D.height_D, CFG_D.width_D), dtype=np.uint16)
            w_mask['mask'] = mask

if __name__ == "__main__":
    main()