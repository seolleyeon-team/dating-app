from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.seolleyeon_avatar_prompt_builder_v4 import build_avatar_prompt


def _parse_numbers(value: str, *, cast):
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def _write_report(report: dict, path: Optional[str]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run FLUX parameter sweep for safe avatar fixtures.")
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--steps", default="4,6")
    parser.add_argument("--guidance", default="1.0,1.3")
    parser.add_argument("--candidate_count", type=int, default=4)
    parser.add_argument("--report_json", default="")
    args = parser.parse_args(argv)

    if not args.dry_run:
        parser.error("This local script only supports --dry_run; run live generation through the worker smoke script.")

    steps_values = _parse_numbers(args.steps, cast=int)
    guidance_values = _parse_numbers(args.guidance, cast=float)
    runs = []
    for steps in steps_values:
        for guidance in guidance_values:
            os.environ["AVATAR_FLUX_NUM_INFERENCE_STEPS"] = str(steps)
            os.environ["AVATAR_FLUX_GUIDANCE_SCALE"] = str(guidance)
            prompts = [
                build_avatar_prompt(
                    candidate_index=index,
                    candidate_count=args.candidate_count,
                    seed=1000 + index,
                )
                for index in range(args.candidate_count)
            ]
            runs.append(
                {
                    "steps": steps,
                    "guidanceScale": guidance,
                    "candidateCount": args.candidate_count,
                    "promptVersions": sorted(
                        {prompt.meta.get("prompt_version") for prompt in prompts}
                    ),
                    "promptWordCounts": [
                        prompt.meta.get("prompt_word_count_approx") for prompt in prompts
                    ],
                    "negativePromptKwargUsed": False,
                }
            )

    _write_report({"status": "ok", "mode": "dry_run", "runs": runs}, args.report_json)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
