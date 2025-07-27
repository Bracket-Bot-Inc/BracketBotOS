from bbos import register, realtime
from bbos.os_utils import Priority

import numpy as np


# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class speakerphone:
    speaker_device = 0
    mic_device = 0
    speaker_sample_rate: int = 48_000
    mic_sample_rate: int = 48_000
    speaker_channels: int = 2
    mic_channels: int = 1
    update_rate: int = 50
    speaker_chunk_size: int = speaker_sample_rate // update_rate
    mic_chunk_size: int= mic_sample_rate // update_rate


# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------
@realtime(50, Priority.CTRL_HIGH, [2, 3])
def speakerphone_audio(chunk_size, channels):
    return [
        ("audio", np.int16, (chunk_size, channels)),  # chunk_size, channels
    ]