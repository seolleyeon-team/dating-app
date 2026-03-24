#!/usr/bin/env python3
"""
Seolleyeon CLIP Embedder (Hugging Face Transformers, AutoModel)

- 목적: 프로필 사진을 CLIP 임베딩 벡터로 변환해서 KNN/Vector Search에 쓰기.
- 특징:
  * AutoModel + AutoProcessor로 로드
  * 이미지 임베딩(get_image_features) 추출
  * L2 normalize 옵션(벡터 검색에서 cosine/dot-product에 유리)
  * 로컬 파일 경로 / https URL 입력 지원
  * 여러 장 프로필 사진 평균(mean) 임베딩 지원
  * like/nope로 사용자 preference vector 계산 지원

참고: CLIP 문서에서 processor(images=..., return_tensors="pt") + model.get_image_features(...) 예시가 있음.
"""

import argparse
import json
import os
import re
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

import requests
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor


# -----------------------------
# Defaults (모델/다운로드 보안)
# -----------------------------
DEFAULT_MODEL_ID = os.getenv("CLIP_MODEL_ID", "openai/clip-vit-base-patch32")

# 서버(Cloud Run)에서 URL을 받아 다운로드할 때 SSRF 위험을 줄이고 싶으면 allowlist 사용
# 로컬에서만 쓰면 비워도 됨(빈 값이면 allowlist 체크 안 함)
DEFAULT_ALLOWED_HOSTS = os.getenv(
    "ALLOWED_IMAGE_HOSTS",
    "firebasestorage.googleapis.com,storage.googleapis.com"
)

DEFAULT_MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(5 * 1024 * 1024)))  # 5MB
DEFAULT_HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "8.0"))


def _pick_device(device: str) -> torch.device:
    if device == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(device)


def _pick_dtype(dtype: str, device: torch.device) -> torch.dtype:
    """
    dtype="auto"면:
    - CUDA: float16 (대부분 빠름/저렴)
    - CPU: float32 (안정적)
    """
    if dtype == "auto":
        return torch.float16 if device.type == "cuda" else torch.float32

    mapping = {
        "float32": torch.float32,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
    }
    if dtype not in mapping:
        raise ValueError(f"Unsupported dtype: {dtype}. Use one of {list(mapping.keys())} or auto.")
    # CPU에서 float16/bfloat16은 환경에 따라 느리거나 미지원일 수 있어 float32 권장
    if device.type == "cpu" and mapping[dtype] in (torch.float16, torch.bfloat16):
        return torch.float32
    return mapping[dtype]


def _parse_allowed_hosts(s: str) -> Optional[set]:
    s = (s or "").strip()
    if not s:
        return None
    hosts = set()
    for h in s.split(","):
        h = h.strip().lower()
        if h:
            hosts.add(h)
    return hosts or None


def _load_image_from_url(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    allowed_hosts: Optional[set],
) -> Image.Image:
    # https 권장(서버 운영 시 필수급)
    if not url.startswith("https://"):
        raise ValueError("Only https:// URLs are allowed for safety (server-friendly).")

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    if allowed_hosts is not None and host not in allowed_hosts:
        raise ValueError(f"Host not allowed: {host}. Set ALLOWED_IMAGE_HOSTS env if needed.")

    # 다운로드 (청크 단위로 max_bytes 초과 방지)
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()

        cl = r.headers.get("content-length")
        if cl is not None:
            try:
                content_length = int(cl)
            except (ValueError, TypeError):
                content_length = None
            else:
                if content_length > max_bytes:
                    raise ValueError(f"Image too large (content-length: {content_length} > {max_bytes}).")

        # 청크 단위로 읽어 메모리 보호
        chunks = []
        downloaded = 0
        for chunk in r.iter_content(chunk_size=64 * 1024):
            downloaded += len(chunk)
            if downloaded > max_bytes:
                raise ValueError(f"Image too large (downloaded {downloaded} > {max_bytes}).")
            chunks.append(chunk)
        data = b"".join(chunks)

    img = Image.open(BytesIO(data)).convert("RGB")
    return img


def _load_image_from_path(path: str) -> Image.Image:
    img = Image.open(path).convert("RGB")
    return img


def load_image_any(
    source: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
    allowed_hosts: Optional[set] = _parse_allowed_hosts(DEFAULT_ALLOWED_HOSTS),
) -> Image.Image:
    """
    source:
      - 로컬 파일 경로
      - https URL
    """
    if source.startswith("https://"):
        return _load_image_from_url(source, timeout=timeout, max_bytes=max_bytes, allowed_hosts=allowed_hosts)
    return _load_image_from_path(source)


def l2_normalize(x: torch.Tensor, eps: float = 1e-12) -> torch.Tensor:
    return x / x.norm(p=2, dim=-1, keepdim=True).clamp(min=eps)


