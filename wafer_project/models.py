"""Shared, validated task descriptions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LotTask:
    lot_id: str
    destination: str
    alternatives: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: object, stations: dict[str, bool]) -> "LotTask":
        if not isinstance(data, dict):
            raise ValueError("Each task must be a JSON object")
        if set(data) - {"lot_id", "destination", "alternatives"}:
            raise ValueError("Unknown task fields")
        lot_id = data.get("lot_id")
        destination = data.get("destination")
        if not isinstance(lot_id, str) or not lot_id.strip():
            raise ValueError("lot_id must be a nonempty string")
        if not isinstance(destination, str) or destination not in stations:
            raise ValueError("destination must be a configured station")
        alternatives = data.get("alternatives", [])
        if not isinstance(alternatives, list) or any(
            not isinstance(name, str) or name not in stations for name in alternatives
        ):
            raise ValueError("alternatives must be a list of configured stations")
        return cls(lot_id.strip(), destination, tuple(dict.fromkeys(alternatives)))
