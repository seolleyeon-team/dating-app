from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.cleanup import (  # noqa: E402
    cleanup_expired_avatar_candidates,
    default_firestore_client,
    default_storage_client,
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scheduled TTL cleanup for expired Seolleyeon avatar temp candidates."
    )
    parser.add_argument("--firestore_project")
    parser.add_argument("--firestore_database")
    parser.add_argument("--max_delete_per_run", type=int, default=500)
    parser.add_argument("--apply", action="store_true", help="Delete temp objects and update Firestore. Default is dry-run.")
    parser.add_argument("--output_report_json", help="Optional path for a JSON summary report.")
    args = parser.parse_args(argv)

    firestore_client = default_firestore_client(args.firestore_project, args.firestore_database)
    storage_client = default_storage_client(args.firestore_project)
    summary = cleanup_expired_avatar_candidates(
        firestore_client=firestore_client,
        storage_client=storage_client,
        dry_run=not args.apply,
        max_delete_per_run=args.max_delete_per_run,
    )
    report = summary.to_dict()
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_report_json:
        Path(args.output_report_json).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