@dataclass
class EmbedResult:
    model_id: str
    dims: int
    normalized: bool
    embeddings: List[List[float]]  # batch


class SeolleyeonCLIPEmbedder:
    """
    AutoModel + AutoProcessor로 CLIP 로드 후 이미지 임베딩 추출.
    """

    def __init__(self, model_id: str = DEFAULT_MODEL_ID, device: str = "auto", dtype: str = "auto"):
        self.model_id = model_id
        self.device = _pick_device(device)
        self.dtype = _pick_dtype(dtype, self.device)

        # AutoModel은 model_id 기반으로 적절한 아키텍처(CLIP 등)를 자동 선택해 로드함.  (Auto Classes 문서) :contentReference[oaicite:2]{index=2}
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(model_id)
        self.model.eval()

        # 이동/캐스팅
        self.model.to(self.device)
        if self.device.type == "cuda" and self.dtype in (torch.float16, torch.bfloat16):
            self.model.to(dtype=self.dtype)

        # CLIPModel이면 get_image_features가 존재하는 게 일반적.
        # (혹시 다른 아키텍처가 로드되면 아래 fallback에서 처리)
        self._has_get_image_features = hasattr(self.model, "get_image_features")

    @torch.inference_mode()
    def embed_pil_images(self, images: Sequence[Image.Image], normalize: bool = True) -> EmbedResult:
        if len(images) == 0:
            raise ValueError("No images to embed.")

        # processor(images=..., return_tensors="pt")는 CLIP 문서 예시 그대로. :contentReference[oaicite:3]{index=3}
        inputs = self.processor(images=list(images), return_tensors="pt")
        if "pixel_values" not in inputs:
            raise RuntimeError("Processor did not return pixel_values. Check model/processor compatibility.")

        pixel_values = inputs["pixel_values"].to(self.device)

        # GPU면 autocast로 속도/비용 최적화(선택)
        if self.device.type == "cuda" and self.dtype in (torch.float16, torch.bfloat16):
            with torch.autocast(device_type="cuda", dtype=self.dtype):
                feats = self._image_features(pixel_values)
        else:
            feats = self._image_features(pixel_values)

        feats = feats.float()  # 저장/서빙 안정성을 위해 float32로 변환
        if normalize:
            feats = l2_normalize(feats)

        embeddings = feats.detach().cpu().tolist()
        dims = len(embeddings[0]) if embeddings else int(getattr(self.model.config, "projection_dim", 0))

        return EmbedResult(model_id=self.model_id, dims=dims, normalized=normalize, embeddings=embeddings)

    def _image_features(self, pixel_values: torch.Tensor) -> torch.Tensor:
        # 1) CLIPModel이면 get_image_features 사용(문서 예시). :contentReference[oaicite:4]{index=4}
        if self._has_get_image_features:
            out = self.model.get_image_features(pixel_values=pixel_values)
            # transformers 버전에 따라 BaseModelOutputWithPooling 또는 Tensor 반환
            return self._extract_tensor(out)

        # 2) fallback: forward 결과에 image_embeds가 있으면 사용
        outputs = self.model(pixel_values=pixel_values)
        if hasattr(outputs, "image_embeds") and outputs.image_embeds is not None:
            return self._extract_tensor(outputs.image_embeds)

        raise RuntimeError(
            "Loaded model does not expose get_image_features nor image_embeds. "
            "Try a standard CLIP checkpoint like openai/clip-vit-base-patch32."
        )

    def _extract_tensor(self, out) -> torch.Tensor:
        """BaseModelOutputWithPooling 또는 유사 객체에서 embedding tensor 추출."""
        if isinstance(out, torch.Tensor):
            return out
        if hasattr(out, "pooler_output") and out.pooler_output is not None:
            return out.pooler_output
        if hasattr(out, "last_hidden_state") and out.last_hidden_state is not None:
            return out.last_hidden_state[:, 0, :]  # CLS token
        raise RuntimeError(f"Cannot extract tensor from model output type: {type(out)}")

    def embed_sources(self, sources: Sequence[str], normalize: bool = True) -> EmbedResult:
        images = [load_image_any(s) for s in sources]
        return self.embed_pil_images(images, normalize=normalize)

    def embed_profile_mean(self, sources: Sequence[str], normalize: bool = True) -> Tuple[List[float], int]:
        """
        프로필 사진 여러 장을 임베딩한 뒤 mean pooling으로 1개 벡터로 합침.
        (초기 운영에서 "대표 1장"만 쓰다가 나중에 mean으로 확장하기 좋음)
        """
        res = self.embed_sources(sources, normalize=normalize)
        mat = torch.tensor(res.embeddings, dtype=torch.float32)  # (n, d)
        mean_vec = mat.mean(dim=0, keepdim=False)
        if normalize:
            mean_vec = l2_normalize(mean_vec.unsqueeze(0)).squeeze(0)
        return mean_vec.tolist(), res.dims

    def preference_vector(
        self,
        like_sources: Sequence[str],
        nope_sources: Sequence[str],
        normalize: bool = True,
    ) -> Tuple[List[float], int]:
        """
        pref = normalize(mean(like) - mean(nope))
        설레연의 "AI 취향 학습(30장 like/nope)"에서 바로 쓸 수 있는 형태.
        like_sources 또는 nope_sources 중 하나는 반드시 비어있지 않아야 함.
        """
        if not like_sources and not nope_sources:
            raise ValueError("At least one of like_sources or nope_sources must be non-empty.")

        dims = 0

        if like_sources:
            like_res = self.embed_sources(like_sources, normalize=True)
            like_mat = torch.tensor(like_res.embeddings, dtype=torch.float32)
            like_mean = like_mat.mean(dim=0)
            dims = like_res.dims
        else:
            like_mean = None

        if nope_sources:
            nope_res = self.embed_sources(nope_sources, normalize=True)
            nope_mat = torch.tensor(nope_res.embeddings, dtype=torch.float32)
            nope_mean = nope_mat.mean(dim=0)
            dims = dims or nope_res.dims
        else:
            nope_mean = None

        # like만 있으면 그 벡터 사용, nope만 있으면 반전, 둘 다 있으면 차이
        if like_mean is not None and nope_mean is not None:
            pref = like_mean - nope_mean
        elif like_mean is not None:
            pref = like_mean
        else:
            pref = -nope_mean  # type: ignore[operator]

        if normalize:
            pref = l2_normalize(pref.unsqueeze(0)).squeeze(0)

        return pref.tolist(), dims


