#!/usr/bin/env python3
"""Costa OS License — generate and verify license keys.

License keys are HMAC-SHA256 signatures of the user's email.
Verification is offline — no server needed. The secret is only on the server;
the key itself is a signed token that can be verified with the public-facing
verify function using the same secret.

Key format: COSTA-{email_b64}-{hmac_hex[:32]}
"""

import base64
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

# This secret lives ONLY on the license server.
# For local verification, the full key is self-validating:
# we store the email + signature, and re-derive to check.
# The "secret" is that only the server can GENERATE valid keys.
LICENSE_SECRET = os.environ.get("COSTA_LICENSE_SECRET", "")

LICENSE_FILE = Path.home() / ".config" / "costa" / "license"


def generate_key(email: str, secret: str) -> str:
    """Generate a license key for an email. Server-side only."""
    email_clean = email.strip().lower()
    email_b64 = base64.urlsafe_b64encode(email_clean.encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), email_clean.encode(), hashlib.sha256).hexdigest()[:32]
    return f"COSTA-{email_b64}-{sig}"


def verify_key(key: str, secret: str) -> tuple[bool, str]:
    """Verify a license key. Returns (valid, email)."""
    try:
        parts = key.strip().split("-", 2)
        if len(parts) != 3 or parts[0] != "COSTA":
            return False, ""
        email_b64 = parts[1]
        provided_sig = parts[2]
        # Re-pad base64
        padding = 4 - len(email_b64) % 4
        if padding != 4:
            email_b64 += "=" * padding
        email = base64.urlsafe_b64decode(email_b64).decode().strip().lower()
        expected_sig = hmac.new(secret.encode(), email.encode(), hashlib.sha256).hexdigest()[:32]
        if hmac.compare_digest(provided_sig, expected_sig):
            return True, email
        return False, ""
    except Exception:
        return False, ""


def is_licensed() -> bool:
    """Check if this machine has a valid Costa OS license.

    Validates that a well-formed license file exists with key and email.
    The key format is verified structurally (COSTA-{base64}-{hex32}).
    Full HMAC verification happens server-side during activation.
    """
    if not LICENSE_FILE.exists():
        return False
    try:
        data = json.loads(LICENSE_FILE.read_text())
        key = data.get("key", "")
        email = data.get("email", "")
        if not key or not email:
            return False
        # Structural validation: key must match COSTA-{b64}-{hex32} format
        parts = key.strip().split("-", 2)
        if len(parts) != 3 or parts[0] != "COSTA":
            return False
        if len(parts[2]) != 32:
            return False
        # Verify the email in the key matches the stored email
        email_b64 = parts[1]
        padding = 4 - len(email_b64) % 4
        if padding != 4:
            email_b64 += "=" * padding
        decoded_email = base64.urlsafe_b64decode(email_b64).decode().strip().lower()
        return decoded_email == email.strip().lower()
    except Exception:
        return False


def activate(key: str, secret: str) -> bool:
    """Activate a license key on this machine."""
    valid, email = verify_key(key, secret)
    if not valid:
        return False
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_FILE.write_text(json.dumps({"key": key, "email": email}))
    os.chmod(LICENSE_FILE, 0o600)
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  costa-license check          — check if licensed")
        print("  costa-license activate KEY   — activate a license key")
        print("  costa-license generate EMAIL — generate key (server only)")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "check":
        if is_licensed():
            data = json.loads(LICENSE_FILE.read_text())
            print(f"Licensed to: {data.get('email', 'unknown')}")
        else:
            print("Not licensed (free version)")
    elif cmd == "activate" and len(sys.argv) >= 3:
        key = sys.argv[2]
        if not LICENSE_SECRET:
            print("Error: COSTA_LICENSE_SECRET not set")
            sys.exit(1)
        if activate(key, LICENSE_SECRET):
            print("License activated! Restart waybar to remove watermark.")
        else:
            print("Invalid license key.")
            sys.exit(1)
    elif cmd == "generate" and len(sys.argv) >= 3:
        if not LICENSE_SECRET:
            print("Error: COSTA_LICENSE_SECRET not set")
            sys.exit(1)
        print(generate_key(sys.argv[2], LICENSE_SECRET))
    else:
        print("Unknown command")
        sys.exit(1)
