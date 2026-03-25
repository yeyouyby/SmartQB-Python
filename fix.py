with open("algorithms/simulated_annealing.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "random." in line and "import" not in line:
        if line.strip().startswith("#"):
            continue
        if "#" not in line:
            lines[i] = line.rstrip() + "  # nosec B311\n"

with open("algorithms/simulated_annealing.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