def cmd_embed(args: argparse.Namespace) -> int:
    embedder = SeolleyeonCLIPEmbedder(model_id=args.model, device=args.device, dtype=args.dtype)
    res = embedder.embed_sources(args.image, normalize=not args.no_normalize)

    out = {
        "model_id": res.model_id,
        "dims": res.dims,
        "normalized": res.normalized,
        "count": len(res.embeddings),
        "embeddings": res.embeddings,  # (batch, dims)
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_embed_profile_mean(args: argparse.Namespace) -> int:
    embedder = SeolleyeonCLIPEmbedder(model_id=args.model, device=args.device, dtype=args.dtype)
    vec, dims = embedder.embed_profile_mean(args.image, normalize=not args.no_normalize)
    out = {
        "model_id": embedder.model_id,
        "dims": dims,
        "normalized": not args.no_normalize,
        "embedding": vec,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_pref(args: argparse.Namespace) -> int:
    embedder = SeolleyeonCLIPEmbedder(model_id=args.model, device=args.device, dtype=args.dtype)
    vec, dims = embedder.preference_vector(args.like, args.nope)
    out = {
        "model_id": embedder.model_id,
        "dims": dims,
        "normalized": True,
        "pref_vector": vec,
        "like_count": len(args.like),
        "nope_count": len(args.nope),
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Seolleyeon CLIP embedder (AutoModel). Produces normalized image embeddings for recommendation."
    )
    p.add_argument("--model", default=DEFAULT_MODEL_ID, help=f"HF model id (default: {DEFAULT_MODEL_ID})")
    p.add_argument("--device", default="auto", help="auto | cpu | cuda | cuda:0 ... (default: auto)")
    p.add_argument("--dtype", default="auto", help="auto | float32 | float16 | bfloat16 (default: auto)")

    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("embed", help="Embed one or more images (returns batch embeddings).")
    s1.add_argument("--image", nargs="+", required=True, help="Image sources: local path or https URL. (space-separated)")
    s1.add_argument("--no-normalize", action="store_true", help="Disable L2 normalization.")
    s1.set_defaults(func=cmd_embed)

    s2 = sub.add_parser("embed_profile_mean", help="Embed multiple images and mean-pool into one profile vector.")
    s2.add_argument("--image", nargs="+", required=True, help="Image sources: local path or https URL. (space-separated)")
    s2.add_argument("--no-normalize", action="store_true", help="Disable L2 normalization.")
    s2.set_defaults(func=cmd_embed_profile_mean)

    s3 = sub.add_parser("pref", help="Compute preference vector from like/nope images.")
    s3.add_argument("--like", nargs="+", required=True, help="Like image sources (local path or https URL).")
    s3.add_argument("--nope", nargs="+", required=True, help="Nope image sources (local path or https URL).")
    s3.set_defaults(func=cmd_pref)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())