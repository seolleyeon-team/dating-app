from __future__ import annotations

import logging
import re
from typing import Any, Callable, Mapping

from avatar_generation.trait_card import (
    FLORENCE2_TRAIT_EXTRACTION_PROMPT,
    TRAIT_CARD_SCHEMA_VERSION,
    TraitCardValidationResult,
    validate_trait_card_response,
)


FLORENCE2_MODEL_ID = "microsoft/Florence-2-large-ft"
FLORENCE2_TRAIT_EXTRACTION_VERSION = "florence2_trait_card_v3"
logger = logging.getLogger(__name__)

MockTraitResponse = str | Mapping[str, Any] | Callable[[Any, str], str | Mapping[str, Any]]


class Florence2TraitExtractionAdapter:
    """Local Florence-2 wrapper for privacy-safe trait-card extraction.

    Transformers are imported and model weights are loaded only when a real
    extraction is requested. Dry-run and mock paths are deterministic and do
    not touch model libraries or network-backed APIs.
    """

    model_id = FLORENCE2_MODEL_ID
    version = FLORENCE2_TRAIT_EXTRACTION_VERSION

    def __init__(
        self,
        *,
        model_id: str = FLORENCE2_MODEL_ID,
        processor: Any = None,
        model: Any = None,
        dry_run: bool = False,
        dry_run_response: MockTraitResponse | None = None,
        local_files_only: bool = True,
        device: str | None = None,
        torch_dtype: Any = None,
        trust_remote_code: bool = True,
        attn_implementation: str | None = "eager",
        task_prompt: str = "<MORE_DETAILED_CAPTION>",
        max_new_tokens: int = 512,
        num_beams: int = 1,
    ) -> None:
        self.model_id = model_id
        self.processor = processor
        self.model = model
        self.dry_run = bool(dry_run)
        self.dry_run_response = dry_run_response
        self.local_files_only = bool(local_files_only)
        self.device = device
        self.torch_dtype = torch_dtype
        self.trust_remote_code = bool(trust_remote_code)
        self.attn_implementation = (
            str(attn_implementation).strip() if attn_implementation else ""
        )
        self.task_prompt = self._normalize_task_prompt(task_prompt)
        self.max_new_tokens = int(max_new_tokens)
        self.num_beams = int(num_beams)

    def extract_traits(
        self,
        *,
        image: Any,
        response_override: MockTraitResponse | None = None,
        avatar_presentation_gender: Any = None,
    ) -> TraitCardValidationResult:
        response = response_override if response_override is not None else self.dry_run_response
        if response is not None:
            return validate_trait_card_response(
                self._resolve_mock_response(response, image),
                avatar_presentation_gender=avatar_presentation_gender,
            )

        if self.dry_run:
            return validate_trait_card_response(
                {
                    "schemaVersion": TRAIT_CARD_SCHEMA_VERSION,
                    "privacySafe": True,
                    "confidence": 0.0,
                    "traitCard": {},
                },
                avatar_presentation_gender=avatar_presentation_gender,
            )

        if image is None:
            raise ValueError("image is required for non-dry-run Florence-2 trait extraction")

        caption = self._generate_response(image)
        return validate_trait_card_response(
            self._caption_to_trait_response(caption),
            avatar_presentation_gender=avatar_presentation_gender,
        )

    def _resolve_mock_response(
        self,
        response: MockTraitResponse,
        image: Any,
    ) -> str | Mapping[str, Any]:
        if callable(response):
            return response(image, FLORENCE2_TRAIT_EXTRACTION_PROMPT)
        return response

    @staticmethod
    def _normalize_task_prompt(task_prompt: str | None) -> str:
        value = str(task_prompt or "MORE_DETAILED_CAPTION").strip()
        if not value:
            value = "MORE_DETAILED_CAPTION"
        if not value.startswith("<"):
            value = f"<{value}"
        if not value.endswith(">"):
            value = f"{value}>"
        return value

    def _load_components(self) -> tuple[Any, Any]:
        if self.processor is not None and self.model is not None:
            return self.processor, self.model

        from transformers import AutoModelForCausalLM as AutoModel
        from transformers import AutoProcessor

        load_kwargs: dict[str, Any] = {
            "trust_remote_code": self.trust_remote_code,
            "local_files_only": self.local_files_only,
        }
        if self.torch_dtype is not None:
            load_kwargs["torch_dtype"] = self.torch_dtype
        if self.attn_implementation:
            load_kwargs["attn_implementation"] = self.attn_implementation

        if self.processor is None:
            processor_kwargs = dict(load_kwargs)
            processor_kwargs.pop("attn_implementation", None)
            self.processor = AutoProcessor.from_pretrained(
                self.model_id,
                **processor_kwargs,
            )
        if self.model is None:
            self.model = AutoModel.from_pretrained(self.model_id, **load_kwargs)
            if self.device and hasattr(self.model, "to"):
                self.model = self.model.to(self.device)
            if hasattr(self.model, "eval"):
                self.model.eval()

        return self.processor, self.model

    def _generate_response(self, image: Any) -> str:
        processor, model = self._load_components()
        inputs = processor(
            text=self.task_prompt,
            images=image,
            return_tensors="pt",
        )

        inputs = self._prepare_inputs_for_model(inputs, model)

        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=self.max_new_tokens,
            num_beams=self.num_beams,
            do_sample=False,
            # Florence-2 remote model code can crash on transformers 4.50+
            # when the generation KV cache is enabled.
            use_cache=False,
        )
        decoded = processor.batch_decode(generated_ids, skip_special_tokens=False)
        generated_text = decoded[0] if decoded else ""
        return self._post_process_caption(processor, generated_text, image)

    def _prepare_inputs_for_model(self, inputs: Any, model: Any) -> Mapping[str, Any]:
        target_dtype = self.torch_dtype or getattr(model, "dtype", None)
        prepared: dict[str, Any] = {}
        for key, value in dict(inputs).items():
            if not hasattr(value, "to"):
                prepared[key] = value
                continue
            if key == "pixel_values" and target_dtype is not None:
                if self.device:
                    prepared[key] = value.to(device=self.device, dtype=target_dtype)
                else:
                    prepared[key] = value.to(dtype=target_dtype)
            elif self.device:
                prepared[key] = value.to(self.device)
            else:
                prepared[key] = value
        return prepared

    def _post_process_caption(self, processor: Any, generated_text: str, image: Any) -> str:
        if not hasattr(processor, "post_process_generation"):
            return generated_text
        width = int(getattr(image, "width", 0) or 0)
        height = int(getattr(image, "height", 0) or 0)
        if width <= 0 or height <= 0:
            return generated_text
        try:
            parsed = processor.post_process_generation(
                generated_text,
                task=self.task_prompt,
                image_size=(width, height),
            )
        except Exception as exc:  # pragma: no cover - model-code compatibility guard
            logger.warning(
                "Florence-2 post-process failed; using decoded caption: %s: %s",
                type(exc).__name__,
                str(exc).splitlines()[0][:160],
            )
            return generated_text
        if isinstance(parsed, Mapping):
            value = parsed.get(self.task_prompt)
            if isinstance(value, str):
                return value
            for candidate in parsed.values():
                if isinstance(candidate, str):
                    return candidate
        if isinstance(parsed, str):
            return parsed
        return generated_text

    def _caption_to_trait_response(self, caption: str) -> Mapping[str, Any]:
        text = str(caption or "").lower()

        def has_any(*needles: str) -> bool:
            return any(needle in text for needle in needles)

        face_and_eyes_visible = has_any(
            "face",
            "portrait",
            "head and shoulders",
            "head-and-shoulders",
            "eyes",
            "eye",
            "looking",
            "person",
        )
        no_eyewear_phrase = has_any(
            "without glasses",
            "no glasses",
            "no eyeglasses",
            "no eyewear",
            "not wearing glasses",
            "bare eyes",
            "unobstructed eyes",
        )
        eyewear_detected = has_any(
            "glasses",
            "eyeglasses",
            "spectacles",
            "eyewear",
            "sunglasses",
        ) and not no_eyewear_phrase
        eyewear_present = "unclear"
        eyewear_style = "unclear"
        eyewear_confidence = "unclear"
        eyewear_source = "florence"
        if eyewear_detected:
            eyewear_present = "yes"
            eyewear_confidence = "high" if has_any("wearing glasses", "wearing eyeglasses", "sunglasses") else "medium"
            if has_any("sunglasses"):
                eyewear_style = "sunglasses"
            elif has_any("clear frame", "clear-frame", "transparent frame"):
                eyewear_style = "clear_frame"
            elif has_any("round glasses", "round frame", "round-framed"):
                eyewear_style = "round_dark" if has_any("black", "dark") else "round_metal"
            elif has_any("rectangular glasses", "square glasses", "rectangular frame"):
                eyewear_style = "rectangular_dark" if has_any("black", "dark") else "rectangular_metal"
            elif has_any("metal frame", "thin frame", "wire frame"):
                eyewear_style = "thin_metal"
            else:
                eyewear_style = "other_simple"
        elif no_eyewear_phrase:
            eyewear_present = "no"
            eyewear_style = "none"
            eyewear_confidence = "high"

        hair_length = "unclear"
        if has_any("long hair", "long-haired"):
            hair_length = "long"
        elif has_any("short hair", "short-haired"):
            hair_length = "short"
        elif has_any("medium hair", "shoulder-length"):
            hair_length = "medium"

        hair_color = "unclear"
        if has_any("black hair"):
            hair_color = "black"
        elif has_any("dark brown hair"):
            hair_color = "dark_brown"
        elif has_any("light brown hair"):
            hair_color = "light_brown"
        elif has_any("brown hair"):
            hair_color = "brown"

        hair_volume = "unclear"
        if has_any("voluminous hair", "full hair", "thick hair") or re.search(
            r"\bhigh[-\s]+volume\b(?:[-\s]+\w+){0,2}[-\s]+\bhair\b", text
        ):
            hair_volume = "high"
        elif re.search(
            r"\b(?:medium|moderate)[-\s]+volume\b(?:[-\s]+\w+){0,2}[-\s]+\bhair\b", text
        ):
            hair_volume = "medium"
        elif has_any("flat hair", "thin hair", "slicked-down hair") or re.search(
            r"\blow[-\s]+volume\b(?:[-\s]+\w+){0,2}[-\s]+\bhair\b", text
        ):
            hair_volume = "low"

        hair_direction = "unclear"
        if has_any("side-parted hair", "side parted hair", "side part", "side-part"):
            hair_direction = "side_part"
        elif has_any("center-parted hair", "center parted hair", "middle-parted hair", "middle parted hair", "center part", "middle part"):
            hair_direction = "center_part"
        elif has_any("forward bangs", "front bangs", "bangs across the forehead", "bangs over the forehead"):
            hair_direction = "forward_bangs"
        elif has_any("swept-back hair", "swept back hair", "slicked-back hair", "slicked back hair", "combed-back hair", "combed back hair"):
            hair_direction = "swept_back"
        elif has_any("pulled-back hair", "pulled back hair", "hair pulled back", "ponytail", "hair in a bun"):
            hair_direction = "pulled_back"
        elif has_any("messy hair", "naturally messy hair", "tousled hair"):
            hair_direction = "natural_messy"

        hair_bangs = "unclear"
        if has_any("curtain bangs"):
            hair_bangs = "curtain_bangs"
        elif has_any("side bangs"):
            hair_bangs = "side_bangs"
        elif has_any("full bangs", "straight bangs"):
            hair_bangs = "full_bangs"
        elif has_any("bangs", "fringe"):
            hair_bangs = "soft_bangs"

        facial_hair_present = "unclear"
        facial_hair_style = "unclear"
        if has_any("clean-shaven", "clean shaven", "no facial hair"):
            facial_hair_present = "no"
            facial_hair_style = "none"
        elif has_any("stubble", "mustache", "moustache", "beard", "goatee"):
            facial_hair_present = "yes"
            if has_any("stubble"):
                facial_hair_style = "stubble"
            elif has_any("mustache", "moustache"):
                facial_hair_style = "mustache"
            elif has_any("goatee"):
                facial_hair_style = "goatee"
            else:
                facial_hair_style = "short_beard"

        face_shape_category = "unclear"
        if has_any("round face", "round facial shape"):
            face_shape_category = "round"
        elif has_any("oval face", "oval facial shape"):
            face_shape_category = "oval"
        elif has_any("long face", "long facial shape", "elongated face"):
            face_shape_category = "long"
        elif has_any("soft square face", "square face"):
            face_shape_category = "soft_square"

        facial_feature_balance = "unclear"
        if has_any("balanced features", "balanced facial features"):
            facial_feature_balance = "balanced"
        elif has_any("soft features", "soft facial features"):
            facial_feature_balance = "soft"
        elif has_any("defined features", "defined facial features"):
            facial_feature_balance = "defined"

        eye_size_category = "unclear"
        if has_any("small eyes"):
            eye_size_category = "small"
        elif has_any("large eyes", "medium-large eyes", "medium large eyes"):
            eye_size_category = "medium_large"
        elif has_any("medium eyes"):
            eye_size_category = "medium"

        eye_tilt_category = "unclear"
        if has_any("slightly upturned eyes", "upturned eyes"):
            eye_tilt_category = "slightly_upturned"
        elif has_any("slightly downturned eyes", "downturned eyes"):
            eye_tilt_category = "slightly_downturned"
        elif has_any("neutral eyes", "level eyes"):
            eye_tilt_category = "neutral"

        eye_shape_mood = "unclear"
        if has_any("gentle eyes", "gentle eye expression"):
            eye_shape_mood = "gentle"
        elif has_any("focused eyes", "focused gaze"):
            eye_shape_mood = "focused"
        elif has_any("calm eyes", "calm gaze"):
            eye_shape_mood = "calm"
        elif has_any("soft eyes", "soft gaze"):
            eye_shape_mood = "soft"
        elif eye_tilt_category in {"slightly_upturned", "slightly_downturned"}:
            eye_shape_mood = eye_tilt_category
        elif has_any("neutral expression", "neutral gaze"):
            eye_shape_mood = "neutral"

        brow_thickness = "unclear"
        if has_any("thin brows", "thin eyebrows"):
            brow_thickness = "thin"
        elif has_any("thick brows", "thick eyebrows", "full eyebrows"):
            brow_thickness = "thick"
        elif has_any("natural brows", "natural eyebrows"):
            brow_thickness = "natural"

        brow_shape = "unclear"
        if has_any("straight brows", "straight eyebrows"):
            brow_shape = "straight"
        elif has_any("soft arch brows", "soft-arch brows", "soft arched eyebrows", "soft arch eyebrows", "soft arch"):
            brow_shape = "soft_arch"
        elif has_any("arched brows", "arched eyebrows"):
            brow_shape = "arched"
        elif has_any("natural brows", "natural eyebrows"):
            brow_shape = "natural"

        nose_prominence = "unclear"
        if has_any("soft nose", "subtle nose"):
            nose_prominence = "soft"
        elif has_any("defined nose", "prominent nose"):
            nose_prominence = "defined"
        elif has_any("medium nose", "moderate nose"):
            nose_prominence = "medium"

        nose_bridge_impression = "unclear"
        if has_any("soft nose bridge"):
            nose_bridge_impression = "soft"
        elif has_any("defined nose bridge"):
            nose_bridge_impression = "defined"
        elif has_any("moderate nose bridge"):
            nose_bridge_impression = "moderate"
        elif has_any("medium nose bridge"):
            nose_bridge_impression = "medium"

        cheek_fullness = "unclear"
        if has_any("full cheeks", "rounded cheeks"):
            cheek_fullness = "full"
        elif has_any("moderate cheeks", "medium cheeks"):
            cheek_fullness = "moderate"
        elif has_any("low cheek fullness", "slim cheeks"):
            cheek_fullness = "low"

        jaw_impression = "unclear"
        if has_any("soft jaw", "soft jawline"):
            jaw_impression = "soft"
        elif has_any("moderately defined jaw", "moderate defined jaw", "defined jaw impression"):
            jaw_impression = "moderate_defined"
        elif has_any("broad soft jaw", "broad jaw"):
            jaw_impression = "broad_soft"

        mouth_expression = "unclear"
        if has_any("subtle smile", "slight smile", "smiling softly", "soft smile"):
            mouth_expression = "subtle_smile"
        elif has_any("calm closed mouth", "closed mouth"):
            mouth_expression = "calm_closed"
        elif has_any("neutral mouth", "neutral expression"):
            mouth_expression = "neutral"
        elif has_any("smile", "smiling"):
            mouth_expression = "subtle_smile"

        mouth_fullness_category = "unclear"
        if has_any("thin lips", "thin mouth"):
            mouth_fullness_category = "thin"
        elif has_any("subtle lips", "subtle mouth"):
            mouth_fullness_category = "subtle"
        elif has_any("full lips", "full mouth"):
            mouth_fullness_category = "full"
        elif has_any("medium lips", "medium mouth"):
            mouth_fullness_category = "medium"

        skin_tone_range = "unclear"
        if has_any("fair warm skin", "fair skin"):
            skin_tone_range = "fair_warm"
        elif has_any("natural beige skin", "beige skin"):
            skin_tone_range = "natural_beige"
        elif has_any("medium warm skin", "warm medium skin"):
            skin_tone_range = "medium_warm"
        elif has_any("sun kissed skin", "sun-kissed skin"):
            skin_tone_range = "sun_kissed"

        expression_mood = "unclear"
        if has_any("gentle expression", "gentle mood"):
            expression_mood = "gentle"
        elif has_any("focused expression", "focused mood"):
            expression_mood = "focused"
        elif has_any("calm expression", "calm mood", "calm"):
            expression_mood = "calm"
        elif has_any("neutral expression", "neutral mood", "neutral"):
            expression_mood = "neutral"

        clothing_category = "unclear"
        clothing_keywords = (
            ("hoodie", "hoodie"),
            ("sweatshirt", "sweatshirt"),
            ("t-shirt", "t_shirt"),
            ("tshirt", "t_shirt"),
            ("tee shirt", "t_shirt"),
            ("shirt", "shirt"),
            ("jacket", "jacket"),
            ("coat", "jacket"),
            ("knit", "knit"),
            ("polo", "polo"),
        )
        for keyword, value in clothing_keywords:
            if keyword in text:
                clothing_category = value
                break

        clothing_color = "unclear"
        clothing_colors = (
            ("white", "white"),
            ("black", "black"),
            ("gray", "gray"),
            ("grey", "gray"),
            ("navy", "navy"),
            ("blue", "blue"),
            ("beige", "beige"),
            ("brown", "brown"),
            ("green", "green"),
        )
        clothing_nouns = tuple(keyword for keyword, _ in clothing_keywords)
        for color, value in clothing_colors:
            color_pattern = re.escape(color)
            for noun in clothing_nouns:
                noun_pattern = re.escape(noun)
                color_before_noun = rf"\b{color_pattern}\b(?:[-\s]+\w+){{0,2}}[-\s]+\b{noun_pattern}\b"
                noun_before_color = rf"\b{noun_pattern}\b(?:\s+(?:is|was|looks|appears|in))?\s+\b{color_pattern}\b"
                if re.search(color_before_noun, text) or re.search(noun_before_color, text):
                    clothing_color = value
                    break
            if clothing_color != "unclear":
                break

        return {
            "schemaVersion": TRAIT_CARD_SCHEMA_VERSION,
            "privacySafe": True,
            "confidence": 0.35 if text.strip() else 0.0,
            "traitCard": {
                "visible_crop": "head_and_shoulders"
                if has_any("head", "shoulder", "portrait", "face")
                else "unclear",
                "hair_length": hair_length,
                "hair_volume": hair_volume,
                "hair_direction": hair_direction,
                "hair_bangs": hair_bangs,
                "hair_color_range": hair_color,
                "eyewear_present": eyewear_present,
                "eyewear_style": eyewear_style,
                "eyewear_confidence": eyewear_confidence,
                "eyewear_source": eyewear_source,
                "facial_hair_present": facial_hair_present,
                "facial_hair_style": facial_hair_style,
                "face_shape_category": face_shape_category,
                "facial_feature_balance": facial_feature_balance,
                "eye_size_category": eye_size_category,
                "eye_tilt_category": eye_tilt_category,
                "eye_shape_mood": eye_shape_mood,
                "brow_thickness": brow_thickness,
                "brow_shape": brow_shape,
                "nose_prominence": nose_prominence,
                "nose_bridge_impression": nose_bridge_impression,
                "cheek_fullness": cheek_fullness,
                "jaw_impression": jaw_impression,
                "mouth_expression": mouth_expression,
                "mouth_fullness_category": mouth_fullness_category,
                "skin_tone_range": skin_tone_range,
                "expression_mood": expression_mood,
                "clothing_category": clothing_category,
                "clothing_color": clothing_color,
            },
        }
