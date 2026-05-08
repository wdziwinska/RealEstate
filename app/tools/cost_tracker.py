from __future__ import annotations

from collections import defaultdict
from threading import Lock
from app.models import CostUsage


class CostTracker:
    """Small token/cost ledger with rough default prices per 1M tokens."""

    DEFAULT_PRICING_USD_PER_1M = {
        "gpt-4o": {"prompt": 2.50, "completion": 10.00},
        "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
        "compatible": {"prompt": 1.00, "completion": 3.00},
    }

    def __init__(self, model_name: str = "gpt-4o") -> None:
        self.model_name = model_name
        self._usage: dict[str, CostUsage] = defaultdict(CostUsage)
        self._lock = Lock()

    def record(
        self,
        agent_name: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model_name: str | None = None,
    ) -> CostUsage:
        model = model_name or self.model_name
        pricing = self.DEFAULT_PRICING_USD_PER_1M.get(
            model, self.DEFAULT_PRICING_USD_PER_1M["compatible"]
        )
        cost = (
            prompt_tokens / 1_000_000 * pricing["prompt"]
            + completion_tokens / 1_000_000 * pricing["completion"]
        )
        with self._lock:
            usage = self._usage[agent_name]
            usage.prompt_tokens += prompt_tokens
            usage.completion_tokens += completion_tokens
            usage.cost_usd = round(usage.cost_usd + cost, 6)
            usage.calls += 1
            return usage.model_copy(deep=True)

    def usage_for(self, agent_name: str) -> CostUsage:
        with self._lock:
            return self._usage[agent_name].model_copy(deep=True)

    def snapshot(self) -> dict[str, CostUsage]:
        with self._lock:
            return {agent: usage.model_copy(deep=True) for agent, usage in self._usage.items()}

    def total(self) -> CostUsage:
        total = CostUsage()
        with self._lock:
            usages = [usage.model_copy(deep=True) for usage in self._usage.values()]
        for usage in usages:
            total.prompt_tokens += usage.prompt_tokens
            total.completion_tokens += usage.completion_tokens
            total.cost_usd = round(total.cost_usd + usage.cost_usd, 6)
            total.calls += usage.calls
        return total
