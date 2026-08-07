# 16 — CI/CD Release Gates

작성: 2026-07-31

## Workflow

`.github/workflows/ci.yml`

| Job | Gate |
|-----|------|
| functions | lint + test |
| rules | firestore emulator tests |
| flutter | format + analyze + test |
| python-recsys | avatar pytest + **recsys/tests required** |
| secret-scan | gitleaks |

## Still missing vs ideal

- Android/Web build jobs
- Storage rules tests job
- bandit / pip-audit / semgrep (optional; do not fake PASS)
- Manual approval separation for deploy (deploy not in CI — good)
