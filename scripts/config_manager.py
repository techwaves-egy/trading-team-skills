#!/usr/bin/env python3
"""
AI Autonomous Trading Firm — Credential & Notification Configuration Manager (v1.9.0)
Saves, updates, and persists multiple Telegram Chat IDs and Discord notification endpoints.
"""

import sys
import os
import json

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "alert_config.json")


def ensure_config_exists():
    """Ensure config directory and alert_config.json exist with default template."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        default_config = {
            "telegram": {"enabled": False, "bot_token": "", "chat_ids": [], "chat_id": ""},
            "discord": {"enabled": False, "webhook_url": ""},
            "settings": {
                "min_strategy_score_to_alert": 75,
                "alert_on_tp_sl_updates": True,
                "alert_on_regime_shifts": True,
                "sound_notification": True
            }
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)


def load_config() -> dict:
    ensure_config_exists()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"telegram": {"enabled": False, "bot_token": "", "chat_ids": []}, "discord": {"enabled": False, "webhook_url": ""}}


def save_config(config: dict) -> bool:
    ensure_config_exists()
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to write config: {e}", file=sys.stderr)
        return False


def set_telegram(bot_token: str, chat_id: str) -> dict:
    """Save and enable Telegram bot credentials and add chat_id."""
    config = load_config()
    config["telegram"]["enabled"] = True
    config["telegram"]["bot_token"] = bot_token.strip()
    
    chat_ids = config["telegram"].get("chat_ids", [])
    if str(chat_id).strip() not in [str(c) for c in chat_ids]:
        chat_ids.append(str(chat_id).strip())
    config["telegram"]["chat_ids"] = chat_ids
    config["telegram"]["chat_id"] = str(chat_id).strip()
    
    save_config(config)
    print(f"[SUCCESS] Telegram configured. Active Chat IDs: {chat_ids}")
    return config


def add_telegram_chat(chat_id: str) -> dict:
    """Add an additional Telegram Chat ID to the broadcast list."""
    config = load_config()
    chat_ids = config["telegram"].get("chat_ids", [])
    if str(chat_id).strip() not in [str(c) for c in chat_ids]:
        chat_ids.append(str(chat_id).strip())
        config["telegram"]["chat_ids"] = chat_ids
        save_config(config)
        print(f"[SUCCESS] Added Telegram Chat ID {chat_id}. All Active Chat IDs: {chat_ids}")
    else:
        print(f"[INFO] Chat ID {chat_id} is already in the active broadcast list.")
    return config


def set_discord(webhook_url: str) -> dict:
    """Save and enable Discord webhook credentials."""
    config = load_config()
    config["discord"]["enabled"] = True
    config["discord"]["webhook_url"] = webhook_url.strip()
    save_config(config)
    print("[SUCCESS] Discord webhook URL saved and enabled.")
    return config


def mask_string(s: str, keep_start: int = 4, keep_end: int = 4) -> str:
    if not s or s.startswith("YOUR_"):
        return "Not Configured"
    if len(s) <= (keep_start + keep_end):
        return "***"
    return f"{s[:keep_start]}...{s[-keep_end:]}"


def get_status() -> dict:
    """Get human-readable masked configuration status."""
    config = load_config()
    tg = config.get("telegram", {})
    dc = config.get("discord", {})
    
    tg_configured = tg.get("enabled", False) and bool(tg.get("bot_token")) and not tg.get("bot_token").startswith("YOUR_")
    dc_configured = dc.get("enabled", False) and bool(dc.get("webhook_url")) and not dc.get("webhook_url").startswith("YOUR_")
    
    status = {
        "telegram": {
            "status": "CONNECTED" if tg_configured else "NOT_CONFIGURED",
            "bot_token": mask_string(tg.get("bot_token", "")),
            "chat_ids": tg.get("chat_ids", [])
        },
        "discord": {
            "status": "CONNECTED" if dc_configured else "NOT_CONFIGURED",
            "webhook_url": mask_string(dc.get("webhook_url", ""), keep_start=25, keep_end=6)
        }
    }
    return status


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "telegram":
        set_telegram(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "add_chat":
        add_telegram_chat(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "discord":
        set_discord(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "status":
        st = get_status()
        print(json.dumps(st, indent=2))
    else:
        print("Usage:")
        print("  python config_manager.py telegram <BOT_TOKEN> <CHAT_ID>")
        print("  python config_manager.py add_chat <CHAT_ID>")
        print("  python config_manager.py discord <WEBHOOK_URL>")
        print("  python config_manager.py status")
