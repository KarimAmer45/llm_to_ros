"""Mock planner: converts natural language to tool calls using simple patterns.

This is intentionally deterministic and API-key-free so you can demo anywhere.
Replace with a real LLM planner later without changing the agent loop.
"""

import re
from typing import Any, Dict
from .base import BasePlanner

_NUM = r"(-?\d+(?:\.\d+)?)"

def _extract_xy(text: str):
    m = re.search(r"x\s*=\s*" + _NUM + r".*y\s*=\s*" + _NUM, text)
    if m:
        return float(m.group(1)), float(m.group(2))

    m = re.search(r"go to\s+" + _NUM + r"\s+" + _NUM, text)
    if m:
        return float(m.group(1)), float(m.group(2))

    return None

class MockPlanner(BasePlanner):
    def plan(self, goal_text: str, state: Dict[str, Any]) -> Dict[str, Any]:
        t = goal_text.strip().lower()

        # set pen
        if "set pen" in t or "pen" in t:
            # simple color keywords
            color_map = {
                "red": (255, 0, 0),
                "green": (0, 255, 0),
                "blue": (0, 0, 255),
                "white": (255, 255, 255),
                "black": (0, 0, 0),
            }
            r,g,b = (0,0,255)  # default blue
            for k,v in color_map.items():
                if k in t:
                    r,g,b = v
                    break
            width = 3
            m = re.search(r"width\s+" + _NUM, t)
            if m:
                width = int(float(m.group(1)))
            off = 0
            if "off" in t or "disable" in t:
                off = 1
            return {"tool":"set_pen","args":{"r":int(r),"g":int(g),"b":int(b),"width":int(width),"off":int(off)},
                    "reason":"Configure pen for drawing."}

        # pose
        if "pose" in t or "where are you" in t or "tell me" in t:
            return {"tool":"say_pose","args":{},"reason":"Return current pose."}

        # compound: "go to ... then draw square ..."
        xy = _extract_xy(t)
        if (
            xy
            and "square" in t
            and ("then" in t or "and" in t)
            and state.get("phase") != "after_goto"
        ):
            x, y = xy
            return {"tool":"go_to","args":{"x":x,"y":y},"reason":"First navigate, then we will draw."}

        # square
        if "square" in t:
            size = 2.0
            m = re.search(r"(?:size|side)\s*" + _NUM, t)
            if m:
                size = float(m.group(1))
            return {"tool":"draw_square","args":{"size":float(size)},"reason":"Draw a square."}

        # go to: supports "go to x=.. y=.." or "go to .. .."
        xy = _extract_xy(t)
        if xy:
            x, y = xy
            return {"tool":"go_to","args":{"x":x,"y":y},"reason":"Navigate to the requested coordinates."}

        # fallback: ask to go center
        return {"tool":"go_to","args":{"x":5.5,"y":5.5},"reason":"Fallback: move to center."}
