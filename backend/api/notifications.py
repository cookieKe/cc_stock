from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from backend.database import get_db
from backend.models.notification import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/")
def list_notifications(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    total = db.query(Notification).count()
    rows = (
        db.query(Notification)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "channel": r.channel,
                "title": r.title,
                "content": r.content,
                "status": r.status,
                "is_read": r.is_read,
                "created_at": str(r.created_at),
            }
            for r in rows
        ],
    }


@router.put("/{notif_id}/read")
def mark_read(notif_id: int, db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == notif_id).first()
    if n:
        n.is_read = True
        db.commit()
    return {"status": "ok"}


@router.put("/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.is_read == False).update({"is_read": True})  # noqa: E712
    db.commit()
    return {"status": "ok"}
