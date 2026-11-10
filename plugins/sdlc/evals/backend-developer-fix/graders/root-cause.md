---
type: llm
weight: 1
---
A passing reply reports a fix in the shared `parse_age` (validate.py), not only a patch in the caller `build_profile`. A missing value (None) must be handled explicitly there: either by raising a contextual error that names the input, or by returning an explicit absence value (None) with the type hints updated and the choice stated. Both are acceptable. Unacceptable: a bare TypeError still escaping, a magic value such as -1 or 0, or swallowing errors silently. The reply names a test added for the missing-age case and quotes the test command with its pass output. It does not claim passing tests it did not show.
