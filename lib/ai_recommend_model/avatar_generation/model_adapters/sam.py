from __future__ import annotations

from typing import Any, Callable, Sequence

from PIL import Image, ImageChops

from avatar_generation.analysis.segmentation import (
    FaceRegion,
    SegmentationResult,
    fallback_segment_reference_regions,
)


class SamUnavailableError(RuntimeError):
    pass


class SamSegmentationAdapter:
    """Optional SAM adapter with lazy loading and a dependency-free mock path."""

    provider_name = "sam"

    def __init__(
        self,
        *,
        model_path: str,
        model_type: str = "vit_h",
        device: str | None = None,
        loader: Callable[[str], Any] | None = None,
    ) -> None:
        self.model_path = model_path
        self.model_type = model_type
        self.device = device
        self._loader = loader
        self._model: Any | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def segment(
        self,
        image: Image.Image,
        *,
        face_hints: Sequence[FaceRegion] = (),
    ) -> SegmentationResult:
        model = self._load_model()
        if hasattr(model, "segment"):
            result = model.segment(image, face_hints=face_hints)
            if isinstance(result, SegmentationResult):
                return result
            raise SamUnavailableError("SAM model segment() returned an unsupported result.")

        if hasattr(model, "predict") and hasattr(model, "set_image"):
            return self._segment_with_predictor(model, image, face_hints=face_hints)

        raise SamUnavailableError("SAM model does not expose a supported segmentation interface.")

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self._loader is not None:
            self._model = self._loader(self.model_path)
            return self._model
        if self.model_path.startswith("mock://"):
            self._model = _MockSamModel(self.model_path)
            return self._model

        try:
            from segment_anything import SamPredictor, sam_model_registry
        except ImportError as exc:  # pragma: no cover - optional dependency.
            raise SamUnavailableError(
                "segment_anything is not installed; use mock:// for tests or disable SAM."
            ) from exc

        try:
            model = sam_model_registry[self.model_type](checkpoint=self.model_path)
        except KeyError as exc:  # pragma: no cover - optional dependency.
            raise SamUnavailableError(f"Unsupported SAM model type: {self.model_type}") from exc
        if self.device and hasattr(model, "to"):
            model.to(device=self.device)
        self._model = SamPredictor(model)
        return self._model

    def _segment_with_predictor(
        self,
        predictor: Any,
        image: Image.Image,
        *,
        face_hints: Sequence[FaceRegion],
    ) -> SegmentationResult:
        if not face_hints:
            return fallback_segment_reference_regions(
                image,
                face_regions=(),
                provider=self.provider_name,
                extra_metadata={"modelPath": self.model_path, "modelType": self.model_type},
            )

        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover - real SAM path requires numpy.
            raise SamUnavailableError("numpy is required for SAM segmentation.") from exc

        face = face_hints[0].clamped(image.size)
        if face is None:
            return fallback_segment_reference_regions(
                image,
                face_regions=(),
                provider=self.provider_name,
                extra_metadata={"modelPath": self.model_path, "modelType": self.model_type},
            )

        predictor.set_image(np.asarray(image.convert("RGB")))
        masks, scores, _ = predictor.predict(
            box=np.asarray(face.bbox),
            multimask_output=False,
        )
        mask = Image.fromarray((masks[0].astype("uint8") * 255), mode="L").resize(image.size)
        style_mask = ImageChops.invert(mask)
        score = float(scores[0]) if len(scores) else None
        return SegmentationResult(
            provider=self.provider_name,
            face_mask=mask,
            style_mask=style_mask,
            faces=(face,),
            metadata={
                "modelPath": self.model_path,
                "modelType": self.model_type,
                "score": score,
            },
        )


class _MockSamModel:
    def __init__(self, model_path: str) -> None:
        self.model_path = model_path

    def segment(
        self,
        image: Image.Image,
        *,
        face_hints: Sequence[FaceRegion] = (),
    ) -> SegmentationResult:
        return fallback_segment_reference_regions(
            image,
            face_regions=face_hints,
            provider="sam_mock",
            extra_metadata={"modelPath": self.model_path},
        )
