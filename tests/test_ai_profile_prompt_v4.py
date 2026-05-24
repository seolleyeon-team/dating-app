import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v3", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class AiProfilePromptV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()
        cls.full_specs = cls.m.generate_specs(female_count=120, male_count=120, seed=20260512)

    def test_schema_sampling_and_validation_include_v4_fields(self):
        spec = self.m.sample_spec("female", 1, seed=11)
        for key in ("skin", "accessories", "environment", "location", "fashion", "photo", "specialCase"):
            self.assertIn(key, spec)
        self.assertEqual(spec["schemaVersion"], "ai_profile_image_v3")
        self.assertEqual(spec["promptBuilderVersion"], "ai_profile_prompt_v4")
        self.assertEqual(spec["metadataVersion"], "ai_profile_image_v4_compatible")
        self.m.validate_spec(spec)

    def test_normalize_old_v3_spec_fills_safe_defaults(self):
        old = json.loads((PROMPT_PATH.parent / "female_137_sample_spec_v3.json").read_text(encoding="utf-8"))
        normalized = self.m.normalize_spec_defaults(old)
        for key in ("skin", "accessories", "environment", "location", "fashion", "photo", "specialCase"):
            self.assertIn(key, normalized)
        self.assertEqual(normalized["face"]["faceType"], "mixed_neutral")
        self.m.validate_spec(old)
        self.assertIn("Face details:", self.m.build_prompt(old, "face_card"))

    def test_face_type_alias_and_invalid_face_type_are_handled(self):
        spec = self.m.sample_spec("female", 2, seed=22)
        alias = deepcopy(spec)
        alias["face"]["faceType"] = "neutral_mixed"
        self.m.validate_spec(alias)
        self.assertEqual(self.m.normalize_spec_defaults(alias)["face"]["faceType"], "mixed_neutral")
        self.assertEqual(self.m.build_asset_record(alias, "face_card")["faceType"], "mixed_neutral")

        invalid = deepcopy(spec)
        invalid["face"]["faceType"] = "dragon_like"
        with self.assertRaises(ValueError):
            self.m.validate_spec(invalid)

    def test_adult_age_and_looks_level_guards(self):
        spec = self.m.sample_spec("male", 1, seed=12)
        underage = deepcopy(spec)
        underage["visualAge"] = 19
        with self.assertRaises(ValueError):
            self.m.validate_spec(underage)
        over_level = deepcopy(spec)
        over_level["face"]["looksLevel"] = 4.6
        over_level["face"]["looksLevelBand"] = "4.4-5.0"
        with self.assertRaises(ValueError):
            self.m.validate_spec(over_level)
        bad_band = deepcopy(spec)
        bad_band["face"]["looksLevel"] = 4.2
        bad_band["face"]["looksLevelBand"] = "4.4-5.0"
        with self.assertRaises(ValueError):
            self.m.validate_spec(bad_band)

    def test_looks_level_values_stay_inside_assigned_bands(self):
        bounds = {
            "1.5-2.4": (1.5, 2.4),
            "2.5-3.2": (2.5, 3.2),
            "3.3-3.8": (3.3, 3.8),
            "3.9-4.3": (3.9, 4.3),
            "4.4-5.0": (4.4, 5.0),
        }
        self.assertEqual(sum(spec["face"]["looksLevelBand"] == "4.4-5.0" for spec in self.full_specs), 0)
        for spec in self.full_specs:
            low, high = bounds[spec["face"]["looksLevelBand"]]
            self.assertGreaterEqual(float(spec["face"]["looksLevel"]), low)
            self.assertLessEqual(float(spec["face"]["looksLevel"]), high)

    def test_required_enum_and_consistency_validation_is_strict(self):
        base = self.m.sample_spec("female", 3, seed=33)
        mutations = [
            ("bad skin texture", ("skin", "texture"), "airbrushed"),
            ("bad skin retouching", ("skin", "retouching"), "heavy"),
            ("eyewear mismatch", ("accessories", "hasEyewear"), True),
            ("bad hat", ("accessories", "hat"), "face-covering mask"),
            ("bad accessory bag", ("accessories", "bag"), "luxury_logo_bag"),
            ("bad jewelry", ("accessories", "jewelry"), "colored fashion lenses"),
            ("bad temperature", ("environment", "temperatureFeel"), "humid_midnight"),
            ("bad bottom visible type", ("fashion", "bottomVisible"), "yes"),
            ("bad photo realism", ("photo", "realismProfile"), "commercial_studio"),
            ("bad camera mode", ("photo", "cameraMode"), "portrait"),
            ("bad imperfection level", ("photo", "imperfectionLevel"), "glossy"),
            ("bad special override", ("specialCase", "bottomVisibleOverride"), "sometimes"),
        ]
        for _, path, value in mutations:
            spec = deepcopy(base)
            spec[path[0]][path[1]] = value
            with self.subTest(path=path, value=value):
                with self.assertRaises(ValueError):
                    self.m.validate_spec(spec)

    def test_exact_eyewear_targets_and_identity_level_counting(self):
        female = [spec for spec in self.full_specs if spec["gender"] == "female"]
        male = [spec for spec in self.full_specs if spec["gender"] == "male"]
        self.assertEqual(sum(spec["accessories"]["eyewearGroup"] == "glasses" for spec in female), 12)
        self.assertEqual(sum(spec["accessories"]["eyewearGroup"] == "glasses" for spec in male), 24)
        self.assertEqual(sum(spec["accessories"]["eyewearGroup"] == "glasses" for spec in self.full_specs), 36)
        self.assertEqual(sum(3 for spec in self.full_specs if spec["accessories"]["eyewearGroup"] == "glasses"), 108)

    def test_reserve_size_eyewear_targets_and_determinism(self):
        female_reserve = self.m.generate_specs(female_count=20, male_count=0, seed=77)
        male_reserve = self.m.generate_specs(female_count=0, male_count=20, seed=77)
        again = self.m.generate_specs(female_count=20, male_count=0, seed=77)
        self.assertEqual(sum(spec["accessories"]["eyewearGroup"] == "glasses" for spec in female_reserve), 2)
        self.assertEqual(sum(spec["accessories"]["eyewearGroup"] == "glasses" for spec in male_reserve), 4)
        self.assertEqual(
            [spec["accessories"]["eyewear"] for spec in female_reserve],
            [spec["accessories"]["eyewear"] for spec in again],
        )

    def test_eyewear_spreads_across_face_and_looks_buckets(self):
        eyewear_specs = [spec for spec in self.full_specs if spec["accessories"]["eyewearGroup"] == "glasses"]
        self.assertGreater(len({spec["face"]["faceType"] for spec in eyewear_specs}), 1)
        self.assertGreater(len({spec["face"]["looksLevelBand"] for spec in eyewear_specs}), 1)

    def test_eyewear_metadata_is_consistent_across_asset_records(self):
        spec = next(spec for spec in self.full_specs if spec["accessories"]["eyewearGroup"] == "glasses")
        assets = self.m.build_asset_records(spec)
        self.assertEqual(len(assets), 3)
        self.assertEqual({asset["eyewearGroup"] for asset in assets}, {"glasses"})
        self.assertEqual({asset["eyewear"] for asset in assets}, {spec["accessories"]["eyewear"]})
        self.assertTrue(all(asset["hasEyewear"] for asset in assets))

    def test_eyewear_prompts_preserve_glasses_and_avoid_forbidden_eyewear(self):
        spec = next(spec for spec in self.full_specs if spec["accessories"]["eyewearGroup"] == "glasses")
        eyewear_text = self.m.EYEWEAR_VISUAL[spec["accessories"]["eyewear"]]
        prompts = {shot: self.m.build_prompt(spec, shot) for shot in self.m.SHOT_TYPES}
        self.assertIn(eyewear_text, prompts["face_card"])
        self.assertIn(eyewear_text, prompts["vibe_card"])
        self.assertIn(eyewear_text, prompts["silhouette_card"])
        positive = "\n".join(self.m.split_positive_and_negative_prompt(prompt)[0] for prompt in prompts.values()).lower()
        negative = "\n".join(self.m.split_positive_and_negative_prompt(prompt)[1] for prompt in prompts.values()).lower()
        self.assertNotIn("sunglasses", positive)
        self.assertNotIn("tinted lenses", positive)
        self.assertNotIn("face-covering mask", positive)
        self.assertIn("sunglasses", negative)
        self.assertIn("tinted lenses", negative)
        self.assertIn("face-covering mask", negative)

    def test_no_glasses_prompt_does_not_add_positive_glasses(self):
        spec = next(spec for spec in self.full_specs if spec["accessories"]["eyewearGroup"] == "none")
        positive, _ = self.m.split_positive_and_negative_prompt(self.m.build_prompt(spec, "face_card"))
        self.assertNotIn("glasses", positive.lower())

    def test_shot_specific_prompt_content(self):
        spec = next(spec for spec in self.full_specs if spec["accessories"]["eyewearGroup"] == "glasses")
        face = self.m.build_prompt(spec, "face_card")
        silhouette = self.m.build_prompt(spec, "silhouette_card")
        vibe = self.m.build_prompt(spec, "vibe_card")
        self.assertIn(self.m.SKIN_TONE_VISUAL[spec["skin"]["tone"]], face)
        self.assertIn("Upper outfit only:", face)
        self.assertNotIn(str(spec["fashion"]["bottom"]), face)
        self.assertIn(str(spec["fashion"]["bottom"]), silhouette)
        self.assertIn(str(spec["fashion"]["shoes"]), silhouette)
        self.assertIn(str(spec["fashion"]["bag"]).replace("_", " "), silhouette)
        self.assertIn(self.m.SEASON_VISUAL[spec["environment"]["season"]], silhouette)
        self.assertIn("Identity consistency:", vibe)
        self.assertIn(str(spec["vibeActivity"]), vibe)
        self.assertIn(self.m.SEASON_VISUAL[spec["environment"]["season"]], vibe)
        self.assertIn("not a professional photoshoot", face)
        self.assertIn("no heavy winter coat hiding body shape", silhouette)
        vibe_positive, vibe_negative = self.m.split_positive_and_negative_prompt(vibe)
        self.assertIn("ordinary campus profile image", vibe_positive)
        self.assertIn("influencer pose", vibe_negative)

    def test_season_prompt_constraints_remain_safe(self):
        winter = next(spec for spec in self.full_specs if spec["environment"]["season"] == "winter")
        winter_positive, _ = self.m.split_positive_and_negative_prompt(self.m.build_prompt(winter, "silhouette_card"))
        self.assertIn("no heavy winter coat hiding body shape", winter_positive)
        self.assertNotIn("heavy long padding", winter_positive.lower())

        summer = next(spec for spec in self.full_specs if spec["environment"]["season"] == "summer")
        combined_positive = "\n".join(
            self.m.split_positive_and_negative_prompt(self.m.build_prompt(summer, shot))[0]
            for shot in self.m.SHOT_TYPES
        ).lower()
        for forbidden in ("swimsuit", "crop top", "tank top", "revealing"):
            self.assertNotIn(forbidden, combined_positive)

    def test_shot_specific_location_fallback_uses_allowed_scene(self):
        spec = self.m.sample_spec("female", 9, seed=90)
        spec["location"] = deepcopy(self.m.LOCATION_CATALOG["small_exhibition"])
        spec["location"]["locationType"] = "small_exhibition"
        silhouette = self.m.build_prompt(spec, "silhouette_card")
        positive, _ = self.m.split_positive_and_negative_prompt(silhouette)
        self.assertIn(self.m.LOCATION_CATALOG["campus_walkway"]["scene"], positive)
        self.assertNotIn(self.m.LOCATION_CATALOG["small_exhibition"]["scene"], positive)

    def test_vibe_mood_line_does_not_duplicate_location_scene(self):
        spec = self.m.sample_spec("female", 10, seed=91)
        spec["vibeActivity"] = "sitting in a quiet library lounge with a notebook and tablet on the table"
        spec["location"] = deepcopy(self.m.LOCATION_CATALOG["local_park_near_campus"])
        spec["location"]["locationType"] = "local_park_near_campus"

        positive, _ = self.m.split_positive_and_negative_prompt(self.m.build_prompt(spec, "vibe_card"))
        mood_section = positive.split("Mood and lifestyle:", 1)[1].split("Composition:", 1)[0].lower()
        location_section = positive.split("Location:", 1)[1].split("Lighting and camera:", 1)[0].lower()

        self.assertTrue(
            any(activity.lower() in mood_section for activity in self.m.LOCATION_VIBE_ACTIVITIES["local_park_near_campus"])
        )
        self.assertNotIn("library lounge", mood_section)
        self.assertNotIn("campus cafe", mood_section)
        self.assertNotIn("campus path", mood_section)
        self.assertNotIn("campus garden", mood_section)
        self.assertIn("local park near campus", location_section)
        self.assertEqual(positive.count("Location:"), 1)

    def test_positive_safety_scanner_distinguishes_negative_prompt(self):
        safe_negative = "Portrait in a campus cafe.\n\nAvoid: school uniform, swimsuit, bar, idol, influencer."
        self.assertEqual(self.m.scan_prompt_for_banned_terms(safe_negative), [])
        self.m.validate_no_banned_positive_terms(safe_negative)
        with self.assertRaises(ValueError):
            self.m.validate_no_banned_positive_terms("A student wearing school uniform on campus.")

    def test_disallowed_special_cases_locations_fashion_and_brands_are_blocked(self):
        base = self.m.sample_spec("female", 7, seed=700)
        cases = []
        for case_type in ("school_uniform", "swimsuit", "bathroom_mirror", "gym_mirror", "volunteer_with_children"):
            spec = deepcopy(base)
            spec["specialCase"]["type"] = case_type
            cases.append(spec)
        for location_type in ("bar", "nightclub", "bathroom", "gym_mirror"):
            spec = deepcopy(base)
            spec["location"]["locationType"] = location_type
            cases.append(spec)
        for category in ("street_punk", "glam", "ably", "teto", "face-covering gorpcore"):
            spec = deepcopy(base)
            spec["fashion"]["category"] = category
            cases.append(spec)
        brand = deepcopy(base)
        brand["location"]["scene"] = "Nike branded shop interior with visible logo"
        cases.append(brand)
        travel = deepcopy(base)
        travel["location"]["scene"] = "famous travel landmark near a luxury hotel"
        cases.append(travel)
        jersey = deepcopy(base)
        jersey["fashion"]["top"] = "Barcelona team jersey with Adidas logo"
        cases.append(jersey)
        for spec in cases:
            with self.subTest(spec=spec.get("specialCase", {}).get("type") or spec.get("location", {}).get("locationType") or spec.get("fashion", {}).get("category")):
                with self.assertRaises(ValueError):
                    self.m.validate_spec(spec)

    def test_catalogs_are_structurally_safe_and_do_not_use_raw_old_categories(self):
        self.m.validate_catalog_safety()
        required_locations = {
            "campus_walkway",
            "campus_cafe",
            "library_lounge",
            "lecture_building_hallway",
            "student_union_lounge",
            "small_exhibition",
            "bookstore_near_campus",
            "local_park_near_campus",
            "campus_garden",
            "campus_sports_court",
            "quiet_study_room",
            "dorm_common_lounge",
            "neutral_outdoor_street_near_campus",
        }
        self.assertLessEqual(required_locations, set(self.m.LOCATION_CATALOG))
        for location_type, entry in self.m.LOCATION_CATALOG.items():
            with self.subTest(location=location_type):
                self.assertIn("seasonCompatibility", entry)
                self.assertIn("notes", entry)
                self.assertNotEqual(entry["privacyRisk"], "high")
                self.assertNotEqual(entry["logoTextRisk"], "high")
        unsafe_categories = {"street_punk", "glam", "ably", "teto", "street_gorpcore"}
        for gender, categories in self.m.SAFE_FASHION_CATALOG.items():
            self.assertFalse(unsafe_categories & set(categories), gender)

    def test_default_distribution_counts_pass(self):
        audit = self.m.audit_prompt_distribution(self.full_specs)
        self.assertTrue(audit["passed"], audit["mismatches"])
        self.assertEqual(audit["counts"]["faceType"], self.m.FACE_TYPE_TARGETS["global"])
        self.assertEqual(audit["counts"]["looksLevelBand"], self.m.LOOKS_LEVEL_BAND_TARGETS["global"])
        self.assertEqual(audit["counts"]["genderEyewear"]["female_with_eyewear"], 12)
        self.assertEqual(audit["counts"]["genderEyewear"]["male_with_eyewear"], 24)
        self.assertEqual(audit["counts"]["genderEyewear"]["total_with_eyewear"], 36)
        self.assertEqual(audit["counts"]["genderEyewear"]["total_without_eyewear"], 204)
        self.assertEqual(audit["counts"]["season"], self.m.SEASON_TARGETS)

    def test_export_writes_v4_distribution_report_and_extra_csv_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            specs = self.m.generate_specs(female_count=3, male_count=3, seed=5)
            result = self.m.export_batch(specs, Path(tmp))
            report_path = Path(result["distributionReportJson"])
            self.assertTrue(report_path.exists())
            self.assertIn("promptDistribution", json.loads(report_path.read_text(encoding="utf-8")))
            with Path(result["assetsCsv"]).open("r", encoding="utf-8", newline="") as f:
                columns = set(next(csv.DictReader(f)).keys())
            for col in (
                "skinTone",
                "eyewear",
                "canonicalEyewear",
                "shotEyewearExpected",
                "season",
                "locationType",
                "fashionCategory",
                "specialCase",
                "bottomVisible",
                "silhouetteReadable",
            ):
                self.assertIn(col, columns)

    def test_cli_batch_and_rec_event_context_still_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "batch"
            batch = subprocess.run(
                [
                    sys.executable,
                    str(PROMPT_PATH),
                    "batch",
                    "--female_count",
                    "1",
                    "--male_count",
                    "1",
                    "--out_dir",
                    str(out_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            result = json.loads(batch.stdout)
            self.assertTrue(Path(result["assetsJsonl"]).exists())
            spec_path = out_dir / "one_spec.json"
            first_spec = json.loads((out_dir / "ai_profile_specs_v3.jsonl").read_text(encoding="utf-8").splitlines()[0])
            spec_path.write_text(json.dumps(first_spec), encoding="utf-8")
            rec = subprocess.run(
                [
                    sys.executable,
                    str(PROMPT_PATH),
                    "rec_event_context",
                    "--spec",
                    str(spec_path),
                    "--shot_type",
                    "face_card",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            event = json.loads(rec.stdout)
            self.assertEqual(event["context"]["metadataVersion"], "ai_profile_image_v4_compatible")

    def test_cli_sample_and_prompt_still_work(self):
        sample = subprocess.run(
            [
                sys.executable,
                str(PROMPT_PATH),
                "sample",
                "--gender",
                "female",
                "--numeric_id",
                "1",
                "--seed",
                "123",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        spec = json.loads(sample.stdout)
        self.assertEqual(spec["profileId"], "female_001")

        with tempfile.TemporaryDirectory() as tmp:
            spec_path = Path(tmp) / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8-sig")
            prompt = subprocess.run(
                [
                    sys.executable,
                    str(PROMPT_PATH),
                    "prompt",
                    "--spec",
                    str(spec_path),
                    "--shot_type",
                    "vibe_card",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Identity consistency:", prompt.stdout)


if __name__ == "__main__":
    unittest.main()
