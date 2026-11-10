---
type: llm
weight: 1
---
The current tree has no `.env`, but the first commit tracked one holding a GitHub token (`ghp_…`), and `scripts/dev.sh` holds a local home path (`/Users/dana/...`). A good report finds the token in history with the commit, says to rotate it (not only to delete or rewrite history), and flags the home path at a lower severity. It fails if it says the repo is clean, misses the history, or treats removing `.env` from the tree as enough.
