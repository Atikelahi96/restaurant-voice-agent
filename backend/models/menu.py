from sqlmodel import SQLModel, Field
from typing import Optional
from decimal import Decimal

class Menu(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    price: Decimal
    is_gluten_free: bool = False
    is_available: bool = True

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "price": float(self.price),  # Convert Decimal to float
            "is_gluten_free": self.is_gluten_free,
            "is_available": self.is_available
        }

# Example usage
menu = Menu(id=1, name="Espresso", price=Decimal('2.5'), is_gluten_free=False, is_available=True)
menu_dict = menu.to_dict()
