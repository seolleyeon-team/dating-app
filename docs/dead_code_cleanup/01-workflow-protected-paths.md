# Workflow protected paths

## Source files and parser result

The supplied workflow exports were both read:

- `C:/Users/samsung/Downloads/ui.drawio (2).html`
- `C:/Users/samsung/Downloads/ui.drawio (5).svg`

| Export | Bytes | SHA-256 |
|---|---:|---|
| HTML | 228,017 | `248149DE63DE8932FC0971A0F39C637E7FE2549117CD9AE806C2270A9005F1FE` |
| SVG | 3,486,099 | `3E3E227222827BB8F5D8AD5B4255D97A0513D2EA2A8880EF49ECDAFE6BBEA978` |

Both exports contain the same draw.io `mxGraphModel`. Parsing produced 410 cells, 253 vertices, 155 edges, 253 labels, 18 YES/NO branch labels, and 56 raw `.dart` labels. After slash normalization, `lib/` normalization for the two omitted prefixes, and duplicate removal, the graph yielded 54 canonical Dart references. Label and edge comparisons between the two exports produced no differences.

## Protected current paths

The following workflow-connected current paths are protected from deletion. A workflow reference is not required to be a Dart `import`; route strings, callbacks, assets, backend operations, and tests connected to these flows are protected as well.

### Authentication and onboarding

```text
lib/features/onboarding/screens/terms_screen.dart
lib/features/onboarding/screens/terms_detail_sheet.dart
lib/features/onboarding/screens/basic_info_screen.dart
lib/features/onboarding/screens/interests_selection_screen.dart
lib/features/onboarding/screens/height_selection_screen.dart
lib/features/onboarding/screens/lifestyle_screen.dart
lib/features/onboarding/screens/major_selection_screen.dart
lib/features/onboarding/screens/photo_upload_screen.dart
lib/features/onboarding/screens/self_introduction_screen.dart
lib/features/onboarding/screens/profile_qa_screen.dart
lib/features/onboarding/screens/keyword_screen.dart
lib/features/onboarding/screens/ideal_height_range_screen.dart
lib/features/onboarding/screens/ideal_type/ideal_type_screen.dart
lib/features/onboarding/screens/ideal_type/ideal_personality_screen.dart
lib/features/onboarding/screens/ideal_type/ideal_age_screen.dart
lib/features/onboarding/screens/ideal_type/ideal_lifestyle_screen.dart
lib/features/onboarding/screens/ideal_type/ideal_department_screen.dart
```

The export also contains `features/onboarding/...` labels without the `lib/` prefix. Those were canonicalized to the paths above, not treated as separate files.

### Tutorials, recommendations, chat, profile, and community

```text
lib/features/tutorial/screens/welcome_tutorial_screen.dart
lib/features/tutorial/screens/tutorial_screen.dart
lib/features/tutorial/screens/todays_match_tutorial_screen.dart
lib/features/tutorial/screens/ai_taste_button_tutorial_screen.dart
lib/features/tutorial/screens/ai_taste_training_screen.dart
lib/features/tutorial/screens/ai_taste_training_tutorial_screen.dart
lib/features/tutorial/screens/slot_machine_tutorial_screen.dart
lib/features/tutorial/screens/promise_agreement_tutorial_screen.dart
lib/features/tutorial/screens/season_meeting_intro_screen.dart
lib/features/tutorial/screens/bamboo_forest_intro_tutorial_screen.dart
lib/features/tutorial/screens/bamboo_forest_safety_tutorial_screen.dart
lib/features/tutorial/screens/bamboo_forest_write_tutorial_screen.dart

lib/features/matching/screens/mystery_card_screen.dart
lib/features/matching/screens/profile_discovery_screen.dart
lib/features/matching/screens/ai_match_card_screen.dart
lib/features/matching/screens/profile_specific_detail_screen.dart
lib/features/matching/screens/ai_preference_screen.dart
lib/features/chat/screens/premium_chat_list_screen.dart
lib/features/chat/screens/chat_room_screen.dart
lib/features/chat/screens/group_match_screen.dart
lib/features/community/screens/community_screen.dart
lib/features/community/screens/post_detail_screen.dart
lib/features/community/screens/post_write_screen.dart
lib/features/profile/screens/my_page_screen.dart
lib/features/profile/screens/profile_edit_screen.dart
lib/features/profile/screens/friends_list_screen.dart
lib/features/profile/screens/heart_charge_screen.dart
lib/features/profile/screens/received_hearts_screen.dart
lib/features/profile/screens/settings_screen.dart
```

### Events and meetings

```text
lib/features/event/screens/event_screen.dart
lib/features/event/screens/season_meeting_roulette_screen.dart
lib/features/event/screens/random_mathcing_screen.dart
lib/features/event/screens/match_result_screen.dart
lib/features/event/screens/team_setup_screen.dart
lib/features/event/screens/three_vs_three_match_screen.dart
```

The intentional spelling `random_mathcing_screen.dart` is currently imported by `lib/router/app_router.dart` and is covered by `test/critical_user_journey_contract_test.dart`. It is therefore protected even though it looks like a typo.

## Diagram-to-current mapping

| Old/stale diagram label | Current state | Evidence | Cleanup decision |
|---|---|---|---|
| `lib/features/event/screens/random_matching_screen.dart` | Absent | No file in current tree; current router uses `random_mathcing_screen.dart` | No deletion; stale label |
| `lib/features/event/screens/random_meeting_screen.dart` | Absent | Git commit `2cd46c1c` removed it during the blind-meeting replacement | No deletion; intentional replacement |
| `lib/features/meeting/screens/meeting_application_screen.dart` | Absent | Git commit `2cd46c1c` removed it during the blind-meeting replacement | No deletion; intentional replacement |
| `lib/features/matching/screens/ai_preference.dart` | Renamed; current file is `ai_preference_screen.dart` | Current router import and tests reference the `_screen` path | No deletion; stale name |
| `features/tutorial/screens/todays_match_tutorial_screen.dart` | Current file exists under `lib/` | Export omitted `lib/` | No deletion; canonicalization |

The old `3:3 random meeting` concept must not be treated as a reason to remove the current `3:3 blind taste meeting`. The current legacy route names are compatibility aliases and redirect to the current blind-meeting intro; they are not evidence that the current blind-meeting implementation is dead.

## Mandatory protected surfaces

The workflow graph is not a complete runtime map. In addition to every path above, protect all connected:

- current and legacy route aliases, deep links, route arguments, notification tap routes, and terminated-state replay;
- `3:3` blind taste meeting, `3:3` season meeting, matching, eligibility, safety-stamp lifecycle, result/follow-up, and no-show/deposit behavior;
- meeting icebreaker roulette, bomb-pass timer/audio, quiet repeated notifications, Cloud Tasks, Scheduler, and their reconciliation jobs;
- Firebase Functions exports/triggers, Firestore/Storage rules and indexes, migration/repair/backfill jobs;
- push/background entry points, Android/iOS registration, web bootstrap/service worker, assets, tests, fixtures, and operational scripts.

This document is a protection manifest, not a deletion list.
