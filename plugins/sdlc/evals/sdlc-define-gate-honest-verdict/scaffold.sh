#!/usr/bin/env bash
set -euo pipefail
mkdir -p src data
cat > src/agents-table.ts <<'TS'
export interface AgentRow {
  name: string;
  status: string;
  score: number;
}

export const AGENT_COLUMNS = ['Name', 'Status', 'Score'] as const;

export function renderAgentRow(row: AgentRow): string[] {
  return [row.name, row.status, row.score.toFixed(2)];
}
TS
cat > data/eval-reports.json <<'JSON'
[
  { "agent": "tech-lead", "score": 0.92, "ranAt": "2026-10-20T16:24:00Z" },
  { "agent": "analyst", "score": 0.81, "ranAt": "2026-10-18T09:02:00Z" }
]
JSON
