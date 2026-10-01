#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Hardware-Bound Git Node Guard (v4.2.0)
Prevents unauthorized git commits and git pushes on secondary PC nodes.
Only the Master Primary Workstation (Waleed-IT) is authorized to commit or push code.
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "scripts"))

try:
    from skill_integrity_guard import is_master_primary_node, get_current_node_fingerprint, send_admin_telegram
except ImportError:
    # If cannot import, fallback to manual hostname check
    import socket
    def is_master_primary_node():
        return socket.gethostname().upper().strip() == "WALEED-IT"
    def get_current_node_fingerprint():
        return {"hostname": socket.gethostname().upper().strip(), "username": os.environ.get("USERNAME", "")}
    def send_admin_telegram(msg):
        pass


def enforce_git_node_lock():
    """Verify that git commit or push is originating strictly from Master Primary Node."""
    if not is_master_primary_node():
        fp = get_current_node_fingerprint()
        curr_host = fp.get("hostname", "UNKNOWN")
        curr_user = fp.get("username", "UNKNOWN")
        
        # Send security notification to Admin
        try:
            alert_msg = (
                f"🚨 <b>GIT VIOLATION: UNAUTHORIZED COMMIT/PUSH BLOCKED</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Attempted Action:</b> Git Commit / Push\n"
                f"<b>Rejected Node:</b> <code>{curr_host}</code> (Secondary Machine)\n"
                f"<b>User:</b> <code>{curr_user}</code>\n"
                f"<b>Status:</b> 🛑 <b>BLOCKED BY GIT NODE GUARD</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Repository modifications can only originate from Master Primary Node (Waleed-IT). "
                f"This secondary node is strictly READ-ONLY.</i>"
            )
            send_admin_telegram(alert_msg)
        except Exception:
            pass

        print("\n" + "=" * 65, file=sys.stderr)
        print("🚨 [GIT NODE LOCK VIOLATION] CODE COMMITS ARE BLOCKED ON THIS PC", file=sys.stderr)
        print("=" * 65, file=sys.stderr)
        print(f"Current Host:    {curr_host}", file=sys.stderr)
        print(f"Current User:    {curr_user}", file=sys.stderr)
        print("Node Status:     SECONDARY EXECUTION NODE (STRICTLY READ-ONLY)", file=sys.stderr)
        print("-" * 65, file=sys.stderr)
        print("All code modifications, git commits, and remote pushes MUST", file=sys.stderr)
        print("originate exclusively from the Master Primary Workstation (Waleed-IT).", file=sys.stderr)
        print("\nTo synchronize code on this secondary machine, use:", file=sys.stderr)
        print("    git pull origin master", file=sys.stderr)
        print("    git reset --hard origin/master", file=sys.stderr)
        print("=" * 65 + "\n", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


def install_git_hooks():
    """Install git pre-commit and pre-push hooks to enforce node lock."""
    hooks_dir = os.path.join(BASE_DIR, ".git", "hooks")
    if not os.path.exists(hooks_dir):
        return False

    hook_script = f"""#!/bin/sh
# AI Autonomous Trading Firm — Hardware-Bound Git Hook
python "{os.path.join(BASE_DIR, 'scripts', 'git_node_guard.py')}"
"""
    for hook_name in ("pre-commit", "pre-push"):
        hook_path = os.path.join(hooks_dir, hook_name)
        try:
            with open(hook_path, "w", encoding="utf-8") as f:
                f.write(hook_script)
        except Exception as e:
            print(f"[WARN] Failed to install {hook_name} hook: {e}", file=sys.stderr)
            return False
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--install":
        ok = install_git_hooks()
        if ok:
            print("[OK] Hardware-bound git pre-commit and pre-push hooks installed successfully.")
        else:
            print("[ERROR] Failed to install git hooks.")
    else:
        enforce_git_node_lock()
