import json
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

@dataclass
class LogEvent:
    t: float
    kind: str
    data: Dict[str, Any]

class JsonlLogger:
    def __init__(self, path: str):
        self.path = path

    def log(self, kind: str, **data: Any) -> None:
        ev = LogEvent(t=time.time(), kind=kind, data=data)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(ev), ensure_ascii=False) + "\n")
