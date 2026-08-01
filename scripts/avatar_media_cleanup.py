from __future__ import annotations

import sys
from pathlib import Path

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.cleanup import main


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
