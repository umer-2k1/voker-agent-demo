"""Multi-agent LiveKit voice demo instrumented with Voker Voice.

Run with ``python example/voice_demo/agent.py dev``.  The LiveKit worker health
endpoint listens on ``VOICE_DEMO_PORT`` (8080 by default); calls are received
through the configured LiveKit room, not through this HTTP port.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    RunContext,
    cli,
    function_tool,
)
from livekit.plugins import deepgram, openai

from voker_voice.livekit import observe

load_dotenv(Path(__file__).with_name(".env"))


@dataclass
class DemoCallState:
    """Small, in-memory state that makes tool results coherent within one call."""

    customer_name: str | None = None
    appointment_id: str | None = None
    notes: list[str] = field(default_factory=list)
    voker_session: Any | None = None


def _record_intent(context: RunContext[DemoCallState], intent: str) -> None:
    """Attach the routed caller intent to the observed Voker session."""

    observed_session = context.userdata.voker_session
    if observed_session is not None:
        observed_session.emit(
            "intent.detected",
            status="ok",
            attributes={"intent": intent, "confidence": 0.99, "source": "route_tool"},
        )


def _record_outcome(context: RunContext[DemoCallState], outcome: str) -> None:
    observed_session = context.userdata.voker_session
    if observed_session is not None:
        observed_session.emit(
            "outcome.recorded",
            status="ok",
            attributes={"outcome": outcome, "source": "tool_result"},
        )


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required; add it to example/voice_demo/.env")
    return value


def _runtime_llm() -> openai.LLM:
    """Direct DeepSeek runtime LLM; independent from Voker's post-call evaluator."""

    return openai.LLM.with_deepseek(
        model=os.getenv("DEEPSEEK_RUNTIME_MODEL", "deepseek-flash"),
        api_key=_required("DEEPSEEK_API_KEY"),
        temperature=0.2,
    )


class SchedulingAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            id="scheduling-agent",
            instructions=(
                "You are the scheduling specialist. Help book, move, or cancel appointments. "
                "Use tools before promising availability. If a tool fails, state that clearly and "
                "offer the next sensible option."
            ),
        )

    @function_tool()
    async def check_slot(self, context: RunContext[DemoCallState], day: str, time: str) -> str:
        """Check whether an appointment slot is available."""
        normalized_time = time.lower().replace(" ", "")
        if day.lower() in {"monday", "friday"} and normalized_time.startswith(("9:", "09:")):
            raise RuntimeError("calendar provider timeout: planned observability demo failure")
        return f"{day} at {time} is available."

    @function_tool()
    async def reschedule(self, context: RunContext[DemoCallState], day: str, time: str) -> str:
        """Reschedule the caller's appointment after confirming the desired slot."""
        state = context.userdata
        state.appointment_id = state.appointment_id or "APT-1042"
        state.notes.append(f"Rescheduled to {day} {time}")
        _record_outcome(context, "resolved")
        return f"Appointment {state.appointment_id} was moved to {day} at {time}."


class BillingAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            id="billing-agent",
            instructions=(
                "You are the billing specialist. Handle charges, invoices, and refunds. "
                "Use the refund tool before committing to a refund; never claim a denied refund "
                "succeeded."
            ),
        )

    @function_tool()
    async def issue_refund(self, context: RunContext[DemoCallState], amount: float) -> str:
        """Issue a demonstration refund. Refunds above 25 intentionally fail."""
        if amount > 25:
            _record_outcome(context, "escalated")
            raise PermissionError("refund policy requires supervisor approval above $25")
        context.userdata.notes.append(f"Refunded ${amount:.2f}")
        _record_outcome(context, "resolved")
        return f"Refund of ${amount:.2f} was issued."


class SupportAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            id="support-agent",
            instructions=(
                "You are the technical support specialist. Diagnose access and product issues. "
                "Create a support ticket for outages or issues that cannot be resolved during "
                "the call."
            ),
        )

    @function_tool()
    async def create_ticket(self, context: RunContext[DemoCallState], summary: str) -> str:
        """Create a support ticket for an unresolved customer issue."""
        ticket_id = f"SUP-{len(context.userdata.notes) + 100}"
        context.userdata.notes.append(f"{ticket_id}: {summary}")
        _record_outcome(context, "escalated")
        return f"Created support ticket {ticket_id}."


class IntakeAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            id="intake-agent",
            instructions=(
                "You are the intake agent for an appointment service. Greet the caller and "
                "identify their need. Transfer appointment requests to scheduling, payment/refund "
                "questions to billing, and access/outage questions to technical support. Always "
                "explain a transfer."
            ),
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Greet the caller briefly and ask how you can help."
        )

    @function_tool()
    async def transfer_to_scheduling(self, context: RunContext[DemoCallState]) -> tuple[Agent, str]:
        """Transfer appointment booking, cancellation, or rescheduling requests."""
        _record_intent(context, "appointment_management")
        return SchedulingAgent(), "I am transferring you to our scheduling specialist."

    @function_tool()
    async def transfer_to_billing(self, context: RunContext[DemoCallState]) -> tuple[Agent, str]:
        """Transfer invoice, charge, and refund requests."""
        _record_intent(context, "billing_or_refund")
        return BillingAgent(), "I am transferring you to our billing specialist."

    @function_tool()
    async def transfer_to_support(self, context: RunContext[DemoCallState]) -> tuple[Agent, str]:
        """Transfer login, product, access, and service-outage requests."""
        _record_intent(context, "technical_support")
        return SupportAgent(), "I am transferring you to technical support."


server = AgentServer(
    host=os.getenv("VOICE_DEMO_HOST", "127.0.0.1"),
    port=int(os.getenv("VOICE_DEMO_PORT", "8080")),
)


@server.rtc_session(agent_name="voker-voice-demo")
async def entrypoint(context: JobContext) -> None:
    # Validate before joining so a missing credential produces a clear worker error.
    for variable in (
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "DEEPSEEK_API_KEY",
        "DEEPGRAM_API_KEY",
        "VOKER_API_KEY",
    ):
        _required(variable)

    await context.connect()
    session = AgentSession[DemoCallState](
        userdata=DemoCallState(),
        stt=deepgram.STT(model=os.getenv("DEEPGRAM_STT_MODEL", "nova-3"), language="en-US"),
        llm=_runtime_llm(),
        tts=deepgram.TTS(model=os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-asteria-en")),
        min_endpointing_delay=0.5,
        max_tool_steps=4,
    )

    # One call attaches Voker Voice. It exports asynchronously and never blocks the agent.
    observer = observe(
        session,
        context=context,
        agent="voker-voice-demo",
        version=os.getenv("VOICE_DEMO_VERSION", "demo-1"),
        metadata={"demo": "multi-agent-livekit", "runtime_llm": "deepseek"},
    )
    session.userdata.voker_session = observer.session
    await session.start(agent=IntakeAgent(), room=context.room)


if __name__ == "__main__":
    cli.run_app(server)
