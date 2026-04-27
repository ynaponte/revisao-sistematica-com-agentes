import re
import logging
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END, START
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.runtime import Runtime

from .llm import get_llm
from .models import OutputState, ScreeningState, ScreeningContext
from .prompts import SCREENING_SYSTEM_PROMPT


logger = logging.getLogger(__name__)


async def agent_node(state: ScreeningState, runtime: Runtime[ScreeningContext]) -> ScreeningState:
    context = runtime.context
    
    llm = get_llm(context.get("provider"))
    agent = create_agent(
        model=llm,
        system_prompt=SCREENING_SYSTEM_PROMPT
    )
    response = await agent.ainvoke({"messages": state.get("messages")})
    logger.info("Agente terminou a execução")
    return response


def parse_regex_output(state: ScreeningState) -> OutputState:
    last_msg = state["messages"][-1]
    response_text = last_msg.content if not isinstance(last_msg, dict) else last_msg.get("content", "")
    
    tokens = 0
    if isinstance(last_msg, dict):
        usage = last_msg.get("usage_metadata") or {}
        tokens = usage.get("total_tokens", 0)
    else:
        usage = getattr(last_msg, "usage_metadata", None) or {}
        if isinstance(usage, dict):
            tokens = usage.get("total_tokens", 0)
        elif hasattr(usage, "total_tokens"):
            tokens = getattr(usage, "total_tokens", 0)
    
    decision_match = re.search(r"DECISION:\s*(ACCEPTED|REJECTED)", response_text, re.IGNORECASE)
    discr_match = re.search(r"DISCRIMINANTS[^:]*:\s*(.*)", response_text, re.IGNORECASE)
    just_match = re.search(r"JUSTIFICATION[^:]*:\s*(.*)", response_text, re.IGNORECASE | re.DOTALL)

    decision = decision_match.group(1).upper() if decision_match else "REJECTED"
    
    if discr_match and "NONE" not in discr_match.group(1).upper():
        discriminants = [d.strip() for d in discr_match.group(1).split(",")]
    else:
        discriminants = []

    if just_match:
        justification = just_match.group(1).strip()
    elif not decision_match:
        justification = f"Erro no Parse. Saída original: {response_text}"
    else:
        justification = "Justificativa não fornecida pelo agente."

    return {
        "decision": decision,
        "rejection_reasons": discriminants,
        "justification": justification,
        "tokens": tokens
    }

def build_graph() -> CompiledStateGraph[ScreeningState, ScreeningContext, ScreeningState, OutputState]:
    """
    Builds the LangGraph application using standard architecture with
    built-in agent functions, a checkpointer, and a context dictionary.
    """
    builder = StateGraph(
        state_schema=ScreeningState,
        context_schema=ScreeningContext,
        input_schema=ScreeningState,
        output_schema=OutputState
    )
    builder.add_node("agent", agent_node)
    builder.add_node("parser", parse_regex_output)

    builder.add_edge(START, "agent")
    builder.add_edge("agent", "parser")
    builder.add_edge("parser", END)
    
    return builder.compile(checkpointer=MemorySaver())
