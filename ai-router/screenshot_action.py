"""Costa AI Screenshot Action — capture a screen region and analyze it with AI.

Select a region with slurp, capture with grim, send to Claude Haiku for analysis.
Results shown as dunst notification and copied to clipboard.

Usage:
    python3 screenshot_action.py
"""

import subprocess
import sys
import os
import tempfile
from pathlib import Path


SCREENSHOT_PATH = "/tmp/costa-screenshot.png"


def notify(title: str, body: str, urgency: str = "normal", timeout: int = 10000):
    """Show a dunst notification."""
    subprocess.run([
        "notify-send", "-u", urgency, "-t", str(timeout),
        "-a", "Costa AI", title, body,
    ], check=False)


def clipboard_copy(text: str):
    """Copy text to Wayland clipboard."""
    try:
        subprocess.run(["wl-copy"], input=text, text=True, check=True, timeout=5)
    except Exception:
        pass


def capture_region() -> str | None:
    """Use slurp + grim to capture a screen region. Returns path or None if cancelled."""
    # Get region selection from slurp
    try:
        slurp = subprocess.run(
            ["slurp"],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return None

    if slurp.returncode != 0:
        # User cancelled selection (pressed Escape)
        return None

    geometry = slurp.stdout.strip()
    if not geometry:
        return None

    # Capture the selected region with grim
    try:
        result = subprocess.run(
            ["grim", "-g", geometry, SCREENSHOT_PATH],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            notify("Screenshot Error", f"grim failed: {result.stderr.strip()}", urgency="critical")
            return None
    except Exception as e:
        notify("Screenshot Error", str(e), urgency="critical")
        return None

    return SCREENSHOT_PATH


def _get_anthropic_key() -> str | None:
    """Read the Anthropic API key from environment or costa config."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_file = Path.home() / ".config" / "costa" / "env"
    try:
        for line in env_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def analyze_screenshot(image_path: str) -> str:
    """Send screenshot to Claude Haiku for analysis via the Anthropic API."""
    import base64
    import requests

    api_key = _get_anthropic_key()
    if not api_key:
        return "No Anthropic API key configured. Add one in ~/.config/costa/env"

    # Read and base64-encode the image
    try:
        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return f"Failed to read screenshot: {e}"

    prompt = (
        "Analyze this screenshot. What do you see? "
        "If it's an error, explain the fix. "
        "If it's code, explain it. "
        "If it's UI, describe it. "
        "If there is readable text, include an OCR transcription at the end under 'Text:'. "
        "Be concise (1-3 sentences for the analysis)."
    )

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_data,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            json=payload, headers=headers, timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            content = data.get("content", [])
            parts = [block["text"] for block in content if block.get("type") == "text"]
            return " ".join(parts).strip()
        return f"Claude API error: {resp.status_code} {resp.text[:200]}"
    except Exception as e:
        return f"Analysis error: {e}"


def extract_ocr_text(response: str) -> str | None:
    """Extract OCR text from the analysis response if present."""
    # Look for text after "Text:" label
    for marker in ("Text:", "OCR:", "Transcription:"):
        idx = response.find(marker)
        if idx != -1:
            return response[idx + len(marker):].strip()
    return None


def detect_error(response: str) -> bool:
    """Check if the analysis identifies an error."""
    error_keywords = [
        "error", "exception", "traceback", "failed", "failure",
        "crash", "bug", "issue", "problem", "fix",
        "stacktrace", "stack trace", "segfault", "panic",
    ]
    lower = response.lower()
    return any(kw in lower for kw in error_keywords)


def capture_and_analyze():
    """Full flow: capture screen region, analyze with AI, notify and copy result."""
    # Show a brief notification that we're starting
    notify("Screenshot AI", "Select a region...", timeout=3000)

    # Capture
    image_path = capture_region()
    if image_path is None:
        # User cancelled — exit silently
        return

    notify("Screenshot AI", "Analyzing...", timeout=5000)

    # Analyze
    response = analyze_screenshot(image_path)

    if not response:
        notify("Screenshot AI", "No response from AI.", urgency="critical")
        cleanup()
        return

    # Copy full response to clipboard
    clipboard_copy(response)

    # Extract OCR text if present and copy that too
    ocr_text = extract_ocr_text(response)
    if ocr_text:
        # Write OCR text to a separate file for easy access
        Path("/tmp/costa-screenshot-ocr.txt").write_text(ocr_text)

    # Determine notification urgency and actions
    if detect_error(response):
        notify("Screenshot AI — Error Detected", response, urgency="critical", timeout=15000)
    else:
        notify("Screenshot AI", response, timeout=12000)

    # Print response to stdout as well (useful for piping)
    print(response)

    cleanup()


def cleanup():
    """Remove temporary screenshot file."""
    try:
        Path(SCREENSHOT_PATH).unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
    capture_and_analyze()
