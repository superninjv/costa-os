"""Costa OS installation configuration schema."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GpuVendor(Enum):
    AMD = "amd"
    NVIDIA = "nvidia"
    INTEL = "intel"
    NONE = "none"


class AiTier(Enum):
    CLOUD_ONLY = 0      # No local models, Claude API only
    VOICE_ONLY = 1      # Whisper STT locally, LLM via API
    VOICE_AND_LLM = 2   # Whisper + local Ollama (3b speed + smartest model for VRAM)
    FULL_WORKSTATION = 3 # Full ML stack, large models, training


class OllamaModelPair:
    """Smart + fast model pair selected by available VRAM.

    The VRAM manager dynamically balances loaded models based on GPU pressure,
    stepping down through fallback models when VRAM is needed by other apps.
    E.g. on 16GB: full=14b+3b, medium=7b+3b, reduced=3b, gaming=nothing.
    """

    # NOTE: qwen3 models peg GPU at 100% idle on AMD RDNA4 + ROCm.
    # Use qwen2.5 for resident models until this is fixed upstream.
    # qwen3 can still be used for on-demand queries (load, run, unload).
    TIERS = [
        # (min_vram_mb, smart_model, fallback_models, fast_model)
        (24000, "qwen2.5:32b", ["qwen2.5:14b", "qwen2.5:7b", "qwen2.5:3b"], "qwen2.5:3b"),
        (12000, "qwen2.5:14b", ["qwen2.5:7b", "qwen2.5:3b"], "qwen2.5:3b"),
        (8000, "qwen2.5:7b", ["qwen2.5:3b"], "qwen2.5:3b"),
        (4000, "qwen2.5:3b", ["qwen2.5:1.5b"], "qwen2.5:1.5b"),
        (2000, "qwen2.5:1.5b", [], None),
    ]

    def __init__(self, vram_mb: int):
        self.smart_model: Optional[str] = None
        self.fallback_models: list[str] = []
        self.fast_model: Optional[str] = None
        for min_vram, smart, fallbacks, fast in self.TIERS:
            if vram_mb >= min_vram:
                self.smart_model = smart
                self.fallback_models = fallbacks
                self.fast_model = fast
                break

    @property
    def all_models(self) -> list[str]:
        """All models to pull during install (smart + fallbacks + fast)."""
        models = []
        if self.smart_model:
            models.append(self.smart_model)
        models.extend(self.fallback_models)
        if self.fast_model and self.fast_model not in models:
            models.append(self.fast_model)
        return models


class WhisperBackend(Enum):
    CPU = "cpu"
    VULKAN = "vulkan"
    ROCM = "rocm"
    CUDA = "cuda"


@dataclass
class HardwareProfile:
    gpu_vendor: GpuVendor = GpuVendor.NONE
    gpu_name: str = ""
    gpu_vram_mb: int = 0
    ram_mb: int = 0
    cpu_cores: int = 0
    cpu_name: str = ""

    @property
    def max_ai_tier(self) -> AiTier:
        """Determine the maximum AI tier this hardware can support."""
        if self.gpu_vram_mb >= 12000:
            return AiTier.FULL_WORKSTATION
        elif self.gpu_vram_mb >= 6000:
            return AiTier.VOICE_AND_LLM
        elif self.gpu_vram_mb >= 2000 or self.ram_mb >= 16000:
            return AiTier.VOICE_ONLY
        else:
            return AiTier.CLOUD_ONLY

    @property
    def recommended_models(self) -> "OllamaModelPair":
        """Recommend smart + fast model pair for this hardware."""
        return OllamaModelPair(self.gpu_vram_mb)

    @property
    def recommended_ollama_model(self) -> Optional[str]:
        """Recommend the best local model for this hardware (legacy compat)."""
        return self.recommended_models.smart_model

    @property
    def whisper_backend(self) -> WhisperBackend:
        if self.gpu_vendor == GpuVendor.AMD and self.gpu_vram_mb >= 2000:
            return WhisperBackend.VULKAN  # ROCm whisper has issues on RDNA4
        elif self.gpu_vendor == GpuVendor.NVIDIA and self.gpu_vram_mb >= 2000:
            return WhisperBackend.CUDA
        elif self.gpu_vendor == GpuVendor.INTEL and self.gpu_vram_mb >= 2000:
            return WhisperBackend.VULKAN
        return WhisperBackend.CPU

    @property
    def whisper_model(self) -> str:
        """Recommend whisper model based on hardware."""
        if self.gpu_vram_mb >= 4000:
            return "small.en"
        elif self.gpu_vram_mb >= 2000:
            return "base.en"
        return "tiny.en"


@dataclass
class MonitorConfig:
    name: str = ""           # e.g. "DP-1"
    resolution: str = ""     # e.g. "2560x1440"
    refresh_rate: int = 60
    position: str = ""       # e.g. "720x0"
    scale: float = 1.0
    transform: int = 0       # 0=normal, 1=90deg, etc.
    primary: bool = False


@dataclass
class CostaConfig:
    """Full installation configuration."""

    # User
    username: str = ""
    hostname: str = "costa"
    timezone: str = "America/New_York"
    locale: str = "en_US.UTF-8"

    # Hardware (auto-detected)
    hardware: HardwareProfile = field(default_factory=HardwareProfile)
    monitors: list[MonitorConfig] = field(default_factory=list)

    # AI configuration
    ai_tier: AiTier = AiTier.VOICE_AND_LLM
    anthropic_api_key: str = ""
    ollama_smart_model: str = "qwen2.5:14b"  # primary local brain
    ollama_fast_model: str = "qwen2.5:3b"   # summaries + speed-critical
    whisper_model: str = "base.en"

    # Package selections
    install_dev_tools: bool = True
    install_creative: bool = False
    install_gaming: bool = False

    # Audio
    has_microphone: bool = True
    mic_device: str = ""
    speaker_device: str = ""

    # Theme
    theme: str = "costa"  # future: allow custom themes

    def validate(self) -> list[str]:
        """Return list of validation errors."""
        errors = []
        if not self.username:
            errors.append("Username is required")
        if self.ai_tier.value > self.hardware.max_ai_tier.value:
            errors.append(
                f"AI tier {self.ai_tier.name} exceeds hardware capability "
                f"(max: {self.hardware.max_ai_tier.name})"
            )
        if self.ai_tier != AiTier.CLOUD_ONLY and not self.anthropic_api_key:
            # Cloud-only doesn't need a key if user has no API access
            pass  # API key is optional, local models work without it
        return errors
