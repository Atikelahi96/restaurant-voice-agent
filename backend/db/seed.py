# backend/db/seed.py
"""
One-shot bootstrap: creates tables + seed sample menu & ensures orders table exists.
Run with:
    python -m backend.db.seed
"""
from backend.db.session import init_db, SessionLocal

# 🔁 Ensure both models are imported so SQLModel metadata sees them:
from backend.models.menu import Menu
from backend.models.order import Order, OrderItem  # <-- import these

from sqlmodel import select

def run():
    init_db()  # Creates all registered tables

    with SessionLocal() as session:
        if session.exec(select(Menu)).first():
            print("Menu already seeded – skipping.")
            return

        session.add_all([
            Menu(name="Espresso", price=2.50),
            Menu(name="Americano", price=3.00),
            Menu(name="Latte", price=5.00),
            Menu(name="Cappuccino", price=4.50),
            Menu(name="Flat White", price=4.00),
            Menu(name="GF Blueberry Muffin", price=3.50, is_gluten_free=True),
            Menu(name="Almond Croissant", price=4.00, is_gluten_free=True),
        ])
        session.commit()
        print("✅  Seeded sample menu.")

if __name__ == "__main__":
    run()
