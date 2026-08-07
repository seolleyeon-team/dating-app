# SEOLLEYEON — Phase 6P-6A mutation log

Only the five R2-authoritative affected ordinary heads were updated. Every update used an exact `--force-with-lease` expectation and the R2 bare rewrite candidate. No blind force push, mirror push, tag update, or unaffected-ref push was used.

## Push sequence

| Order | Ref | Lease old SHA | New SHA | Result |
|---:|---|---|---|---|
| 1 pilot | `audit/opus5-production-hardening` | `c4fe98dda8741e00f3a5a390b494b4758e0a06de` | `dd3dad982967e7b430a5c78fd7260f6a7658af9f` | accepted; post-push verification passed |
| 2 | `audit/p0-authz-hardening` | `d7c8beb418e836f46df69582c0155f60662ef892` | `18311abcf6bb969a9502449d82d4a6c97a0123b4` | accepted; post-push verification passed |
| 3 | `dowon0803` | `dece374b55d9b808966943ed54a2ea6cf501c2d6` | `585a424c0cee021acd946324d2260c5058690a53` | accepted; post-push verification passed |
| 4 | `kakao-message` | `733a77649bad2f920cdac7a7d0e8b158351131a0` | `fb407173ddf456c58670dad523b48c55460d074b` | accepted; post-push verification passed |
| 5 last | `main` | `ad8341a5c8516a49dad1671a026b3b99232f01e7` | `cdc6951b77f20a76e720199981b866f074f3b1ea` | accepted; final verification passed |

## Operational notes

- Each ref had an immediate `git ls-remote` lease precheck.
- The first post-push verification command for `audit/p0-authz-hardening` had a PowerShell variable-interpolation parse error; it performed no remote mutation. The corrected verification immediately passed.
- The first `main` precheck had a `HEAD` parsing-only comparison error; all underlying SHA/ref/tag conditions were already equal. The corrected hard gate passed before the main push.
- A dry-run for the pilot passed before the actual push.
- Remote push count: `5`.
- Tags changed: `0`.
- Unaffected ordinary refs changed: `0`.

