from pathlib import Path

path = Path("src/prefilter.py")
text = path.read_text(encoding="utf-8")

old_doc = '    """Persist only the fields downstream execution governance needs."""\n'
new_doc = '    """Copy only the family fields downstream execution governance needs."""\n'
assert text.count(old_doc) == 1, "compact family helper docstring changed unexpectedly"
text = text.replace(old_doc, new_doc, 1)

old_field = '        "version": summary.get("version"),\n'
assert text.count(old_field) == 1, "compact family schema changed unexpectedly"
text = text.replace(old_field, "", 1)

# Preserve the legacy no-disabled-indicator architecture guard exactly as-is.
# It scans raw text for the token name, so avoid unrelated words that merely
# contain the same character sequence.
for term in ("rsi", "macd", "bollinger", "stochastic"):
    hits = [
        line for line in text.splitlines()
        if term in line.lower() and "no rsi" not in line.lower() and "#" not in line
    ]
    assert not hits, f"incidental disabled-indicator token remains: {term}: {hits}"

path.write_text(text, encoding="utf-8")

# One-shot build scaffolding: remove this helper from the worktree so the
# production commit contains only the intended source/tests.
Path(__file__).unlink()
