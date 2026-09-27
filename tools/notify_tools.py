"""
Notification tools - Agent-callable notification interfaces
WeChat notification + Dashboard push
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import shutil
import subprocess
from pydantic import BaseModel, Field
from tools.compat import BaseTool


# ── WeChat Notify ──────────────────────────────────────────────────────
class WechatNotifyInput(BaseModel):
    message: str = Field(description="Notification content")

class WechatNotifyTool(BaseTool):
    name: str = "wechat_notify"
    description: str = "Send notification via WeChat (trade alerts, risk warnings, etc.)"

    def _run(self, message: str = "", **kwargs) -> str:
        try:
            if not message:
                return json.dumps({"error": "please provide notification content"}, ensure_ascii=False)

            # Method 1: via openclaw CLI
            if shutil.which("openclaw"):
                result = subprocess.run(
                    ["openclaw", "message", "send", "--channel", "wechat-access", "--message", message[:2000]],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    return json.dumps({"success": True, "channel": "wechat"}, ensure_ascii=False)

            # Method 2: via wechat_notifier module
            try:
                import wechat_notifier as wn
                wn.send_message(message)
                return json.dumps({"success": True, "channel": "wechat_notifier"}, ensure_ascii=False)
            except:
                pass

            return json.dumps({"success": False, "note": "notification channel unavailable, check config"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Dashboard Push ──────────────────────────────────────────────────────
class DashboardNotifyInput(BaseModel):
    title: str = Field(description="Notification title")
    message: str = Field(description="Notification content")
    level: str = Field(default="info", description="Level: info/warning/error/success")

class DashboardNotifyTool(BaseTool):
    name: str = "dashboard_notify"
    description: str = "Push realtime notification to Dashboard (Agent status changes, trade decisions, etc.)"

    def _run(self, title: str = "", message: str = "", level: str = "info", **kwargs) -> str:
        try:
            # Write notification file (Dashboard polls and reads)
            notify_file = os.path.join(os.path.dirname(__file__), "..", "history", "notifications.json")
            os.makedirs(os.path.dirname(notify_file), exist_ok=True)

            notifications = []
            if os.path.exists(notify_file):
                try:
                    with open(notify_file, "r", encoding="utf-8") as f:
                        notifications = json.load(f)
                except:
                    notifications = []

            import time
            notifications.append({
                "title": title,
                "message": message,
                "level": level,
                "timestamp": time.time(),
            })

            # Keep last 50 notifications
            if len(notifications) > 50:
                notifications = notifications[-50:]

            with open(notify_file, "w", encoding="utf-8") as f:
                json.dump(notifications, f, ensure_ascii=False, indent=2)

            return json.dumps({"success": True, "note": "pushed to Dashboard"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Tool Registration ──────────────────────────────────────────────────────
def get_notify_tools() -> list:
    """Return all notification tools"""
    return [
        WechatNotifyTool(),
        DashboardNotifyTool(),
    ]
