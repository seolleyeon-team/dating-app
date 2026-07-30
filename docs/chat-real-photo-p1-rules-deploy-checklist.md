# Chat Real Photo P1 Rules Deploy Checklist

## Local Checks

```sh
bash scripts/p1_rules_diff_check.sh
```

Confirm:

- `userPrivateMedia` client read/write denied
- `clipEmbeddings` client read/write denied
- `users/{uid}` cannot persist `chatRealPhotoUrl`, `realProfilePhotoUrl`, `sourcePhotoUrl`, `sourcePhotoRefs`, `sourcePhotoGcsUri`, `gcsUri`, or signed URL fields
- `chat_rooms/{roomId}` cannot persist signed URLs, private bucket refs, chat-profile bucket refs, or real photo public URLs
- `storage.rules` denies direct client read/write for `seolleyeon-chat-profile-photos`
- source/temp bucket paths remain denied
- approved avatar bucket behavior is unchanged

## Deploy

```sh
bash scripts/p1_deploy_rules_staging.sh --apply
```

The script checks project mismatch and refuses production-like mutation unless explicitly allowed.

## After Deploy

- Wait for rules propagation.
- Run privacy QA.
- Run A/B/C callable matrix.
- Confirm no public document stores signed or private media refs.
