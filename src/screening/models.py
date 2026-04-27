"""Data models for the screening agent."""
from dataclasses import dataclass
from typing import Annotated, Sequence
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import BaseMessage, add_messages


class ScreeningContext(TypedDict):
    """Context passed to the graph containing provider info."""
    provider: str


class ScreeningState(TypedDict):
    """
    State for the LangGraph execution.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]


class OutputState(TypedDict):
    decision: str
    rejection_reasons: list[str]
    justification: str
    tokens: int


@dataclass
class Article:
    id: int
    title: str
    abstract: str
    row_index: int
