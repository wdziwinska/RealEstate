from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.models import GraphState


def ensure_state(state: GraphState | Mapping[str, Any] | None = None) -> GraphState:
    """Normalize LangGraph dict state and direct Pydantic state into GraphState."""

    if state is None:
        return GraphState()
    if isinstance(state, GraphState):
        return state
    return GraphState.model_validate(dict(state))


def state_to_dict(state: GraphState) -> dict[str, Any]:
    return state.model_dump(mode="json")


def merge_state(state: GraphState | Mapping[str, Any], **updates: Any) -> dict[str, Any]:
    current = ensure_state(state)
    data = current.model_dump(mode="python")
    data.update(updates)
    return GraphState.model_validate(data).model_dump(mode="json")
