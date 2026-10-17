"""Pure scheduling logic: no network requests or robot actions."""

from dataclasses import dataclass, replace
from typing import Sequence

from .models import LotTask


@dataclass(frozen=True)
class Decision:
    task: LotTask | None
    reason: str


def choose_next(
    tasks: Sequence[LotTask], stations: dict[str, bool], policy: str = "fifo"
) -> Decision:
    if policy not in {"fifo", "available_first"}:
        raise ValueError("policy must be fifo or available_first")
    if not tasks:
        return Decision(None, "No tasks remain")
    candidates = tasks[:1] if policy == "fifo" else tasks
    for task in candidates:
        destinations = (task.destination,)
        if policy == "available_first":
            # Alternative stations must be explicitly eligible for this lot.
            destinations += task.alternatives
        for destination in destinations:
            if stations.get(destination, False):
                return Decision(
                    replace(task, destination=destination),
                    f"{policy}: {destination} is available",
                )
    return Decision(None, "Waiting: no eligible destination is available for this policy")
