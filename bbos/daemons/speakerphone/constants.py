from bbos import register, realtime

import numpy as np


# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class speakerphone:
    speaker_device = "ReSpeaker Lite"
    mic_device = "ReSpeaker Lite"
    speaker_sample_rate: int = 16_000
    speaker_channels: int = 1
    mic_sample_rate: int = 16_000
    mic_channels: int = 1
    speaker_ms: int = 100
    mic_ms: int = 100
    speaker_chunk_size: int = speaker_sample_rate // 1000 * speaker_ms
    mic_chunk_size: int = mic_sample_rate // 1000 * mic_ms
    mic_volume: float = 2
    speaker_volume: float = 0.3


# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------
@realtime(ms=10+speakerphone.speaker_ms)
def speakerphone_speaker():
    return [
        ("audio", np.int16, (speakerphone.speaker_chunk_size, speakerphone.speaker_channels)),  # chunk_size, channels
    ]

@realtime(ms=speakerphone.mic_ms)
def speakerphone_mic():
    return [
        ("audio", np.int16, (speakerphone.mic_chunk_size, speakerphone.mic_channels)),  # chunk_size, channels
    ]