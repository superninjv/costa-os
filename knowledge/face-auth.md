---
l0: "Face authentication with Howdy: enroll, test, manage faces for login, sudo, and screen unlock via IR camera"
l1_sections: ["What Is Face Auth", "Requirements", "Setup", "Testing", "Managing Faces", "Where Face Auth Works", "Configuration", "Troubleshooting"]
tags: [face-auth, howdy, ir-camera, biometric, pam, login, sudo, hyprlock, greetd, security, unlock]
---

# Face Authentication

## What Is Face Auth
Costa OS supports Windows Hello-style face unlock using **Howdy** — a Linux face recognition system. Look at your IR camera to unlock your screen, authenticate sudo commands, and log in. Password always works as a fallback.

## Requirements
- IR camera (infrared camera, commonly found in laptops with Windows Hello support)
- Auto-detected during Costa OS first-boot via `v4l2-ctl`
- If no IR camera is detected, face auth setup is skipped automatically
- Regular webcams technically work but are far less secure (easier to spoof with photos)

## Setup

### How do I set up face authentication?
**Option 1: Settings Hub**
1. Open Settings Hub (click gear icon in the shell bar, or run `costa-settings`)
2. Go to Security → Face Authentication
3. Click "Enroll Face"
4. Position your face in front of the IR camera
5. Hold still for 2-3 seconds while it captures

**Option 2: Terminal**
```bash
# Enroll your face
sudo howdy add

# Follow the prompts — look directly at the camera
# Enroll multiple times at different angles for better recognition
```

### How do I enroll multiple angles?
Run `sudo howdy add` multiple times. Each run creates a separate face model. Enrolling 3-5 models at different angles (straight on, slight left, slight right, with/without glasses) dramatically improves recognition reliability.

## Testing

### How do I test if face auth works?
```bash
sudo howdy test
```
This opens a camera preview window showing what Howdy sees. Green box = face detected and matched. Red box = face detected but not matched. The test does not authenticate anything — it just checks recognition.

### How do I test it for real?
Open a new terminal and run any `sudo` command:
```bash
sudo echo "Face auth works!"
```
If face auth is working, it authenticates instantly without typing your password. If it fails (wrong angle, low light), the password prompt appears normally.

## Managing Faces

### How do I list enrolled faces?
```bash
sudo howdy list
```
Shows all enrolled face models with their ID numbers and creation dates.

### How do I remove a face model?
```bash
sudo howdy remove <id>
```
Replace `<id>` with the number from `sudo howdy list`.

### How do I remove all face models?
```bash
sudo howdy clear
```

### How do I re-enroll from scratch?
```bash
sudo howdy clear
sudo howdy add    # repeat 3-5 times at different angles
sudo howdy test   # verify it works
```

## Where Face Auth Works

### Login (greetd)
Face auth runs when tuigreet shows the login screen. Look at the camera and it logs you in automatically. If it fails, type your password as usual.

### Sudo
Any `sudo` command tries face auth first. Works in terminal and in GUI apps that request root (e.g., Settings Hub operations).

### Screen Lock (hyprlock)
When your screen locks (timeout or SUPER+L), look at the IR camera to unlock. The lock screen shows a brief "Looking for face..." indicator.

### Password Always Works
Face auth is configured as `sufficient` in PAM, not `required`. This means:
- Face recognized → authenticated immediately
- Face not recognized → falls through to password prompt
- No IR camera plugged in → password prompt immediately
- Howdy crashed → password prompt immediately

## Configuration

### How do I adjust face recognition sensitivity?
```bash
sudo howdy config
```
Key settings in `/lib/security/howdy/config.ini`:
- `certainty = 3.5` — match threshold (lower = stricter, higher = more lenient)
- `device_path` — path to IR camera (auto-detected during first-boot)
- `dark_threshold = 60` — minimum brightness to attempt recognition
- `timeout = 4` — seconds to wait before falling back to password

### How do I change the camera device?
```bash
# List all video devices
v4l2-ctl --list-devices

# Edit howdy config and set device_path
sudo howdy config
```

## Troubleshooting

### Face auth isn't working at all
```bash
# Check if howdy is installed
pacman -Q howdy

# Check if PAM is configured
grep howdy /etc/pam.d/sudo

# Check camera access
v4l2-ctl --list-devices
```

### "No face model" error
You haven't enrolled yet. Run `sudo howdy add`.

### Camera not found
```bash
# List video devices
v4l2-ctl --list-devices

# Look for IR camera (usually labeled "IR" or "Infrared")
# Update device_path in howdy config:
sudo howdy config
```

### Recognition is unreliable
- Enroll more angles: `sudo howdy add` (run 3-5 times)
- Check lighting — IR cameras work in the dark, but very bright backlighting can interfere
- Lower the certainty value (e.g., 3.0) for stricter matching with fewer false negatives
- Clean the IR camera lens

### How do I completely disable face auth?
```bash
# Remove howdy from PAM (disables for all services)
sudo sed -i '/howdy/d' /etc/pam.d/sudo
sudo sed -i '/howdy/d' /etc/pam.d/greetd
sudo sed -i '/howdy/d' /etc/pam.d/hyprlock
```

Or via Settings Hub → Security → Face Authentication → toggle off.
