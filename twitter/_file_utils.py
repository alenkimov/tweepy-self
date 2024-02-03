import json
from pathlib import Path
from typing import Iterable


def load_lines(filepath: Path | str) -> list[str]:
    with open(filepath, "r") as file:
        return [line.strip() for line in file.readlines() if line != "\n"]


def write_lines(filepath: Path | str, lines: Iterable[str]):
    with open(filepath, "w") as file:
        file.write("\n".join(lines))


def to_json(obj) -> str:
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=True, default=str)
