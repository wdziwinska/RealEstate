from __future__ import annotations

import os
from typing import List

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from app.models import GraphState


load_dotenv()


class Researcher:
    """
    Agent responsible for discovering real-estate offers
    using Web Search MCP tools.
    """

    name = "Researcher"

    def __init__(
        self,
        tools: List[BaseTool],
        llm: BaseChatModel | None = None,
    ):
        self.tools = tools

        self.llm = llm or ChatOpenAI(
            model=os.getenv(
                "LOCAL_LLM_MODEL",
                "qwen3:30b",
            ),
            base_url=os.getenv(
                "LOCAL_LLM_BASE_URL",
            ),
            api_key=os.getenv(
                "LOCAL_LLM_API_KEY",
                "dummy",
            ),
            temperature=0,
            max_retries=1,
        )

        self.agent = self.llm.bind_tools(self.tools)

    def _build_query_from_criteria(self, criteria) -> str:
        """
        Build a natural-language search query from UserCriteria
        when raw_query was not provided.
        """

        # Pydantic v2
        if hasattr(criteria, "model_dump"):
            data = criteria.model_dump()
        else:
            data = vars(criteria)

        # raw_query is handled separately
        data.pop("raw_query", None)

        parts: list[str] = []

        for key, value in data.items():
            if value is None:
                continue

            if value == "":
                continue

            if isinstance(value, bool):
                if not value:
                    continue

                parts.append(
                    f"{key.replace('_', ' ')}: yes"
                )
                continue

            if isinstance(value, (list, tuple, set)):
                if not value:
                    continue

                value = ", ".join(str(item) for item in value)

            parts.append(
                f"{key.replace('_', ' ')}: {value}"
            )

        if not parts:
            return (
                "Find residential real estate offers in Warsaw "
                "and within 30 km of Warsaw."
            )

        return (
            "Find residential real estate offers in Warsaw "
            "and within 30 km of Warsaw matching these criteria: "
            + "; ".join(parts)
        )

    def _get_search_query(self, state: GraphState) -> str:
        """
        Prefer original user query, but fall back to structured criteria.
        """

        raw_query = getattr(
            state.criteria,
            "raw_query",
            None,
        )

        if raw_query and raw_query.strip():
            return raw_query.strip()

        return self._build_query_from_criteria(
            state.criteria
        )

    async def run(self, state: GraphState) -> GraphState:
        search_query = self._get_search_query(state)

        print(
            "Researcher search query:",
            repr(search_query),
        )

        messages = [
            SystemMessage(
                content=(
                    "You are the Researcher agent in a real-estate analysis system.\n\n"
                    "Your task is to DISCOVER real property listings.\n"
                    "Do not attempt to validate rail distance, travel time, "
                    "legal status or environmental conditions during discovery. "
                    "Those checks are performed by other agents.\n\n"

                    "Use get-web-search-summaries to find listings matching only "
                    "basic property criteria such as:\n"
                    "- property type\n"
                    "- maximum price\n"
                    "- general location\n"
                    "- minimum area if specified\n\n"

                    "For Warsaw + surrounding area, search broadly. "
                    "Do not put distance-to-PKP requirements into the search query.\n\n"

                    "Prefer search queries resembling normal Google searches, e.g.:\n"
                    "'dom na sprzedaż Warszawa do 1500000'\n"
                    "'dom na sprzedaż Piaseczno do 1500000'\n"
                    "'dom na sprzedaż Legionowo do 1500000'\n\n"

                    "You MUST use web-search tools."
                )
            ),
            HumanMessage(
                content=(
                    "Find property offers matching the following "
                    "criteria:\n\n"
                    f"{search_query}"
                )
            ),
        ]

        response = self.agent.invoke(messages)

        print(
            "Researcher agent response:",
            response,
        )

        print(
            "Researcher tool calls:",
            response.tool_calls,
        )

        if response.tool_calls:
            tool_map = {
                tool.name: tool
                for tool in self.tools
            }

            for call in response.tool_calls:
                tool_name = call["name"]
                tool_args = call["args"]

                tool = tool_map.get(tool_name)

                if tool is None:
                    print(
                        f"Unknown tool requested by LLM: {tool_name}"
                    )
                    continue

                print(
                    f"Executing MCP tool: {tool_name}"
                )
                print(
                    f"Tool arguments: {tool_args}"
                )

                result = await tool.ainvoke(tool_args)

                print(
                    "Tool result:",
                    result,
                )

        return state