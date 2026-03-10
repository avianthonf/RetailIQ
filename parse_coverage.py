import json

with open("coverage.json", "r") as f:
    data = json.load(f)

files = []
for filename, info in data["files"].items():
    pct = info["summary"]["percent_covered"]
    if pct < 100.0:
        files.append((filename, pct, info["missing_lines"]))

files.sort(key=lambda x: x[1])

with open("coverage_summary.txt", "w") as f:
    for filename, pct, missing in files:
        f.write(f"{filename}: {pct:.1f}% ({len(missing)} missing lines)\n")
