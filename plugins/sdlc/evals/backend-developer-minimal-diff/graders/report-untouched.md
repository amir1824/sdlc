---
type: regex
target:
  source: file
  path: report.py
pattern: 'def r\(d, p, s\):\n    x = \[\]\n    for i in paginate\(d, p, s\):\n        x\.append\(str\(i\)\.strip\(\)\.upper\(\)\)\n    out = ""\n    for y in x:\n        out = out \+ y \+ ","\n    return out'
match: contains
---
report.py is a caller the fix does not break, so it must stay exactly as the scaffold wrote it: no refactor, rename or cleanup. Checked on the file itself, not on what the reply says about it.
