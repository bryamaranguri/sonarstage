"""Audio decoding through ffmpeg."""
import subprocess

import numpy as np


def decode(path, sr=44100, mono=False):
    """Decode any audio file to float32 with shape (frames, channels).

    ffmpeg honours MP3 gapless headers (LAME/Xing) and AAC priming metadata, so the
    encoder delay is removed. A naive decoder would shift AAC stems by ~60 ms.
    """
    channels = 1 if mono else 2
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-f", "f32le", "-acodec", "pcm_f32le",
        "-ac", str(channels), "-ar", str(sr), "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, channels)


def probe(path):
    """Codec, sample rate, channels, bitrate and duration of a file."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels,bit_rate:format=duration",
        "-of", "default=noprint_wrappers=1", str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    info = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
    return {
        "codec": info.get("codec_name"),
        "sample_rate": int(info["sample_rate"]) if info.get("sample_rate") else None,
        "channels": int(info["channels"]) if info.get("channels") else None,
        "bitrate_kbps": round(int(info["bit_rate"]) / 1000) if info.get("bit_rate", "N/A").isdigit() else None,
        "duration_s": round(float(info["duration"]), 3) if info.get("duration") else None,
    }
