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
import time
import socket
import uuid
from datetime import datetime, timezone

try:
    import winreg
except ImportError:
    winreg = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from send_alert import broadcast_telegram, send_admin_telegram

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKSUM_FILE = os.path.join(BASE_DIR, "config", "skill_checksums.json")

# Master Primary Workstation Hardware Fingerprint (Waleed Talaat Workstation)
MASTER_PRIMARY_NODE = {
    "hostname": "WALEED-IT",
    "username": "WALEED.TALAAT",
    "machine_guid": "0e29ba84-3fba-49c9-8f41-2d25a81989b8",
    "mac_node": "0xcc15319204d1",
    "description": "Master Primary Workstation (Sole Authorized Modification Node)"
}

PROTECTED_FILES = [
    os.path.join(BASE_DIR, "SKILL.md"),
    os.path.join(BASE_DIR, "scripts", "auto_scanner.py"),
    os.path.join(BASE_DIR, "scripts", "news_analyzer.py"),
    os.path.join(BASE_DIR, "scripts", "git_node_guard.py"),
    os.path.join(BASE_DIR, "scripts", "mt5_connector.py"),
    os.path.join(BASE_DIR, "scripts", "trade_monitor.py"),
    os.path.join(BASE_DIR, "scripts", "send_alert.py"),
    os.path.join(BASE_DIR, "scripts", "daily_summary.py"),
    os.path.join(BASE_DIR, "scripts", "telegram_listener.py"),
    os.path.join(BASE_DIR, "scripts", "start_session.py"),
    os.path.join(BASE_DIR, "docs", "01_ORGANIZATION_ROLES.md"),
    os.path.join(BASE_DIR, "docs", "02_REGIME_STRATEGY_ENGINE.md"),
]

PENDING_AUTH_FILE = os.path.join(BASE_DIR, "config", "pending_authorizations.json")
_last_alert_telemetry = {"time": 0.0, "hash_signature": ""}


def get_current_node_fingerprint():
    """Retrieve current hardware and machine node fingerprint."""
    try:
        hostname = socket.gethostname().upper().strip()
    except Exception:
        hostname = "UNKNOWN_HOST"

    try:
        username = os.getlogin().upper().strip()
    except Exception:
        username = os.environ.get("USERNAME", "UNKNOWN_USER").upper().strip()

    machine_guid = ""
    if winreg:
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            val, _ = winreg.QueryValueEx(k, "MachineGuid")
            machine_guid = str(val).strip().lower()
        except Exception:
            pass

    try:
        mac_node = hex(uuid.getnode())
    except Exception:
        mac_node = ""

    return {
        "hostname": hostname,
        "username": username,
        "machine_guid": machine_guid,
        "mac_node": mac_node
    }


def is_master_primary_node():
    """
    Verify whether the current execution environment is the Master Primary Workstation.
    Only the Master Primary Node has authority to modify or certify protected files.
    """
    fp = get_current_node_fingerprint()

    # Hostname check
    if fp["hostname"] == MASTER_PRIMARY_NODE["hostname"]:
        # Verify machine GUID if on Windows
        if fp["machine_guid"] and fp["machine_guid"] == MASTER_PRIMARY_NODE["machine_guid"].lower():
            return True
        # If machine GUID couldn't be read or matched, verify MAC or username
        if fp["mac_node"] == MASTER_PRIMARY_NODE["mac_node"] or fp["username"] == MASTER_PRIMARY_NODE["username"]:
            return True

    return False


def calculate_sha256(filepath):
    """Compute SHA-256 hash of a file."""
    if not os.path.exists(filepath):
        return None
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()


