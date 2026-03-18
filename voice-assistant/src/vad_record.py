#!/usr/bin/env python3
"""VAD-powered voice recorder for push-to-talk.

Pipeline: pw-cat -> DeepFilterNet (noise reduction) -> Silero VAD -> auto-stop

High noise floor microphones (e.g., Blue Snowball at ~0.2 RMS) require
DeepFilterNet pre-processing to crush noise to ~0.004 RMS before Silero
VAD can work reliably.

Exit codes:
    0 = speech recorded successfully
    1 = no speech detected
"""

import argparse
import os
import subprocess
import sys
import time
import wave

import numpy as np
import torch

# --- Configuration (override via environment) ---
SAMPLE_RATE = int(os.environ.get("COSTA_VAD_SAMPLE_RATE", "16000"))
DEEPFILTER_RATE = int(os.environ.get("COSTA_DEEPFILTER_RATE", "48000"))
DEEPFILTER_LADSPA = os.environ.get(
    "COSTA_DEEPFILTER_LADSPA", "/usr/lib/ladspa/libdeep_filter_ladspa.so"
)
LOCKFILE = "/tmp/ptt.lock"


def load_vad_model():
    torch.set_num_threads(1)
    model, _ = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        trust_repo=True,
    )
    return model


def check_speech_end(model, wav_path, threshold=0.2):
    """Check if speech has started and ended in the cleaned audio."""
    try:
        wf = wave.open(wav_path, "rb")
        n = wf.getnframes()
        if n < SAMPLE_RATE:
            wf.close()
            return False, False
        data = wf.readframes(n)
        wf.close()
    except Exception:
        return False, False

    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    wav_tensor = torch.from_numpy(samples)

    model.reset_states()
    frame_size = 512
    speech_found = False
    last_speech_frame = -1

    for i in range(0, len(samples) - frame_size, frame_size):
        chunk = wav_tensor[i:i + frame_size]
        prob = model(chunk, SAMPLE_RATE).item()
        if prob >= threshold:
            speech_found = True
            last_speech_frame = i

    if not speech_found:
        return False, False

    samples_since_speech = len(samples) - last_speech_frame
    silence_duration = samples_since_speech / SAMPLE_RATE
    return True, silence_duration >= 1.5


def clean_audio(raw_path, clean_path):
    """Run DeepFilterNet noise reduction on recorded audio."""
    tmp_48k = raw_path + ".48k.wav"
    tmp_clean_48k = raw_path + ".clean48k.wav"

    try:
        # Upsample to 48kHz (DeepFilterNet requirement)
        subprocess.run(
            ["sox", raw_path, "-r", str(DEEPFILTER_RATE), tmp_48k],
            check=True, capture_output=True,
        )
        # Apply DeepFilterNet
        subprocess.run(
            ["sox", tmp_48k, tmp_clean_48k, "ladspa",
             DEEPFILTER_LADSPA, "deep_filter_mono"],
            check=True, capture_output=True,
        )
        # Downsample back to 16kHz
        subprocess.run(
            ["sox", tmp_clean_48k, "-r", str(SAMPLE_RATE), clean_path],
            check=True, capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False
    finally:
        for f in [tmp_48k, tmp_clean_48k]:
            try:
                os.unlink(f)
            except OSError:
                pass


def record_with_vad(
    output_path: str,
    max_duration: float = 15.0,
    speech_threshold: float = 0.2,
):
    model = load_vad_model()

    raw_path = output_path + ".raw.wav"
    clean_path = output_path + ".clean.wav"

    # Start recording
    proc = subprocess.Popen(
        ["pw-cat", "--record", "--format=s16", f"--rate={SAMPLE_RATE}",
         "--channels=1", raw_path],
        stderr=subprocess.DEVNULL,
    )

    start_time = time.monotonic()
    speech_found = False

    try:
        while time.monotonic() - start_time < max_duration:
            if not os.path.exists(LOCKFILE):
                break

            time.sleep(0.8)
            elapsed = time.monotonic() - start_time

            if elapsed < 2.0:
                continue

            if clean_audio(raw_path, clean_path):
                found, ended = check_speech_end(model, clean_path, speech_threshold)
                if found:
                    speech_found = True
                if found and ended:
                    break
    finally:
        proc.terminate()
        proc.wait()

    # Final check if we haven't found speech yet
    if not speech_found:
        if clean_audio(raw_path, clean_path):
            speech_found, _ = check_speech_end(model, clean_path, speech_threshold)

    # Clean up
    try:
        os.unlink(clean_path)
    except OSError:
        pass

    if speech_found:
        os.rename(raw_path, output_path)
        return True
    else:
        try:
            os.unlink(raw_path)
        except OSError:
            pass
        return False


def main():
    parser = argparse.ArgumentParser(description="VAD-powered voice recorder")
    parser.add_argument("output", help="Output WAV file path")
    parser.add_argument("--max-duration", type=float, default=15.0)
    parser.add_argument("--threshold", type=float, default=0.2)
    args = parser.parse_args()

    success = record_with_vad(
        args.output,
        max_duration=args.max_duration,
        speech_threshold=args.threshold,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
