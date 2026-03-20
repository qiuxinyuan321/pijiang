from __future__ import annotations

STANDARD11_PROFILE = "standard11"
LEGACY_STANDARD10_PROFILE = "standard10-legacy"
STANDARD11_QUORUM_PROFILE = "standard11-quorum6"
SEAT_REGISTRY_VERSION = "2026-03-20-standard11"

CANONICAL_STANDARD11_SEAT_ORDER = [
    "controller",
    "planning",
    "search-1",
    "search-2",
    "opencode-kimi",
    "opencode-glm5",
    "opencode-minimax",
    "opencode-qwen",
    "chaos",
    "skeptic",
    "fusion",
]

LEGACY_STANDARD10_SEAT_ORDER = [
    "controller",
    "planning",
    "search-1",
    "search-2",
    "opencode-kimi",
    "opencode-glm5",
    "opencode-minimax",
    "chaos",
    "skeptic",
    "fusion",
]

OPENCODE_MARSHAL_SEAT_IDS = [
    "opencode-kimi",
    "opencode-glm5",
    "opencode-minimax",
    "opencode-qwen",
]

LEGACY_PROFILE_ALIASES = {
    "standard10": LEGACY_STANDARD10_PROFILE,
    "default10": LEGACY_STANDARD10_PROFILE,
}

LEGACY_SEAT_ALIASES = {
    "marshal-1": "opencode-kimi",
    "marshal-2": "opencode-glm5",
    "marshal-3": "opencode-minimax",
}


def canonical_seat_type(seat_id: str) -> str:
    if seat_id == "controller":
        return "controller"
    if seat_id == "planning":
        return "planning"
    if seat_id in {"search-1", "search-2"}:
        return "search"
    if seat_id in OPENCODE_MARSHAL_SEAT_IDS:
        return "marshal"
    if seat_id == "chaos":
        return "chaos"
    if seat_id == "skeptic":
        return "skeptic"
    if seat_id == "fusion":
        return "fusion"
    return "marshal"


def canonical_output_filename(seat_id: str) -> str:
    mapping = {
        "controller": "10-controller.md",
        "planning": "11-planning.md",
        "search-1": "12-search-1.md",
        "search-2": "13-search-2.md",
        "opencode-kimi": "14-opencode-kimi.md",
        "opencode-glm5": "15-opencode-glm5.md",
        "opencode-minimax": "16-opencode-minimax.md",
        "opencode-qwen": "17-opencode-qwen.md",
        "chaos": "18-chaos.md",
        "skeptic": "19-skeptic.md",
        "fusion": "20-fusion.md",
    }
    return mapping.get(seat_id, f"{seat_id}.md")
