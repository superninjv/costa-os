---
l0: "Screenshots with AI analysis: grim+slurp capture, OCR text extraction, AI error detection, screen recording"
l1_sections: ["Basic Screenshots", "Screenshot Keybinds", "AI Screenshot Analysis", "OCR Text Extraction", "Error Detection", "Screen Recording", "Color Picker", "Screenshot Directory", "Clipboard Operations"]
tags: [screenshot, capture, grim, slurp, ocr, ai, error-detection, screen-record, wf-recorder, clipboard, wl-copy, color-picker, analysis]
---

# Screenshots & AI Analysis

## Basic Screenshots

### How do I take a screenshot of a region?
```bash
# Save to file
grim -g "$(slurp)" ~/Pictures/Screenshots/screenshot-$(date +%Y%m%d-%H%M%S).png

# Copy to clipboard
grim -g "$(slurp)" - | wl-copy
```

### How do I take a full-screen screenshot?
```bash
grim ~/Pictures/Screenshots/screenshot-$(date +%Y%m%d-%H%M%S).png
```

### How do I screenshot a specific monitor?
```bash
grim -o DP-1 screenshot.png
grim -o HDMI-A-1 screenshot.png
```

### How do I screenshot the active window?
```bash
grim -g "$(hyprctl activewindow -j | jq -r '"\(.at[0]),\(.at[1]) \(.size[0])x\(.size[1])"')" screenshot.png
```

## Screenshot Keybinds
- **Print** — screenshot region, save to ~/Pictures/Screenshots/
- **SUPER+Print** — screenshot region, copy to clipboard
- **SUPER+SHIFT+Print** — screenshot full screen
- **SUPER+SHIFT+A** — AI screenshot (select region, analyze with AI)

## AI Screenshot Analysis

### How do I analyze a screenshot with AI?
1. Press **SUPER+SHIFT+A** (or run `costa-screenshot --ai`)
2. Select a region with your mouse
3. The screenshot is sent to Claude Haiku for analysis
4. A notification shows the AI's analysis
5. Full response is copied to clipboard

The AI describes what it sees, identifies UI elements, reads text, and provides context about the content.

### How do I analyze an existing image?
```bash
costa-screenshot --ai --file /path/to/image.png
```

## OCR Text Extraction

### How do I extract text from my screen?
1. Press **SUPER+SHIFT+T** (or run `costa-screenshot --ocr`)
2. Select a region containing text
3. Extracted text is copied to clipboard and saved to `/tmp/costa-ocr-latest.txt`
4. A notification confirms with a preview of the extracted text

### How do I OCR an existing image?
```bash
costa-screenshot --ocr --file /path/to/image.png
```

### What OCR engine is used?
Tesseract OCR — installed as a base dependency. Supports multiple languages.
```bash
# Install additional language packs
sudo pacman -S tesseract-data-spa  # Spanish
sudo pacman -S tesseract-data-fra  # French
```

## Error Detection

### How does automatic error detection work?
When you take an AI screenshot (SUPER+SHIFT+A) and the image contains an error message, stack trace, or failure output:
1. AI detects it's an error and classifies the type (compiler, runtime, config, network, etc.)
2. Notification shows a concise diagnosis with suggested fix
3. Click "Apply Fix" if the suggestion involves a command
4. Click "Explain More" to get a detailed breakdown via costa-ai

### How do I screenshot an error and get help?
```bash
# Quick method: keybind
# 1. Press SUPER+SHIFT+A
# 2. Select the error on screen
# 3. Read the AI diagnosis in the notification

# CLI method:
grim -g "$(slurp)" /tmp/error-screenshot.png
costa-ai --image /tmp/error-screenshot.png "What is this error and how do I fix it?"
```

## Screen Recording

### How do I record my screen?
```bash
# Record a specific monitor
wf-recorder -o DP-1 -f recording.mp4

# Record a region
wf-recorder -g "$(slurp)" -f recording.mp4

# Record with audio
wf-recorder -a -f recording.mp4

# Stop recording
killall wf-recorder
```
Install if missing: `sudo pacman -S wf-recorder`

## Color Picker

### How do I pick a color from my screen?
```bash
# Click anywhere to get the hex color
hyprpicker

# Copy hex to clipboard automatically
hyprpicker -a
```

## Screenshot Directory
- Default location: `~/Pictures/Screenshots/`
- Created automatically during first-boot
- AI analysis results saved alongside screenshots as `.txt` files

## Clipboard Operations

### How do I copy an image to clipboard?
```bash
# From a screenshot
grim -g "$(slurp)" - | wl-copy

# From an existing file
wl-copy < image.png
```

### How do I paste an image from clipboard?
```bash
wl-paste > output.png
```

### How do I view clipboard history?
Press **SUPER+V** to open clipboard history in rofi. Works for both text and images.
```bash
cliphist list | rofi -dmenu | cliphist decode | wl-copy
```

### How do I clear clipboard history?
```bash
cliphist wipe
```
