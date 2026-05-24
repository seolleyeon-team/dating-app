#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from ai_image_pipeline_v3.hermes_wrapper import main


if __name__ == "__main__":
    if os.environ.get("ALLOW_DEPRECATED_HERMES_IMAGE_PIPELINE") != "1":
        print(
            "scripts/run_hermes_image_pipeline_v3.py is deprecated for Seolleyeon AI profile image generation. "
            "Use scripts/run_ai_image_pipeline_v3.py bounded-chunk-status/reconcile/run so production stays on the bounded executor.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    raise SystemExit(main())
