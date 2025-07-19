from bbos.registry import register

import numpy as np


# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class speakerphone:
    device = 0
    sample_rate: int = 48_000
    gain: float = 8 # tuned gain for mic
    channels: int = 2
    chunk_size: int = 960
    update_rate: int = 50


# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------
@register
def speakerphone_audio():
    return [
        ("audio", np.float32, (speakerphone.chunk_size, speakerphone.channels)),  # chunk_size, channels
    ] 