"""Avatar model adapter implementations."""

from .florence2_visual import Florence2VisualRiskAdapter
from .azure_gpt_image_2 import AzureGptImage2Provider

__all__ = ["AzureGptImage2Provider", "Florence2VisualRiskAdapter"]
