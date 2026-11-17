"""Build a self-contained Gemini CLI extension from this checkout."""

import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New extension directory")
    destination = parser.parse_args().destination.resolve()
    root = Path(__file__).resolve().parents[1]
    source = root / "integrations" / "gemini"
    if destination == source or source in destination.parents:
        parser.error("The destination must be outside the Gemini extension template.")

    shutil.copytree(source, destination)
    for name in ("host.py", "use_rtk.py"):
        shutil.copy2(root / "hooks" / name, destination / "hooks" / name)
    shutil.copy2(root / "LICENSE", destination / "LICENSE")
    print(destination)


if __name__ == "__main__":
    main()
