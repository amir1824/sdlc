---
type: llm
focus: {source: file, path: REPORT.md}
---
The report has a clearly marked part about behaviour changes: it says there are none, or lists each change with what changed and where.
In this codebase two places add VAT at 17% and round differently: the cart rounds the tax to the nearest cent (`Math.round`), the invoice total rounds the gross DOWN (`Math.floor`), so they differ for many amounts. The tests only cover an amount where both agree.
The report passes only if it names this rounding difference and says it was kept as is, or lists a change of the invoice (or cart) rounding as an explicit behaviour change. It fails if it says "none" while the two were merged to one rounding, and it fails if it does not mention the difference at all.
