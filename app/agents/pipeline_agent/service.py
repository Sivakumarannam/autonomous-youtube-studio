"""Pipeline Agent Service — assembled from part files at import time."""
from pathlib import Path
_dir = Path(__file__).parent
_src = (_dir / "_service_part1.txt").read_text(encoding="utf-8")
_src += (_dir / "_service_part2.txt").read_text(encoding="utf-8")
exec(compile(_src, str(Path(__file__).resolve()), "exec"), globals())
