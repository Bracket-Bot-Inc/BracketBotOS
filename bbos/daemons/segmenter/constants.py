from bbos.registry import *
from bbos.tf import *
import numpy as np

CFG_D = Config('depth')

@register
class segmenter:
    model_name = "yolov8n-seg-floor"
    classes = ['floor', 'ground', 'floor ground'] # COCO + custom classes for nav
    iou = 0.8
    mask_threshold = 0.5
    conf = 0.6
    segment_only = ['floor', 'ground', 'floor ground']
    class2mask = {j: i for i, j in enumerate(classes)}
    @staticmethod
    def combine_masks(masks, seg_cls): # (N,H,W), (N,)
        seg_cls = seg_cls.reshape(-1, 1) + 1 # +1 because 0 is background (N,1)
        k = np.arange(len(seg_cls)).reshape(-1, 1) # (N,1)
        return (masks * (seg_cls + k * len(segmenter.classes)).reshape(-1, 1, 1)).sum(axis=0) # (H,W)
    @staticmethod
    def filter_by(segmenter_mask, filt_classes):
        filt_classes = np.array([segmenter.class2mask[c] for c in filt_classes]) + 1
        filtered = np.isin(segmenter_mask['mask'] % len(segmenter.classes), filt_classes)
        return segmenter_mask['mask'][filtered]

@realtime(ms=100)
def segmenter_mask():
    return [
        ("mask", np.uint16, (CFG_D.height_D, CFG_D.width_D)), 
    ]