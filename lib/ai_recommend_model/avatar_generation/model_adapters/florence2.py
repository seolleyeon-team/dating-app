from __future__ import annotations

import logging
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
        elif has_any("brown hair"):
            hair_color = "brown"
        elif has_any("light brown hair"):
            hair_color = "light_brown"

        clothing_category = "unclear"
        for keyword, value in (
            ("hoodie", "hoodie"),
            ("sweatshirt", "sweatshirt"),
            ("t-shirt", "tshirt"),
            ("tshirt", "tshirt"),
            ("shirt", "shirt"),
            ("jacket", "jacket"),
            ("coat", "coat"),
            ("knit", "knit"),
            ("polo", "polo"),
        ):
            if keyword in text:
                clothing_category = value
                break

        clothing_color = "unclear"
        for color, value in (
            ("white", "white"),
            ("black", "black"),
            ("gray", "gray"),
            ("grey", "gray"),
            ("navy", "navy"),
            ("blue", "blue"),
            ("beige", "beige"),
            ("brown", "brown"),
            ("green", "green"),
            ("pink", "muted_pink"),
        ):
            if clothing_category != "unclear" and f"{color} {clothing_category}" in text:
                clothing_color = value
                break
        for keyword, value in (
            ("white", "white"),
            ("black", "black"),
            ("gray", "gray"),
            ("grey", "gray"),
            ("navy", "navy"),
            ("blue", "blue"),
            ("beige", "beige"),
            ("brown", "brown"),
            ("green", "green"),
            ("pink", "muted_pink"),
        ):
            if clothing_color != "unclear":
                break
            if keyword in text:
                clothing_color = value
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
                "hair_volume": "unclear",
                "hair_direction": "unclear",
                "hair_color_range": hair_color,
                "eyewear_present": "yes" if has_any("glasses", "eyewear") else "unclear",
                "eyewear_style": "unclear",
                "face_shape_category": "unclear",
                "eye_size_category": "unclear",
                "eye_tilt_category": "unclear",
                "brow_thickness": "unclear",
                "nose_prominence": "unclear",
                "cheek_fullness": "unclear",
                "jaw_impression": "unclear",
                "mouth_expression": "subtle_smile"
                if has_any("smile", "smiling")
                else "unclear",
                "skin_tone_range": "unclear",
                "expression_mood": "calm"
                if has_any("calm", "neutral")
                else "unclear",
                "clothing_category": clothing_category,
                "clothing_color": clothing_color,
            },
        }
