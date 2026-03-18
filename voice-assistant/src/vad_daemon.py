#!/usr/bin/env python3
"""Persistent VAD daemon for push-to-talk.

Keeps Silero VAD model loaded in memory. Records audio and uses VAD
to detect when speech ends, then stops automatically.

Communication:
  /tmp/vad-cmd    — write "record /path/to/output.wav" to start
  /tmp/vad-status — daemon writes: ready, listening, speech, done, error
  /tmp/ptt.lock   — remove to force-stop (keybind toggle)
"""

import os
import signal
import subprocess
import sys
import time
import wave

import numpy as np
import torch

# --- Configuration (override via environment) ---
SAMPLE_RATE = int(os.environ.get("COSTA_VAD_SAMPLE_RATE", "16000"))
FRAME_SIZE = int(os.environ.get("COSTA_VAD_FRAME_SIZE", "512"))  # 32ms at 16kHz
DEEPFILTER_LADSPA = os.environ.get(
    "COSTA_DEEPFILTER_LADSPA", "/usr/lib/ladspa/libdeep_filter_ladspa.so"
)
VAD_THRESHOLD = float(os.environ.get("COSTA_VAD_THRESHOLD", "0.25"))
SILENCE_AFTER = float(os.environ.get("COSTA_VAD_SILENCE_AFTER", "1.5"))
MAX_DURATION = float(os.environ.get("COSTA_VAD_MAX_DURATION", "15.0"))

LOCKFILE = "/tmp/ptt.lock"
CMD_FILE = "/tmp/vad-cmd"
STATUS_FILE = "/tmp/vad-status"
PID_FILE = "/tmp/vad-daemon.pid"
LOG_FILE = "/tmp/vad-debug.log"


def write_status(status):
    with open(STATUS_FILE, "w") as f:
        f.write(status)


def load_model():
    torch.set_num_threads(1)
    model, _ = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        trust_repo=True,
    )
    return model


def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def do_recording(model, output_path, max_duration=None, threshold=None,
                 silence_after=None):
    """Record with real-time VAD auto-stop."""
    max_duration = max_duration or MAX_DURATION
    threshold = threshold or VAD_THRESHOLD
    silence_after = silence_after or SILENCE_AFTER

    write_status("listening")

    # Record to file (not pipe — pw-cat pipe has SPA header issues)
    proc = subprocess.Popen(
        ["pw-cat", "--record", "--format=s16", f"--rate={SAMPLE_RATE}",
         "--channels=1", output_path],
        stderr=subprocess.DEVNULL,
    )

    start = time.monotonic()
    speech_detected = False
    silent_checks = 0  # consecutive checks with no speech

    try:
        # Let recording accumulate
        time.sleep(1.5)

        while time.monotonic() - start < max_duration:
            if not os.path.exists(LOCKFILE):
                break

            time.sleep(0.3)  # DeepFilterNet takes ~0.6s, so effective interval ~1s

            # Extract last 1s of audio, clean with DeepFilterNet, then VAD
            try:
                file_size = os.path.getsize(output_path)
                pcm_size = file_size - 44
                if pcm_size < SAMPLE_RATE * 2:
                    continue

                # Extract last 1s as temp wav
                want_bytes = int(1.0 * SAMPLE_RATE) * 2
                read_start = max(44, file_size - want_bytes)
                with open(output_path, "rb") as f:
                    f.seek(read_start)
                    raw_data = f.read()
                raw_data = raw_data[:len(raw_data) - (len(raw_data) % 2)]
                if len(raw_data) < FRAME_SIZE * 2:
                    continue

                # Write chunk to temp wav for DeepFilterNet
                chunk_wav = "/tmp/vad-chunk.wav"
                with wave.open(chunk_wav, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(raw_data)

                # DeepFilterNet: upsample -> filter -> downsample
                clean_wav = "/tmp/vad-chunk-clean.wav"
                subprocess.run(
                    ["sox", chunk_wav, "-r", "48000", "/tmp/vad-c48.wav"],
                    check=True, capture_output=True, timeout=3)
                subprocess.run(
                    ["sox", "/tmp/vad-c48.wav", "/tmp/vad-cc.wav", "ladspa",
                     DEEPFILTER_LADSPA, "deep_filter_mono"],
                    check=True, capture_output=True, timeout=5)
                subprocess.run(
                    ["sox", "/tmp/vad-cc.wav", "-r", str(SAMPLE_RATE), clean_wav],
                    check=True, capture_output=True, timeout=3)

                # Read cleaned audio
                with wave.open(clean_wav, "rb") as wf:
                    data = wf.readframes(wf.getnframes())

                # Cleanup temp files
                for f in [chunk_wav, "/tmp/vad-c48.wav", "/tmp/vad-cc.wav", clean_wav]:
                    try:
                        os.unlink(f)
                    except OSError:
                        pass

            except Exception as e:
                log(f"clean error: {e}")
                continue

            data = data[:len(data) - (len(data) % 2)]
            if len(data) < FRAME_SIZE * 2:
                continue

            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            wav_tensor = torch.from_numpy(samples)

            # Run VAD on this 1s chunk — count how many frames have speech
            model.reset_states()
            speech_frames = 0
            total_frames = 0

            for i in range(0, len(samples) - FRAME_SIZE, FRAME_SIZE):
                chunk = wav_tensor[i:i + FRAME_SIZE]
                prob = model(chunk, SAMPLE_RATE).item()
                total_frames += 1
                if prob >= threshold:
                    speech_frames += 1

            speech_ratio = speech_frames / max(total_frames, 1)
            log(f"check: speech_frames={speech_frames}/{total_frames} ratio={speech_ratio:.2f} detected={speech_detected}")

            # Speech present if >20% of frames in this 1s window have speech
            if speech_ratio > 0.2:
                speech_detected = True
                write_status("speech")
                silent_checks = 0
            elif speech_detected:
                # No meaningful speech in this chunk
                silent_checks += 1
                # 1 silent check after speech = done (DeepFilterNet gives clean signal)
                if silent_checks >= 1:
                    log("speech ended — stopping")
                    break

    finally:
        proc.terminate()
        proc.wait()

    if speech_detected and os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        if file_size > 2000:
            write_status("done")
            return True

    # No speech — clean up
    try:
        os.unlink(output_path)
    except OSError:
        pass
    write_status("error")
    return False


def main():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    def cleanup(sig=None, frame=None):
        for f in [CMD_FILE, STATUS_FILE, PID_FILE]:
            try:
                os.unlink(f)
            except OSError:
                pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    write_status("loading")
    model = load_model()
    write_status("ready")

    try:
        os.unlink(CMD_FILE)
    except OSError:
        pass

    while True:
        try:
            if os.path.exists(CMD_FILE):
                with open(CMD_FILE) as f:
                    cmd = f.read().strip()
                os.unlink(CMD_FILE)

                current = ""
                try:
                    with open(STATUS_FILE) as f:
                        current = f.read().strip()
                except Exception:
                    pass

                # Reject if already busy
                if current in ("listening", "speech"):
                    log(f"rejected command (busy: {current})")
                    continue

                # Status is already "pending" (set by the PTT script)
                write_status("starting")

                if cmd.startswith("record "):
                    output_path = cmd[7:].strip()
                    log(f"recording to {output_path}")
                    do_recording(model, output_path)
                    write_status("ready")

            time.sleep(0.05)

        except Exception as e:
            write_status(f"error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
