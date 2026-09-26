## Task 3 Report

Status: implemented after audit of the existing Task 3 candidate changes.

Scope touched:
- `scripts/deploy_functions_guarded.sh`
- `tests/test_deploy_functions_guarded_contract.py`
- `.github/workflows/ci.yml`

Audit result:
- Existing candidate changes already added bootstrap ordering coverage, pinned Firebase CLI 15.30.2 CI preparation, Node 22.23.2 verification, local build before parameter discovery, parameter-aware guard before deploy, dry-run zero deploy assertion, and generated artifact verification/removal flow.
- One gap was found: `FUNCTIONS_DISCOVERY_TIMEOUT=30` was exported for the whole bootstrap wrapper process, so later Firebase CLI version/deploy invocations inherited it. The brief requires the timeout process-locally only.

Fix:
- Changed `scripts/deploy_functions_guarded.sh` so `FUNCTIONS_DISCOVERY_TIMEOUT=30` is scoped only to the pinned CLI parameter discovery command.
- Tightened `tests/test_deploy_functions_guarded_contract.py` so the wrapper regression proves:
  - local build precedes runtime parameter discovery;
  - discovery precedes parameter guard;
  - parameter guard and verified generated artifact removal precede deploy;
  - dry-run does not invoke deploy;
  - discovery receives timeout `30`;
  - CLI version and deploy invocations see `FUNCTIONS_DISCOVERY_TIMEOUT` unset.

Verification:
- RED: `python -m pytest -q tests/test_deploy_functions_guarded_contract.py -k "bootstrap_parameter_discovery_and_guard_precede_the_exact_deploy" --maxfail=1`
  - Failed before the wrapper fix because `export FUNCTIONS_DISCOVERY_TIMEOUT=30` was still present.
- GREEN focused wrapper tests: `python -m pytest -q tests/test_deploy_functions_guarded_contract.py --maxfail=1`
  - `17 passed, 4 skipped`
- P1.4 targeted Python contract suite: `python -m pytest -q tests/test_functions_bootstrap_env_guard.py tests/test_functions_bootstrap_generated_artifact.py tests/test_functions_codebase_parameter_contract.py tests/test_firebase_cli_15302_parameter_resolution.py tests/test_deploy_functions_guarded_contract.py --maxfail=1`
  - `58 passed, 4 skipped`
- Whitespace check: `git diff --check`
  - passed with no output

Not rerun:
- Full Functions lint/test suite was not rerun. The brief stated exact approved Git Bash/Node 22 evidence already exists and to run focused wrapper tests if needed; this change was limited to the wrapper and Python contract coverage.

Concerns:
- POSIX wrapper integration tests are intentionally skipped on this Windows shell and are expected to run on Ubuntu CI.
- No Firebase deploy, Firestore write, cloud mutation, secret output, PR update, force-push, rebase, or history rewrite was performed.

## Fix Round 1

Review finding addressed:
- The earlier report evidence was incomplete because it did not include fresh full Functions build/lint/test evidence after the wrapper change.
- Direct Firebase CLI 15.30.2 source inspection established that `FUNCTIONS_DISCOVERY_TIMEOUT` is read by actual deploy discovery, not by the local metadata helper. The wrapper now scopes `FUNCTIONS_DISCOVERY_TIMEOUT=30` only to the actual `firebase-tools@15.30.2 deploy` subprocess.

Fix:
- Updated `scripts/deploy_functions_guarded.sh` so the local metadata helper command runs with `FUNCTIONS_DISCOVERY_TIMEOUT` unset.
- Updated `scripts/deploy_functions_guarded.sh` so only the real Firebase deploy subprocess is invoked as:
  - `FUNCTIONS_DISCOVERY_TIMEOUT=30 npx -y "firebase-tools@$FIREBASE_TOOLS_VERSION" deploy --only "$TARGETS" --project "$PROJECT" --non-interactive`
