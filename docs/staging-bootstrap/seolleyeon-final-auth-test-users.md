# seolleyeon-final Auth test users

Generated: 2026-05-19 KST

## SG-6 result

Status: `SCRIPT_READY_DRY_RUN_ONLY`

Script:

- `scripts/create_staging_auth_test_users.py`

Default mode:

- dry-run
- target project must be `seolleyeon-final`
- does not import production users
- does not print passwords
- stores generated passwords only under `.local_secrets/staging_test_users.json` in apply mode
- `.local_secrets/` is gitignored

## Planned users

Default emails:

- userA: `staging-user-a@seolleyeon-final.local`
- userB: `staging-user-b@seolleyeon-final.local`
- userC: `staging-user-c@seolleyeon-final.local`

Override with environment variables:

- `TEST_USER_A_EMAIL`
- `TEST_USER_B_EMAIL`
- `TEST_USER_C_EMAIL`
- `TEST_USER_A_PASSWORD`
- `TEST_USER_B_PASSWORD`
- `TEST_USER_C_PASSWORD`

## Commands

Dry-run:

```sh
.venv/Scripts/python.exe scripts/create_staging_auth_test_users.py \
  --target_project seolleyeon-final \
  --dry_run \
  --report_json out/staging_auth_test_users_dry_run.json
```

Apply after installing `firebase_admin` and confirming ADC:

```sh
.venv/Scripts/python.exe scripts/create_staging_auth_test_users.py \
  --target_project seolleyeon-final \
  --apply \
  --create_firestore_fixtures \
  --report_json out/staging_auth_test_users_apply.json
```

## Current blocker

`firebase_admin` is not installed in the active `.venv`, so apply mode is not ready until dependency installation is approved.

## SG-6 handoff

```json
{
  "subagent": "SG-6",
  "status": "partial",
  "target_project": "seolleyeon-final",
  "auth_users": [
    "planned:userA",
    "planned:userB",
    "planned:userC"
  ],
  "blocked_by_env": [
    "firebase_admin is not installed for apply mode"
  ],
  "required_followups": [
    "Install firebase_admin in the chosen Python environment.",
    "Run dry-run and review report.",
    "Run --apply only in seolleyeon-final."
  ]
}
```
