"""Tool schemas (minimal JSON-schema-like dicts).

In interviews, emphasize:
- allowlisted tools
- strict args schema
- deterministic executors
"""

TOOL_SCHEMAS = {
    "go_to": {
        "type": "object",
        "required": ["x", "y"],
        "properties": {
            "x": {"type": "number"},
            "y": {"type": "number"},
            "theta": {"type": "number"},
        },
        "additionalProperties": False,
    },
    "draw_square": {
        "type": "object",
        "required": ["size"],
        "properties": {"size": {"type": "number"}},
        "additionalProperties": False,
    },
    "say_pose": {
        "type": "object",
        "required": [],
        "properties": {},
        "additionalProperties": False,
    },
    "set_pen": {
        "type": "object",
        "required": ["r", "g", "b", "width", "off"],
        "properties": {
            "r": {"type": "integer"},
            "g": {"type": "integer"},
            "b": {"type": "integer"},
            "width": {"type": "integer"},
            "off": {"type": "integer"},
        },
        "additionalProperties": False,
    },
}

ALLOWED_TOOLS = set(TOOL_SCHEMAS.keys())
