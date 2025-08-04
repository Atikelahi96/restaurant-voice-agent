from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from sqlmodel import SQLModel, Field, Relationship, select, Session
from .menu import Menu  # Ensure Menu is imported correctly

class OrderItem(SQLModel, table=True):
    __tablename__ = "order_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id")
    menu_id: int = Field(foreign_key="menu.id")
    quantity: int = 1

    menu: Optional["Menu"] = Relationship()  # Use Optional["Menu"], without Mapped
    order: Optional["Order"] = Relationship(back_populates="items")  # Forward reference as string

class Order(SQLModel, table=True):
    __tablename__ = "orders"

    id: Optional[int] = Field(default=None, primary_key=True)
    status: str = "draft"
    channel: str  # e.g. "audio" or "text"
    total: Decimal = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    items: List[OrderItem] = Relationship(back_populates="order")

    @classmethod
    def get_or_create_draft(cls, sess: Session, *, channel: str) -> "Order":  # Forward reference as string
        stmt = select(cls).where(cls.channel == channel, cls.status == "draft")
        existing = sess.exec(stmt).one_or_none()
        if existing:
            return existing
        new = cls(channel=channel)
        sess.add(new); sess.commit(); sess.refresh(new)
        return new

    def add_line(self, sess: Session, menu_id: int, qty: int = 1):
        sess.add(OrderItem(order_id=self.id, menu_id=menu_id, quantity=qty))
        sess.commit()
        self._recalc_total(sess)

    def _recalc_total(self, sess: Session):
        sess.refresh(self, attribute_names=["items"])
        self.total = sum(li.quantity * li.menu.price for li in self.items)
        sess.add(self); sess.commit()

    @classmethod
    def finalize_latest(cls, sess: Session, *, channel: str) -> "Order":  # Forward reference as string
        order = cls.get_or_create_draft(sess, channel=channel)
        order.status = "submitted"
        order._recalc_total(sess)
        return order
