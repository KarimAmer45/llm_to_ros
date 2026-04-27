"""Safety & validation utilities.

This is the layer you should talk about in the interview:
- tool allowlist + schema validation
- bounds checks (workspace constraints)
- speed limits
- execution timeouts and retries handled in the agent loop
"""

from typing import Any, Dict, List, Tuple
from .schemas import TOOL_SCHEMAS, ALLOWED_TOOLS

def _type_ok(expected: str, v: Any) -> bool:
    if expected == "number":
        return isinstance(v, (int, float))
    if expected == "integer":
        return isinstance(v, int)
    if expected == "string":
        return isinstance(v, str)
    if expected == "object":
        return isinstance(v, dict)
    return False

def validate_tool_call(tool: str, args: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if tool not in ALLOWED_TOOLS:
        return False, [f"Tool '{tool}' is not allowed."]
    schema = TOOL_SCHEMAS[tool]
    if not isinstance(args, dict):
        return False, ["Args must be an object/dict."]

    required = schema.get("required", [])
    props = schema.get("properties", {})
    additional = schema.get("additionalProperties", True)

    for r in required:
        if r not in args:
            errors.append(f"Missing required arg '{r}'.")

    for k, v in args.items():
        if k not in props:
            if not additional:
                errors.append(f"Unexpected arg '{k}'.")
            continue
        expected_type = props[k].get("type")
        if expected_type and not _type_ok(expected_type, v):
            errors.append(f"Arg '{k}' must be {expected_type}, got {type(v).__name__}.")

    return (len(errors) == 0), errors

def clamp_go_to_args(args: Dict[str, Any], bounds_min: float, bounds_max: float) -> Dict[str, Any]:
    # Enforce workspace bounds for the active simulator/backend.
    a = dict(args)
    a["x"] = float(min(max(a["x"], bounds_min), bounds_max))
    a["y"] = float(min(max(a["y"], bounds_min), bounds_max))
    if "theta" in a and a["theta"] is not None:
        a["theta"] = float(a["theta"])
    return a
