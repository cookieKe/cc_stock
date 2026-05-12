import json
import httpx
from backend.notification.base import NotificationChannel
from backend.models.notification import Notification
from sqlalchemy.orm import Session


class IMBotChannel(NotificationChannel):
    name = "im_bot"

    def __init__(self, db: Session, webhook_url: str, bot_type: str = "wecom"):
        self.db = db
        self.webhook_url = webhook_url
        self.bot_type = bot_type

    def send(self, title: str, content: str, recipient: str = "") -> bool:
        try:
            payload = self._build_payload(title, content)
            with httpx.Client(timeout=10) as client:
                resp = client.post(self.webhook_url, json=payload)
            success = resp.status_code == 200
            self._log(title, content, "sent" if success else "failed", "" if success else resp.text)
            return success
        except Exception as e:
            self._log(title, content, "failed", str(e))
            return False

    def _build_payload(self, title: str, content: str) -> dict:
        full_text = f"## {title}\n{content}"
        if self.bot_type == "wecom":
            return {
                "msgtype": "markdown",
                "markdown": {"content": full_text},
            }
        elif self.bot_type == "dingtalk":
            return {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": full_text},
            }
        elif self.bot_type == "feishu":
            return {
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"tag": "plain_text", "content": title}},
                    "elements": [{"tag": "markdown", "content": content}],
                },
            }
        return {"text": full_text}

    def _log(self, title: str, content: str, status: str, error_msg: str):
        notif = Notification(
            channel="im_bot",
            title=title,
            content=content[:500],
            status=status,
            error_msg=error_msg[:500],
        )
        self.db.add(notif)
        self.db.commit()


class NotificationService:
    """统一推送服务：多渠道并行发送。"""

    def __init__(self, db: Session):
        self.db = db
        self.channels: list[NotificationChannel] = [InAppChannel(db)]

    def add_im_bot(self, webhook_url: str, bot_type: str = "wecom"):
        self.channels.append(IMBotChannel(self.db, webhook_url, bot_type))

    def broadcast(self, title: str, content: str) -> dict:
        results = {}
        for ch in self.channels:
            results[ch.name] = ch.send(title, content)
        return results

    def send_scan_report(self, scan_result: dict):
        from backend.notification.base import NotificationChannel
        title = f"A股扫描日报 {scan_result.get('scan_date', '')}"
        content = NotificationChannel.format_scan_report(scan_result)
        return self.broadcast(title, content)

    def send_tracker_report(self, tracker_stats: dict):
        from datetime import date
        from backend.notification.base import NotificationChannel
        title = f"追踪组合日报 {date.today()}"
        content = NotificationChannel.format_tracker_report(tracker_stats)
        return self.broadcast(title, content)
