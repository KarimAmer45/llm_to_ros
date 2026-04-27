from abc import ABC, abstractmethod
from typing import Any, Dict

class BasePlanner(ABC):
    """Planner returns a tool call dict: {tool:str, args:dict, reason:str}."""

    @abstractmethod
    def plan(self, goal_text: str, state: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
