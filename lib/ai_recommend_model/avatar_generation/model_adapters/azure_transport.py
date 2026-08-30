from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .azure_contracts import (
    AzureConfigurationError,
    AzureGptImage2Config,
    AzureImageEditRequest,
    AzureProviderResponse,
    AzureTransportError,
)


class AzureHttpImageTransport:
    """Process-level HTTP client for the Azure image edit endpoint."""

    def __init__(self, config: AzureGptImage2Config) -> None:
        if not config.endpoint or not config.deployment or not config.api_version or not config.api_key:
            raise AzureConfigurationError()
        try:
            import httpx
        except Exception as exc:  # pragma: no cover - exercised only in runtime image
            raise AzureConfigurationError("azure_http_client_unavailable") from exc
        self._config = config
        self._httpx = httpx
        self._client = httpx.Client(timeout=config.request_timeout_seconds)

    def send(self, request: AzureImageEditRequest) -> AzureProviderResponse:
        if self._config.api_style == "foundry_v1":
            url = (
                f"{self._config.endpoint.rstrip('/')}/openai/v1/images/edits"
                f"?api-version={quote(request.api_version, safe='')}"
            )
            image_field = "image"
        else:
            url = (
                f"{self._config.endpoint.rstrip('/')}/openai/deployments/"
                f"{quote(request.deployment, safe='')}/images/edits"
                f"?api-version={quote(request.api_version, safe='')}"
            )
            image_field = "image[]"
        fields: dict[str, str] = {
            "prompt": request.prompt,
            "n": "1",
            "model": request.deployment,
        }
        if request.quality:
            fields["quality"] = request.quality
        if request.size:
            fields["size"] = request.size
        try:
            response = self._client.post(
                url,
                headers={"api-key": self._config.api_key},
                data=fields,
                files={
                    image_field: (
                        "source.jpg",
                        request.source_image_bytes,
                        request.source_content_type,
                    )
                },
            )
        except self._httpx.TimeoutException as exc:
            raise AzureTransportError("azure_request_timeout", request_sent=True) from exc
        except self._httpx.NetworkError as exc:
            raise AzureTransportError("azure_connect_error", request_sent=False) from exc
        except Exception as exc:
            raise AzureTransportError("azure_transport_error", request_sent=False) from exc

        payload: dict[str, Any]
        try:
            raw = response.json()
            payload = dict(raw) if isinstance(raw, dict) else {}
        except Exception:
            payload = {}
        return AzureProviderResponse(
            status_code=int(response.status_code),
            headers={str(key): str(value) for key, value in response.headers.items()},
            payload=payload,
        )

    def close(self) -> None:
        self._client.close()


__all__ = ["AzureHttpImageTransport"]