- Updated `tests/test_deploy_functions_guarded_contract.py` test-first to assert:
  - metadata discovery sees `FUNCTIONS_DISCOVERY_TIMEOUT=unset`;
  - CLI version check sees `FUNCTIONS_DISCOVERY_TIMEOUT=unset`;
  - actual deploy sees `FUNCTIONS_DISCOVERY_TIMEOUT=30`;
  - dry-run still performs zero deploy invocations.

RED evidence:
- Command:
  - `python -m pytest -q tests/test_deploy_functions_guarded_contract.py -k "bootstrap_parameter_discovery_and_guard_precede_the_exact_deploy" --maxfail=1`
- Result:
  - Failed before the wrapper fix because the wrapper still contained `FUNCTIONS_DISCOVERY_TIMEOUT=30 npx -y --package="firebase-tools@$FIREBASE_TOOLS_VERSION" -- node`.

Focused wrapper verification:
- Command:
  - `python -m pytest -q tests/test_deploy_functions_guarded_contract.py --maxfail=1`
- Result:
  - `17 passed, 4 skipped in 0.86s`

Exact Git Bash / Node environment:
- Initial blocked command/result:
  - `C:\Program Files\Git\bin\bash.exe -lc 'pwd; node --version; npm --version'`
  - Sandbox run failed with `couldn't create signal pipe, Win32 error 5`.
  - Escalated run succeeded but reported `v24.14.0` / `11.10.1`, so it was not the approved Node 22 environment.
- Exact environment used for full Functions verification:
  - Extracted existing local archive `C:\tmp\node-v22.23.2-win-x64.zip` into worktree-local `.node-runtime`, then used Git Bash with:
  - `export PATH="/c/Users/samsung/StudioProjects/semisemifinal-security-integration/.tmp/functions-bootstrap-p1-2-2-20260924/.node-runtime/node-v22.23.2-win-x64:$PATH"`
  - Verified `node --version` -> `v22.23.2`
  - Verified `npm --version` -> `10.9.8`
  - Removed the temporary `.node-runtime` after verification.

Full Functions verification:
- Command:
  - `C:\Program Files\Git\bin\bash.exe -lc 'export PATH="/c/Users/samsung/StudioProjects/semisemifinal-security-integration/.tmp/functions-bootstrap-p1-2-2-20260924/.node-runtime/node-v22.23.2-win-x64:$PATH"; node --version; npm --version; npm --prefix functions run build'`
- Result:
  - `v22.23.2`
  - `10.9.8`
  - `> build`
  - `> tsc`
  - exit 0
- Command:
  - `C:\Program Files\Git\bin\bash.exe -lc 'export PATH="/c/Users/samsung/StudioProjects/semisemifinal-security-integration/.tmp/functions-bootstrap-p1-2-2-20260924/.node-runtime/node-v22.23.2-win-x64:$PATH"; node --version; npm --version; npm --prefix functions run lint'`
- Result:
  - `v22.23.2`
  - `10.9.8`
  - `> lint`
  - `> tsc --noEmit`
  - exit 0
- Command:
  - `C:\Program Files\Git\bin\bash.exe -lc 'export PATH="/c/Users/samsung/StudioProjects/semisemifinal-security-integration/.tmp/functions-bootstrap-p1-2-2-20260924/.node-runtime/node-v22.23.2-win-x64:$PATH"; node --version; npm --version; npm --prefix functions test'`
- Result:
  - `v22.23.2`
  - `10.9.8`
  - TAP summary: `tests 1089`, `suites 90`, `pass 1089`, `fail 0`, `cancelled 0`, `skipped 0`, `todo 0`, `duration_ms 24537.2413`
  - exit 0

Source-discovery verification:
- Command:
  - `python scripts/deploy_functions_guarded_contract.py source --firebase-json firebase.json`
- Result:
  - `C:\Users\samsung\StudioProjects\semisemifinal-security-integration\.tmp\functions-bootstrap-p1-2-2-20260924\functions`
  - exit 0

Notes:
- `functions/lib/` was generated by the full Functions build/test run and left uncommitted because it is outside Task 3 ownership.
- No Firebase deploy, Firestore write, cloud mutation, secret output, PR update, force-push, rebase, or history rewrite was performed.
