import json
import shutil
import tomllib
from pathlib import Path
from typing import Iterable


def copy_file(source_path: Path | str, destination_path: Path | str):
    destination_path = Path(destination_path)
    if destination_path.exists():
        return
    shutil.copy2(str(source_path), str(destination_path))


def load_toml(filepath: Path | str) -> dict:
    with open(filepath, "rb") as file:
        return tomllib.load(file)


def load_lines(filepath: Path | str) -> list[str]:
    with open(filepath, "r") as file:
        return [line.strip() for line in file.readlines() if line != "\n"]


def write_lines(filepath: Path | str, lines: Iterable[str]):
    with open(filepath, "w") as file:
        file.write("\n".join(lines))


def load_json(filepath: Path | str) -> dict:
    with open(filepath, "r") as file:
        return json.load(file)


def write_json(filepath: Path | str, data):
    with open(filepath, "w") as file:
        json.dump(data, file, indent=4)


def to_json(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)