def generate_signed_manifest(authorized_by="Admin / Lead Architect", force_node_check=True):
    """Generates and saves the authorized SHA-256 checksum manifest."""
    fp = get_current_node_fingerprint()

    if force_node_check and not is_master_primary_node():
        curr_host = fp["hostname"]
        curr_guid = fp["machine_guid"]
        msg = (
            f"🚨 <b>SECURITY VIOLATION: UNAUTHORIZED NODE LOCK ATTEMPT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Action Blocked:</b> Manifest Re-Certification (<code>--authorize</code>)\n"
            f"<b>Attempted Node:</b> <code>{curr_host}</code> (Secondary Machine)\n"
            f"<b>User:</b> <code>{fp['username']}</code>\n"
            f"<b>Status:</b> 🛑 <b>BLOCKED &amp; LOGGED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Skill modifications are strictly restricted to Master Primary Node 'Waleed-IT'. "
            f"Secondary machines are locked in READ-ONLY mode.</i>"
        )
        send_admin_telegram(msg)
        print(f"\n[SECURITY LOCKOUT] Modification authority is strictly RESTRICTED to Master Primary Node 'Waleed-IT'.", file=sys.stderr)
        print(f"Current Host: '{curr_host}' is designated as a Secondary Read-Only Node.", file=sys.stderr)
        print(f"To update this machine, use 'git pull origin master'. Local modifications are forbidden.\n", file=sys.stderr)
        sys.exit(1)

    # Ensure git hooks are active on primary node
    try:
        from git_node_guard import install_git_hooks
        install_git_hooks()
    except Exception:
        pass

    manifest = {
        "version": "4.2.0-node-locked",
        "master_node": MASTER_PRIMARY_NODE["hostname"],
        "node_fingerprint_hash": hashlib.sha256(f"{fp['hostname']}:{fp['machine_guid']}".encode()).hexdigest()[:16],
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


def get_pending_authorizations():
    """Retrieve active pending authorization requests."""
    if not os.path.exists(PENDING_AUTH_FILE):
        return {}
    try:
        with open(PENDING_AUTH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_pending_authorizations(data):
    """Save pending authorization requests."""
    os.makedirs(os.path.dirname(PENDING_AUTH_FILE), exist_ok=True)
    with open(PENDING_AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def create_pending_authorization(mismatches):
    """Creates a new pending authorization request with a unique 4-character token."""
    import secrets
    token = secrets.token_hex(2).upper()
    auths = get_pending_authorizations()
    auths[token] = {
        "token": token,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mismatches": mismatches,
        "status": "PENDING"
    }
    save_pending_authorizations(auths)
    return token


def approve_pending_authorization(token=None, approved_by="Telegram Admin", notify=True):
    """
    Approves pending modifications remotely from Telegram:
    1. Re-signs all protected files cryptographically.
    2. Marks authorization approved.
    3. Broadcasts clearance alert to Telegram.
    """
    auths = get_pending_authorizations()
    target_token = None
    if token:
        cleaned = str(token).upper().strip().replace("#", "")
        if cleaned in auths:
            target_token = cleaned
    else:
        pending_tokens = [k for k, v in auths.items() if v.get("status") == "PENDING"]
        if pending_tokens:
            target_token = pending_tokens[-1]

    manifest = generate_signed_manifest(authorized_by=approved_by)

    if target_token and target_token in auths:
        auths[target_token]["status"] = "APPROVED"
        auths[target_token]["approved_by"] = approved_by
        auths[target_token]["approved_at"] = datetime.now(timezone.utc).isoformat()
        save_pending_authorizations(auths)
    else:
        auths["LATEST"] = {
            "token": target_token or "DIRECT",
            "status": "APPROVED",
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat()
        }
        save_pending_authorizations(auths)

    msg = (
        f"<b>🔒 SKILL MODIFICATION APPROVED VIA TELEGRAM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Status:</b> 🟢 <b>Cryptographically Verified &amp; Certified</b>\n"
        f"<b>Authorized By:</b> <code>{approved_by}</code>\n"
        f"<b>Timestamp:</b> <code>{manifest['authorized_at']}</code>\n"
        f"<b>Protected Files:</b> {len(manifest['files'])} signed\n"
        f"<b>Anti-Tamper Lockout:</b> 🟢 <b>LIFTED — System Resumed</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>All execution gates cleared for active trading.</i>"
    )
    if notify:
        send_admin_telegram(msg)
    return True, msg


def reject_pending_authorization(token=None, rejected_by="Telegram Admin", notify=True):
    """Rejects pending modifications and maintains the Anti-Tamper Lockout."""
    auths = get_pending_authorizations()
    target_token = None
    if token:
        cleaned = str(token).upper().strip().replace("#", "")
        if cleaned in auths:
            target_token = cleaned
            auths[target_token]["status"] = "REJECTED"
            auths[target_token]["rejected_by"] = rejected_by
            auths[target_token]["rejected_at"] = datetime.now(timezone.utc).isoformat()
    else:
        for k, v in auths.items():
            if v.get("status") == "PENDING":
                v["status"] = "REJECTED"
                v["rejected_by"] = rejected_by
                v["rejected_at"] = datetime.now(timezone.utc).isoformat()
    save_pending_authorizations(auths)

    msg = (
        f"<b>🛑 SKILL MODIFICATION REJECTED VIA TELEGRAM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Status:</b> 🔒 <b>Anti-Tamper Lockout Maintained</b>\n"
        f"<b>Action By:</b> <code>{rejected_by}</code>\n"
        f"<b>Notice:</b> Modifications remain unauthorized. Trade execution will continue to be blocked until restored or validly certified.\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    if notify:
        send_admin_telegram(msg)
    return True, msg


def verify_skill_integrity(silent=False, force_alert=False):
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

    # Verify that manifest was certified by Master Primary Node
    expected_master = MASTER_PRIMARY_NODE["hostname"]
    actual_master = manifest.get("master_node")
    if actual_master and actual_master != expected_master:
        return False, [f"Untrusted manifest: Certified by unauthorized node '{actual_master}' (Expected: '{expected_master}')"]

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
            now = time.time()
            sig = "|".join(mismatches)
            # Throttle alerts to avoid spamming if called repeatedly in loop
            if force_alert or (now - _last_alert_telemetry["time"] > 90) or (_last_alert_telemetry["hash_signature"] != sig):
                _last_alert_telemetry["time"] = now
                _last_alert_telemetry["hash_signature"] = sig
                token = create_pending_authorization(mismatches)
                reply_markup = {
                    "inline_keyboard": [
                        [
                            {"text": f"✅ Approve Modification ({token})", "callback_data": f"auth_approve_{token}"},
                            {"text": "❌ Reject", "callback_data": f"auth_reject_{token}"}
                        ]
                    ]
                }
                fp = get_current_node_fingerprint()
                node_label = "Master Node" if is_master_primary_node() else f"Secondary Node ({fp['hostname']})"
                msg = f"""<b>🚨 SECURITY ALERT: UNAUTHORIZED SKILL MODIFICATION DETECTED</b>
━━━━━━━━━━━━━━━━━━━━
<b>Node:</b> <code>{node_label}</code> (User: <code>{fp['username']}</code>)
<b>Anti-Tamper Lockout Activated:</b> Trade execution has been frozen to protect account capital.

<b>Detected Discrepancies:</b>
""" + "\n\n".join(mismatches) + f"""
━━━━━━━━━━━━━━━━━━━━
🔑 <b>Authorization Token:</b> <code>{token}</code>

👉 <b>Tap the button below</b> to approve or reject, or reply:
• <code>/approve {token}</code> (or simply <code>/approve</code>)
• <code>/reject {token}</code>"""
                send_admin_telegram(msg, reply_markup=reply_markup)
        return False, mismatches

    return True, []


verify_integrity = verify_skill_integrity


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--node-status":
        fp = get_current_node_fingerprint()
        is_master = is_master_primary_node()
        print("=" * 65)
        print("🏛️ AI AUTONOMOUS TRADING FIRM — HARDWARE NODE STATUS")
        print("=" * 65)
        print(f"Current Hostname:    {fp['hostname']}")
        print(f"Current User:        {fp['username']}")
        print(f"Machine GUID:        {fp['machine_guid']}")
        print(f"MAC Node:            {fp['mac_node']}")
        print("-" * 65)
        if is_master:
            print("Node Classification: 🟢 MASTER PRIMARY WORKSTATION")
            print("Access Level:        FULL AUTHORIZATION (COMMITS & RE-CERTIFICATION ENABLED)")
        else:
            print("Node Classification: 🔒 SECONDARY EXECUTION NODE")
            print("Access Level:        STRICTLY READ-ONLY (MODIFICATIONS & COMMITS FORBIDDEN)")
        print("=" * 65)
    elif len(sys.argv) > 1 and sys.argv[1] == "--authorize":
        m = generate_signed_manifest()
        print(f"[OK] Signed checksum manifest generated for {len(m['files'])} protected files.")
        send_admin_telegram(
            f"<b>🔒 SKILL SECURITY MANIFEST UPDATED & SIGNED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Node:</b> 🟢 <code>Master Primary Workstation ({m.get('master_node')})</code>\n"
            f"<b>Version:</b> <code>4.2.0 Node-Locked Anti-Tamper Standard</code>\n"
            f"<b>Authorized Files:</b> {len(m['files'])}\n"
            f"<b>Timestamp:</b> <code>{m['authorized_at']}</code>\n"
            f"<b>Status:</b> 🟢 Cryptographically Verified &amp; Certified"
        )
    elif len(sys.argv) > 1 and sys.argv[1] == "--approve":
        tok = sys.argv[2] if len(sys.argv) > 2 else None
        ok, res = approve_pending_authorization(tok, approved_by="CLI Admin")
        print(res)
    else:
        valid, errs = verify_skill_integrity()
        if valid:
            fp = get_current_node_fingerprint()
            node_tag = "Master Node" if is_master_primary_node() else f"Secondary Node ({fp['hostname']})"
            print(f"[OK] All protected skill and engine files are 100% verified. [{node_tag}]")
        else:
            print("[SECURITY VIOLATION] Unauthorized modification detected:")
            for e in errs:
                print(" ", e)
