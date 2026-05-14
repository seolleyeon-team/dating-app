import json
import tempfile
import unittest
from pathlib import Path


class CodexImagegenPendingTests(unittest.TestCase):
    def test_read_pending_accepts_utf8_bom_checkpoint(self):
        from scripts.ai_image_pipeline_v3.codex_imagegen import read_pending

        with tempfile.TemporaryDirectory() as tmp:
            pending = Path(tmp) / "pending-imagegen.json"
            payload = {"assetId": "female_026__face_card__v001", "resolved": True}
            pending.write_text(json.dumps(payload), encoding="utf-8-sig")

            self.assertEqual(read_pending(pending), payload)


if __name__ == "__main__":
    unittest.main()
