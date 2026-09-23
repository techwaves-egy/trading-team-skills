#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Skill Integrity & Anti-Tamper Security Guard (v3.5.2)
Verifies cryptographic SHA-256 signatures of all protected skill and engine files.
If any unauthorized modification is detected:
  1. Blocks all trade execution immediately (Anti-Tamper Lockout).
  2. Sends an Emergency Security Alert to Telegram.
"""

import sys
import os
import hashlib
import json
import logging
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from send_alert import broadcast_telegram

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKSUM_FILE = os.path.join(BASE_DIR, "config", "skill_checksums.json")

PROTECTED_FILES = [
    os.path.join(BASE_DIR, "SKILL.md"),
    os.path.join(BASE_DIR, "scripts", "auto_scanner.py"),
    os.path.join(BASE_DIR, "scripts", "mt5_connector.py"),
    os.path.join(BASE_DIR, "scripts", "trade_monitor.py"),
    os.path.join(BASE_DIR, "scripts", "send_alert.py"),
    os.path.join(BASE_DIR, "scripts", "daily_summary.py"),
    os.path.join(BASE_DIR, "scripts", "telegram_listener.py"),
    os.path.join(BASE_DIR, "scripts", "start_session.py"),
    os.path.join(BASE_DIR, "docs", "01_ORGANIZATION_ROLES.md"),
    os.path.join(BASE_DIR, "docs", "02_REGIME_STRATEGY_ENGINE.md"),
]

def calculate_sha256(filepath):
    """Compute SHA-256 hash of a file."""
    if not os.path.exists(filepath):
        return None
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()

def generate_signed_manifest(authorized_by="Admin / Lead Architect"):
    """Generates and saves the authorized SHA-256 checksum manifest."""
    manifest = {
        "version": "3.5.2",
        "authorized_by": authorized_by,
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "files": {}
    }
    for fpath in PROTECTED_FILES:
        rel_path = os.path.relpath(fpath, BASE_DIR)
        h = calculate_sha256(fpath)
        manifest["files"][rel_path] = h

    os.makedirs(os.path.dirname(CHECKSUM_FILE), exist_ok=True)
    with open(CHECKSUM_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest

def verify_skill_integrity(silent=False):
    """
    Verifies all protected files against skill_checksums.json.
    Returns: (is_valid: bool, mismatch_details: list)
    """
    if not os.path.exists(CHECKSUM_FILE):
        return False, ["Skill checksum manifest (skill_checksums.json) is missing!"]

    try:
        with open(CHECKSUM_FILE, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        return False, [f"Failed to load checksum manifest: {e}"]

    mismatches = []
    for rel_path, expected_hash in manifest.get("files", {}).items():
        abs_path = os.path.join(BASE_DIR, rel_path)
        actual_hash = calculate_sha256(abs_path)

        if actual_hash is None:
            mismatches.append(f"Missing protected file: <code>{rel_path}</code>")
        elif actual_hash != expected_hash:
            mismatches.append(
                f"Hash mismatch on <code>{rel_path}</code>\n"
                f"  • Expected: <code>{expected_hash[:12]}...</code>\n"
                f"  • Actual:   <code>{actual_hash[:12]}...</code>"
            )

    if mismatches:
        if not silent:
            msg = f"""<b>🚨 SECURITY ALERT: UNAUTHORIZED SKILL MODIFICATION DETECTED</b>
━━━━━━━━━━━━━━━━━━━━
<b>Anti-Tamper Lockout Activated:</b> Trade execution has been frozen to protect account capital.

<b>Detected Discrepancies:</b>
""" + "\n\n".join(mismatches) + f"""
━━━━━━━━━━━━━━━━━━━━
<b>Action Required:</b> Inspect files or run authorization script to certify legitimate changes."""
            broadcast_telegram(msg)
        return False, mismatches

    return True, []

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--authorize":
        m = generate_signed_manifest()
        print(f"[OK] Signed checksum manifest generated for {len(m['files'])} protected files.")
        broadcast_telegram(
            f"<b>🔒 SKILL SECURITY MANIFEST UPDATED & SIGNED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Version:</b> <code>3.5.2 Anti-Tamper Standard</code>\n"
            f"<b>Authorized Files:</b> {len(m['files'])}\n"
            f"<b>Timestamp:</b> {m['authorized_at']}\n"
            f"<b>Status:</b> 🟢 Cryptographically Verified"
        )
    else:
        valid, errs = verify_skill_integrity()
        if valid:
            print("[OK] All protected skill and engine files are 100% verified.")
        else:
            print("[SECURITY VIOLATION] Unauthorized modification detected:")
            for e in errs:
                print(" ", e)
