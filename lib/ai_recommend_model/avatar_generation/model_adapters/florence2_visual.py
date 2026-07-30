from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from avatar_generation.analysis.visual_risk import (
    TASK_MORE_DETAILED_CAPTION,
    TASK_OCR_WITH_REGION,
    TASK_OD,
    VisualRiskAnalysis,
    analyze_florence_visual_risk_outputs,
    unavailable_visual_risk_analysis,
)

ProcessorFactory = Callable[..., Any]
ModelFactory = Callable[..., Any]


class Florence2VisualRiskAdapter:
    provider = "florence2"

    def __init__(
        self,
        model_id: str = "microsoft/Florence-2-large-ft",
        *,
        device: Optional[str] = None,
        torch_dtype: Optional[Any] = None,
        include_detailed_caption: bool = False,
        local_files_only: bool = True,
        processor_factory: Optional[ProcessorFactory] = None,
        model_factory: Optional[ModelFactory] = None,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.torch_dtype = torch_dtype
        self.include_detailed_caption = include_detailed_caption
        self.local_files_only = local_files_only
        self._processor_factory = processor_factory
        self._model_factory = model_factory
        self._processor: Any = None
        self._model: Any = None

    def analyze(
        self,
        image: Any,
        *,
        primary_face_bbox_xyxy: Optional[Sequence[float]] = None,
    ) -> VisualRiskAnalysis:
        try:
            outputs = self.detect(image)
            image_size = _image_size(image)
        except Exception:
            return unavailable_visual_risk_analysis(
                self.provider,
                error_code="florence2_inference_unavailable",
            )
        return analyze_florence_visual_risk_outputs(
            outputs,
            provider=self.provider,
            image_size=image_size,
            primary_face_bbox_xyxy=primary_face_bbox_xyxy,
        )

    def detect(self, image: Any) -> Dict[str, Any]:
        self._ensure_loaded()
        tasks = [TASK_OCR_WITH_REGION, TASK_OD]
        if self.include_detailed_caption:
            tasks.append(TASK_MORE_DETAILED_CAPTION)
        return {task: self._run_task(image, task) for task in tasks}

    def _ensure_loaded(self) -> None:
        if self._processor is not None and self._model is not None:
            return
        processor_factory, model_factory = self._factories()
        common_kwargs = {"local_files_only": self.local_files_only}
        model_kwargs: Dict[str, Any] = dict(common_kwargs)
        if self.torch_dtype is not None:
            model_kwargs["torch_dtype"] = self.torch_dtype
        self._processor = processor_factory(self.model_id, **common_kwargs)
        self._model = model_factory(self.model_id, **model_kwargs)
        if self.device:
            self._model = self._model.to(self.device)

    def _factories(self) -> Tuple[ProcessorFactory, ModelFactory]:
        if self._processor_factory is not None and self._model_factory is not None:
            return self._processor_factory, self._model_factory
        from transformers import (  # type: ignore
            Florence2ForConditionalGeneration,
            Florence2Processor,
        )

        return (
            Florence2Processor.from_pretrained,
            Florence2ForConditionalGeneration.from_pretrained,
        )

    def _run_task(self, image: Any, task: str) -> Any:
        inputs = self._processor(text=task, images=image, return_tensors="pt")
        if self.device and hasattr(inputs, "to"):
            inputs = inputs.to(self.device)
        generated_ids = self._model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=1024,
            num_beams=3,
        )
        generated_text = self._processor.batch_decode(
            generated_ids,
            skip_special_tokens=False,
        )[0]
        return self._processor.post_process_generation(
            generated_text,
            task=task,
            image_size=_image_size(image),
        )


def _image_size(image: Any) -> Tuple[int, int]:
    if hasattr(image, "size") and isinstance(image.size, tuple) and len(image.size) == 2:
        return (int(image.size[0]), int(image.size[1]))
    return (int(image.width), int(image.height))
