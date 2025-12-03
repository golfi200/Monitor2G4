# helper lib for audio output

import sys
import numpy as np
import sounddevice as sd

VERSION = "0.5.0"

# Audio
AUDIO_FS  = 16000      # Sample Rate
AUDIO_DUR = 1.0        # Sekunden pro Scan

DBM_MAX = -20
DBM_MIN = -90


# -------------------------------------------------------------
# Optional: Audio (sounddevice)
# -------------------------------------------------------------
try:
    import sounddevice as sd
    HAVE_AUDIO = True
except ImportError:
    print("sounddevice not found, audio disabled", file=sys.stderr)
    HAVE_AUDIO = False

# -------------------------------------------------------------
# Audio-Erzeugung aus MAX-Werten
# -------------------------------------------------------------
def max_to_audio(max_vals: np.ndarray) -> np.ndarray:
    """
    Erzeuge einen kurzen Audio-Buffer aus MAX-Werten:
    - Mapt jeden Kanal auf einen Sinus zwischen ca. 440..4400 Hz
    - Amplitude proportional zur (relativen) Stärke
    """
    n_ch = len(max_vals)
    if n_ch == 0:
        return np.zeros(int(AUDIO_FS * AUDIO_DUR), dtype=np.float32)

    # dBm -> Amplitude (relativ)
    vals = np.clip(max_vals.astype(np.float32), DBM_MIN, DBM_MAX)
    # Normierung: DBM_MIN -> 0.0, DBM_MAX -> 1.0
    amp = (vals - DBM_MIN) / float(DBM_MAX - DBM_MIN)  # 0..1
    amp = amp ** 2.0  # etwas stärker betonen

    t = np.linspace(0, AUDIO_DUR, int(AUDIO_FS * AUDIO_DUR), endpoint=False)
    audio = np.zeros_like(t, dtype=np.float32)

    f_min = 440.0
    f_max = 10 * f_min

    for i in range(n_ch):
        if amp[i] <= 0.0:
            continue
        f = f_min + (f_max - f_min) * (i / max(1, (n_ch - 1)))
        audio += amp[i] * np.sin(2.0 * np.pi * f * t, dtype=np.float32)

    max_abs = np.max(np.abs(audio))
    if max_abs > 0:
        audio /= max_abs

    return audio.astype(np.float32)

def play_audio(max_vals: np.ndarray):
    """Spielt ein Audio-Signal basierend auf den MAX-Werten ab."""
    if not HAVE_AUDIO:
        return
    audio_buf = max_to_audio(max_vals)
    sd.play(audio_buf, samplerate=AUDIO_FS, blocking=False)


