from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.sql import func
from backend.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel = Column(String(20), nullable=False)
    recipient = Column(String(200), default="")
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    status = Column(String(20), default="pending")
    error_msg = Column(String(500), default="")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
