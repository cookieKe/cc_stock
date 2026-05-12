from sqlalchemy.orm import Session
from backend.notification.base import NotificationChannel
from backend.models.notification import Notification


class InAppChannel(NotificationChannel):
    name = "inapp"

    def __init__(self, db: Session):
        self.db = db

    def send(self, title: str, content: str, recipient: str = "") -> bool:
        notif = Notification(
            channel="inapp",
            title=title,
            content=content,
            status="sent",
        )
        self.db.add(notif)
        self.db.commit()
        return True
