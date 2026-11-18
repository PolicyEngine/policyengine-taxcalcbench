"""Verify and load Column Tax's synthetic 2024 cases at a fixed revision."""

import hashlib
import json
from pathlib import Path

REVISION = "fdfe0db992ae9033f5b8b942633181a3596da64c"
MANIFEST = Path(__file__).with_name("ty24_manifest.json")


def verified_cases(directory: Path) -> list[Path]:
    """Require the exact case roster and bytes before evaluating any case."""
    expected = json.loads(MANIFEST.read_text())
    actual = {path.name for path in directory.iterdir() if path.is_dir()}
    if actual != expected.keys():
        raise ValueError(f"Case roster differs: {sorted(actual ^ expected.keys())}")
    for case, files in expected.items():
        for name, checksum in files.items():
            path = directory / case / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                raise ValueError(f"Fixture checksum differs: {case}/{name}")
    return [directory / case for case in sorted(expected)]
