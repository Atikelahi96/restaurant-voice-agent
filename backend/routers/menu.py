from fastapi import APIRouter, Depends
from sqlmodel import select, Session
from backend.db.session import SessionLocal
from backend.models.menu import Menu

router = APIRouter(tags=["menu"])

# Dependency
def get_session():
    with SessionLocal() as sess:
        yield sess

# ---------------------------------------------------------------------------

@router.get("/menu")
def list_menu(sess: Session = Depends(get_session)):
    return sess.exec(select(Menu)).all()

@router.post("/menu")
def create_menu_item(item: Menu, sess: Session = Depends(get_session)):
    sess.add(item)
    sess.commit()
    sess.refresh(item)
    return item
