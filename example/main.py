"""A deliberately fallible LangGraph + OpenRouter playground instrumented with Voker."""

from __future__ import annotations

import os
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any, TypedDict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent
from openai import AsyncOpenAI as BaseAsyncOpenAI
from openai import OpenAI as BaseOpenAI
from pydantic import BaseModel, Field
from voker import VokerClient
from voker.ai.provider_openai import AsyncOpenAI as VokerAsyncOpenAI
from voker.ai.provider_openai import OpenAI as VokerOpenAI

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
AGENT_NAME = os.getenv("VOKER_AGENT_NAME", "imperfect-operations-agent")
app = FastAPI(title=os.getenv("APP_NAME", "Voker Agent API"), version="0.2.0")


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


class AgentResponse(BaseModel):
    session_id: str
    answer: str
    tool_messages: list[str]


class MultiAgentResponse(AgentResponse):
    research: str


class VokerTraceCallback(BaseCallbackHandler):
    """Send LangChain lifecycle events through Voker's generic event SDK."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.client = VokerClient() if os.getenv("VOKER_API_KEY") else None

    def _emit(self, event_name: str, properties: dict[str, Any]) -> None:
        if not self.client:
            return
        # Voker's API requires `properties.output`, when present, to be an object.
        # LangChain exposes several outputs as strings or message instances.
        if "output" in properties and not isinstance(properties["output"], dict):
            properties = {**properties, "output": {"value": str(properties["output"])}}
        try:
            self.client.events.create(agent=AGENT_NAME, session=self.session_id, event_name=event_name, properties=properties)
        except Exception:
            pass  # Observability must never make the demo agent unavailable.

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **_: Any) -> None:
        self._emit("llm", {"api": "openai-chat-completions", "inputs": {"model": serialized.get("kwargs", {}).get("model_name"), "prompts": prompts}, "phase": "start"})

    def on_llm_end(self, response: Any, **_: Any) -> None:
        self._emit("llm", {"api": "openai-chat-completions", "output": response.dict() if hasattr(response, "dict") else str(response)})

    def on_llm_error(self, error: BaseException, **_: Any) -> None:
        self._emit("error", {"stage": "llm", "error_type": type(error).__name__, "message": str(error)})

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **_: Any) -> None:
        self._emit("tool", {"tool": serialized.get("name"), "input": input_str, "phase": "start"})

    def on_tool_end(self, output: Any, **_: Any) -> None:
        status = getattr(output, "status", None)
        self._emit("error" if status == "error" else "tool", {"stage": "tool", "status": status or "success", "output": str(output)})

    def on_tool_error(self, error: BaseException, **_: Any) -> None:
        self._emit("error", {"stage": "tool", "error_type": type(error).__name__, "message": str(error)})


@tool
def calculate_shipping(weight_kg: float, destination: str, express: bool = False) -> str:
    """Estimate shipping. Use this before promising a delivery total."""
    if weight_kg <= 0:
        raise ValueError("weight_kg must be positive")
    multiplier = 2.2 if express else 1.0
    return f"Estimated {destination} shipping: ${(4.99 + weight_kg * 1.75) * multiplier:.2f}."


@tool
def inventory_lookup(sku: str) -> str:
    """Look up a demo SKU. OUTAGE-500 intentionally fails for tracing practice."""
    if sku.upper() == "OUTAGE-500":
        raise RuntimeError("inventory provider returned HTTP 503: planned demo outage")
    inventory = {"WIDGET-1": 12, "WIDGET-2": 0, "BUNDLE-9": 4}
    return f"{sku.upper()}: {inventory.get(sku.upper(), 0)} units available."


@tool
def risky_discount(customer_tier: str, percent: int) -> str:
    """Validate a discount. Values above 25% intentionally produce a tool error."""
    if percent > 25:
        raise PermissionError("Discount policy blocks discounts greater than 25%")
    return f"Approved {percent}% discount for {customer_tier} customer."


async def load_mcp_tools() -> list[Any]:
    client = MultiServerMCPClient(
        {"demo_operations": {"transport": "stdio", "command": sys.executable, "args": [str(APP_DIR / "demo_mcp_server.py")]}},
        tool_name_prefix=True,
        handle_tool_errors=True,
    )
    return await client.get_tools()


class _ParsedResponse:
    """Small adapter for LangChain's OpenAI raw-response expectation."""

    def __init__(self, response: Any) -> None:
        self.response = response

    def parse(self) -> Any:
        return self.response


class _VokerSyncCompletions:
    def __init__(self, client: VokerOpenAI, session_id: str) -> None:
        self.client = client
        self.session_id = session_id
        self.with_raw_response = self

    def create(self, **kwargs: Any) -> _ParsedResponse:
        response = self.client.chat.completions.create(
            voker_agent=AGENT_NAME, voker_session=self.session_id, **kwargs
        )
        return _ParsedResponse(response)


class _VokerAsyncCompletions:
    def __init__(self, client: VokerAsyncOpenAI, session_id: str) -> None:
        self.client = client
        self.session_id = session_id
        self.with_raw_response = self

    async def create(self, **kwargs: Any) -> _ParsedResponse:
        response = await self.client.chat.completions.create(
            voker_agent=AGENT_NAME, voker_session=self.session_id, **kwargs
        )
        return _ParsedResponse(response)


