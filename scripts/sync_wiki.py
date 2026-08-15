#!/usr/bin/env python3
"""Copy only SearchCans-generated Wiki pages into a checked-out GitHub Wiki."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


MANIFEST = ".searchcans-generated-pages"


def page_names(directory: Path) -> set[str]:
    manifest = directory / MANIFEST
    if not manifest.is_file():
        raise ValueError(f"Missing generated-page manifest: {manifest}")
    names = {line.strip() for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()}
    if not names or any(Path(name).name != name or not name.endswith(".md") for name in names):
        raise ValueError("Generated-page manifest contains an invalid page name")
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    source, target = args.source.resolve(), args.target.resolve()
    current = page_names(source)
    previous_manifest = target / MANIFEST
    previous = page_names(target) if previous_manifest.is_file() else set()
    for name in previous - current:
        (target / name).unlink(missing_ok=True)
    for name in current:
        shutil.copyfile(source / name, target / name)
    (target / MANIFEST).write_text("\n".join(sorted(current)) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
