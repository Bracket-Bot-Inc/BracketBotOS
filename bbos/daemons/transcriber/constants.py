from bbos import register, realtime
import numpy as np


# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class transcriber:
    chunk_ms: int = 1000 # ms
    sequence_length: int = 167 # upper bound of spoken characters within 2s window
    context_chunk_count: int = 4


# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------
@realtime(ms=transcriber.chunk_ms)
def transcriber_text():
    return [
        ("text", f"S{transcriber.sequence_length}")
    ]