def create_model(session_id: str) -> tuple[ChatOpenAI, VokerClient]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not configured")
    headers = {"HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:8000"), "X-Title": "Voker Imperfect Agent Demo"}
    voker_client = VokerClient()
    sync_base = BaseOpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1", default_headers=headers)
    async_base = BaseAsyncOpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1", default_headers=headers)
    sync_client = VokerOpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1", base_openai_client=sync_base, voker_client=voker_client)
    async_client = VokerAsyncOpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1", base_openai_client=async_base, voker_client=voker_client)
    model = ChatOpenAI(
        model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini"), api_key=api_key,
        base_url="https://openrouter.ai/api/v1", default_headers=headers,
        temperature=0.7, max_retries=0, max_tokens=1200,
        client=_VokerSyncCompletions(sync_client, session_id),
        async_client=_VokerAsyncCompletions(async_client, session_id),
    )
    return model, voker_client


SYSTEM_PROMPT = """You are a deliberately imperfect operations assistant used to test observability.
Use tools whenever they can answer a request; use MCP tools for policy, incident, and customer-note questions.
Do not invent tool results. If a tool returns an error, explain it and try an appropriate alternative once. Never claim a failed action succeeded."""


class MultiAgentState(TypedDict):
    message: str
    research: str
    tool_messages: list[str]
    answer: str


@app.post("/agent/run", response_model=AgentResponse, tags=["agent"])
async def run_agent(request: AgentRequest) -> AgentResponse:
    # Voker validates session identifiers as UUIDs.
    if request.session_id:
        try:
            session_id = str(uuid.UUID(request.session_id))
        except ValueError as error:
            raise HTTPException(status_code=422, detail="session_id must be a UUID") from error
    else:
        session_id = str(uuid.uuid4())
    try:
        tools = [calculate_shipping, inventory_lookup, risky_discount, *(await load_mcp_tools())]
        model, _voker_client = create_model(session_id)
        graph = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)
        result = await graph.ainvoke({"messages": [HumanMessage(content=request.message)]}, config={"recursion_limit": 12})
        messages: list[BaseMessage] = result["messages"]
        return AgentResponse(session_id=session_id, answer=str(messages[-1].content), tool_messages=[str(message.content) for message in messages if message.type == "tool"])
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Agent run failed: {type(error).__name__}: {error}") from error


@app.post("/agent/multi-run", response_model=MultiAgentResponse, tags=["agent"])
async def run_multi_agent(request: AgentRequest) -> MultiAgentResponse:
    """Two LangGraph agents: tool-using operations researcher, then reviewer."""
    if request.session_id:
        try:
            session_id = str(uuid.UUID(request.session_id))
        except ValueError as error:
            raise HTTPException(status_code=422, detail="session_id must be a UUID") from error
    else:
        session_id = str(uuid.uuid4())
    try:
        tools = [calculate_shipping, inventory_lookup, risky_discount, *(await load_mcp_tools())]
        operations_model, _operations_voker = create_model(session_id)
        reviewer_model, _reviewer_voker = create_model(session_id)
        operations_agent = create_react_agent(
            operations_model,
            tools,
            prompt="You are the operations-research agent. Use tools and MCP to collect concrete evidence. Return concise findings, including any errors.",
        )

        async def research_node(state: MultiAgentState) -> dict[str, Any]:
            result = await operations_agent.ainvoke({"messages": [HumanMessage(content=state["message"])]})
            messages: list[BaseMessage] = result["messages"]
            return {
                "research": str(messages[-1].content),
                "tool_messages": [str(message.content) for message in messages if message.type == "tool"],
            }

        async def reviewer_node(state: MultiAgentState) -> dict[str, str]:
            review = await reviewer_model.ainvoke([
                HumanMessage(content=(
                    "You are the reviewer agent. Give the user a concise final answer based only on the operations-agent findings below. "
                    f"Original request: {state['message']}\nFindings: {state['research']}"
                ))
            ])
            return {"answer": str(review.content)}

        workflow = StateGraph(MultiAgentState)
        workflow.add_node("operations_researcher", research_node)
        workflow.add_node("reviewer", reviewer_node)
        workflow.add_edge(START, "operations_researcher")
        workflow.add_edge("operations_researcher", "reviewer")
        workflow.add_edge("reviewer", END)
        state = await workflow.compile().ainvoke({"message": request.message, "research": "", "tool_messages": [], "answer": ""})
        return MultiAgentResponse(session_id=session_id, answer=state["answer"], research=state["research"], tool_messages=state["tool_messages"])
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Multi-agent run failed: {type(error).__name__}: {error}") from error


@app.get("/", tags=["health"])
def root() -> dict[str, str]:
    return {"message": "Voker imperfect LangGraph agent is running"}


@app.get("/health", tags=["health"])
def health() -> dict[str, Any]:
    return {"status": "ok", "environment": os.getenv("APP_ENV", "development"), "voker_configured": bool(os.getenv("VOKER_API_KEY")), "openrouter_configured": bool(os.getenv("OPENROUTER_API_KEY"))}
