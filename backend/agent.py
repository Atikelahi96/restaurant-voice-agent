import os, asyncio, logging
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import StructuredTool
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from backend.utils import llm_tools

load_dotenv(dotenv_path="backend/.env")
log = logging.getLogger("agent")

# ── helper to sync-wrap async café tools ────────────────────────────────────
def _wrap(async_fn):
    def runner(**kw):
        return asyncio.run(async_fn(params=None, **kw))
    return runner

tools = [
    StructuredTool.from_function(_wrap(llm_tools.list_menu),
                                 name="list_menu",
                                 description="Return full café menu."),
    StructuredTool.from_function(_wrap(llm_tools.add_item),
                                 name="add_item",
                                 description="Add an item to current order."),
    StructuredTool.from_function(_wrap(llm_tools.submit_order),
                                 name="submit_order",
                                 description="Submit order and get total."),
]

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",
    temperature=0.4,
    convert_system_message_to_instructions=True,
    google_api_key=os.getenv("GOOGLE_API_KEY"),   # explicit key avoids ADC lookup
).bind_tools(tools)

SYSTEM = (
    "You are Sunrise Café’s AI assistant. "
    "Use the three tools provided; do NOT free-form chat unless confirming totals."
)

# ── prompt built with ChatPromptTemplate (no create_prompt) ─────────────────
prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    MessagesPlaceholder("chat_history", optional=True),
    ("user", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

memory = ConversationBufferMemory(
    return_messages=True,
    memory_key="chat_history",
)

core_agent = create_openai_tools_agent(llm, tools, prompt)
agent      = AgentExecutor(agent=core_agent, tools=tools,
                           memory=memory, verbose=False)

def chat(text: str) -> str:
    """Synchronous entry for FastAPI `/chat` route."""
    return agent.invoke({"input": text})["output"]
