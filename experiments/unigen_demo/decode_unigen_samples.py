from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 7:
    raise SystemExit(
        "usage: python3 decode_unigen_samples.py "
        "<sample-name> <width> <height> <pattern-width> "
        "<unigen-samples.txt> <output-dir>"
    )

name = sys.argv[1]
width = int(sys.argv[2])
height = int(sys.argv[3])
pattern_width = int(sys.argv[4])

samples_path = Path(sys.argv[5])
out_dir = Path(sys.argv[6])

out_dir.mkdir(parents=True, exist_ok=True)

samples = [
    line.strip()
    for line in samples_path.read_text().splitlines()
    if line.strip()
]

if not samples:
    raise SystemExit(f"No samples found in {samples_path}")

for i, assignment in enumerate(samples, start=1):
    sol = out_dir / f"sample_{i:02d}.sol"
    png = out_dir / f"sample_{i:02d}.png"
    log = out_dir / f"sample_{i:02d}.log"

    # Convert one UniGen sample into MiniSat format
    sol.write_text("SAT\n" + assignment + "\n")

    result = subprocess.run(
        [
            "python3",
            "decode_minisat_solution.py",
            name,
            str(width),
            str(height),
            str(pattern_width),
            str(sol),
            str(png),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    log.write_text(result.stdout)

    if result.returncode == 0:
        print(f"OK: {png.name}")
    else:
        print(f"FAILED: {png.name}")
        print(result.stdout)
