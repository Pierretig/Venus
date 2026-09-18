import re

path = r"C:\Users\pierr\.gemini\antigravity-ide\brain\9c484888-22a5-4761-99f0-eb1d5abc00a5\.system_generated\steps\456\content.md"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

paths = re.findall(r'"path":"([^"]+)"', text)
print("Paths found:", set(paths))

default_branch = re.findall(r'"defaultBranch":"([^"]+)"', text)
print("Default branch:", default_branch)
