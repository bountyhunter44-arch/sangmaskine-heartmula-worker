import base64
import os
import subprocess
import tempfile
from pathlib import Path

import runpod
import soundfile as sf
import torch
import torchaudio
from heartlib import HeartMuLaGenPipeline

MODEL_PATH = Path(os.getenv("HEARTMULA_MODEL_PATH", "/runpod-volume/heartlib/ckpt"))


def _soundfile_save(path, tensor, sample_rate, *args, **kwargs):
    """Avoid torchcodec/torchaudio incompatibilities on newer GPU workers."""
    audio = tensor.detach().to(torch.float32).cpu().numpy().T
    sf.write(str(path), audio, int(sample_rate))


torchaudio.save = _soundfile_save

if not MODEL_PATH.exists():
    raise RuntimeError(f"HeartMuLa model directory is missing: {MODEL_PATH}")

PIPELINE = HeartMuLaGenPipeline.from_pretrained(
    str(MODEL_PATH),
    device={"mula": torch.device("cuda"), "codec": torch.device("cuda")},
    dtype={"mula": torch.bfloat16, "codec": torch.float32},
    version="3B",
    lazy_load=True,
)


def _number(value, default, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def handler(job):
    data = job.get("input") or {}
    lyrics = str(data.get("lyrics") or "").strip()
    tags = str(data.get("tags") or "pop, catchy, vocal").strip()
    if not lyrics:
        return {"error": "lyrics_required"}
    if len(lyrics) > 12000:
        return {"error": "lyrics_too_long"}

    duration = int(_number(data.get("duration_seconds"), 225, 15, 240))
    topk = int(_number(data.get("topk"), 50, 1, 200))
    temperature = _number(data.get("temperature"), 1.0, 0.1, 2.0)
    cfg_scale = _number(data.get("cfg_scale"), 1.5, 1.0, 5.0)

    with tempfile.TemporaryDirectory(prefix="heartmula-") as temp_dir:
        temp = Path(temp_dir)
        lyrics_path = temp / "lyrics.txt"
        tags_path = temp / "tags.txt"
        wav_path = temp / "song.wav"
        mp3_path = temp / "song.mp3"
        lyrics_path.write_text(lyrics, encoding="utf-8")
        tags_path.write_text(tags, encoding="utf-8")

        with torch.no_grad():
            PIPELINE(
                {"lyrics": str(lyrics_path), "tags": str(tags_path)},
                max_audio_length_ms=duration * 1000,
                save_path=str(wav_path),
                topk=topk,
                temperature=temperature,
                cfg_scale=cfg_scale,
            )

        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame",
             "-b:a", "192k", str(mp3_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        audio = mp3_path.read_bytes()
        return {
            "audio_base64": base64.b64encode(audio).decode("ascii"),
            "content_type": "audio/mpeg",
            "file_size": len(audio),
            "duration_seconds": duration,
            "model": "HeartMuLa-oss-3B",
        }


runpod.serverless.start({"handler": handler})
