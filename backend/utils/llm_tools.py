import logging
from decimal import Decimal

from sqlmodel import select
from backend.db.session import SessionLocal
from backend.models import menu, order

from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams

log = logging.getLogger("llm-tools")

# ── Helper ──────────────────────────────────────────────────────────────
def _get_menu_item(name: str, session):
    stmt = select(menu.Menu).where(menu.Menu.name.ilike(f"%{name}%"))
    return session.exec(stmt).first()

def _safe_channel(params: FunctionCallParams) -> str:
    """Pipecat ≤ 0.0.77 doesn't attach `channel`; default gracefully."""
    return getattr(params, "channel", "default")

# ── LLM-CALLABLE FUNCTIONS ──────────────────────────────────────────────
async def list_menu(params: FunctionCallParams):
    with SessionLocal() as s:
        items = s.exec(select(menu.Menu)).all()

        serialised = []
        for i in items:
            d = i.dict(exclude_none=True)
            if isinstance(d.get("price"), Decimal):
                d["price"] = float(d["price"])         # JSON-safe
            serialised.append(d)

        await params.result_callback({"menu": serialised})

async def add_item(params: FunctionCallParams, item: str, qty: int = 1):
    with SessionLocal() as s:
        itm = _get_menu_item(item, s)
        if not itm:
            await params.result_callback({"error": f"'{item}' not found"})
            return

        chan = _safe_channel(params)
        o = order.Order.get_or_create_draft(s, channel=chan)
        o.add_line(s, itm.id, qty)
        await params.result_callback({"status": "added", "item": item, "qty": qty})

async def submit_order(params: FunctionCallParams):
    with SessionLocal() as s:
        chan = _safe_channel(params)
        o = order.Order.finalize_latest(s, channel=chan)
        await params.result_callback({
            "status": "submitted",
            "order_id": o.id,
            "total": str(o.total),      # keep exact value
        })

# ── Tools schema registered with Gemini service ────────────────────────
TOOLS = ToolsSchema(standard_tools=[list_menu, add_item, submit_order])

system_prompt = """
You are Sunrise Café’s AI assistant.
You must always respond in English, regardless of the language the user uses.
Only communicate via FUNCTION CALLS:
• list_menu()                     → when the user asks about menu/options.
• add_item(item:str, qty:int=1)    → when the user orders something.
• submit_order()                   → when the user says they are done or checking out.

NEVER reply with free text unless confirming totals right after submit_order().
"""

