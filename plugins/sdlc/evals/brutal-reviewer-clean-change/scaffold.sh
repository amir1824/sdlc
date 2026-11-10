#!/usr/bin/env bash
set -euo pipefail
git init -q && git config user.email e@example.com && git config user.name eval
mkdir -p src
cat > src/age.ts <<'TS'
export const isAdult = (age: number): boolean => age >= 18;

export const label = (age: number): string => (isAdult(age) ? 'adult' : 'minor');
TS
git add -A && git commit -qm base
cat > src/age.ts <<'TS'
const ADULT_AGE = 18;

export const isAdult = (age: number): boolean => age >= ADULT_AGE;

export const label = (age: number): string => (isAdult(age) ? 'adult' : 'minor');
TS
