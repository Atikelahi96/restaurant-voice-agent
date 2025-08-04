from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select, Session
from backend.db.session import SessionLocal
from backend.models.order import Order

router = APIRouter(tags=["orders"])

# Dependency
def get_session():
    with SessionLocal() as sess:
        yield sess

# ---------------------------------------------------------------------------

@router.get("/orders")
def list_orders(sess: Session = Depends(get_session)):
    return sess.exec(select(Order).order_by(Order.created_at.desc())).all()

@router.get("/orders/{order_id}")
def get_order(order_id: int, sess: Session = Depends(get_session)):
    obj = sess.get(Order, order_id)
    if not obj:
        raise HTTPException(404, "Order not found")
    return obj
