"""Vérifie ou actualise l'année du copyright des contributeurs."""

import argparse
import re
from datetime import date
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--fix", action="store_true")
args = parser.parse_args()
license_path = Path(__file__).resolve().parents[1] / "LICENSE"
text = license_path.read_text(encoding="utf-8")
year = date.today().year
years = "2026" if year == 2026 else f"2026-{year}"
expected = f"Copyright (c) {years} KhiopsLab contributors."
updated, count = re.subn(
    r"Copyright \(c\) 2026(?:-\d{4})? KhiopsLab contributors\.",
    expected,
    text,
)
if count != 1:
    raise SystemExit("Expected one KhiopsLab copyright notice in LICENSE.")
if text != updated:
    if not args.fix:
        raise SystemExit("Run: uv run python scripts/check-copyright.py --fix")
    license_path.write_text(updated, encoding="utf-8")
