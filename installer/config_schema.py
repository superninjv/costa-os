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
    VOICE_AND_LLM = 2   # Whisper + local Ollama (7b or smaller)
    FULL_WORKSTATION = 3 # Full ML stack, large models, training


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
    def recommended_ollama_model(self) -> Optional[str]:
        """Recommend the best local model for this hardware."""
        if self.gpu_vram_mb >= 12000:
            return "qwen2.5:7b"
        elif self.gpu_vram_mb >= 6000:
            return "qwen2.5:3b"
        elif self.gpu_vram_mb >= 3000:
            return "qwen2.5:1.5b"
        return None

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
    ollama_model: str = "qwen2.5:3b"
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
