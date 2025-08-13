from bbos import register, realtime
import numpy as np


# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class transcriber:
    chunk_ms: int = 4000 # ms
    overlap_ms: int = 3000 # ms
    sequence_length: int = 167 # upper bound of spoken characters within 2s window
    


# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------
@realtime(ms=100)
def transcriber_text():
    return [
        ("text", f"U{transcriber.sequence_length}")
    ]