"""Auto-detect hardware for Costa OS installation."""

import subprocess
import re
from config_schema import HardwareProfile, GpuVendor, MonitorConfig


def detect_gpu() -> tuple[GpuVendor, str, int]:
    """Detect GPU vendor, name, and VRAM in MB."""
    try:
        lspci = subprocess.check_output(
            ["lspci", "-v"], text=True, stderr=subprocess.DEVNULL
        )

        # AMD
        amd_match = re.search(r"VGA.*AMD.*?\[(.+?)\]", lspci)
        if amd_match:
            name = amd_match.group(1)
            vram = _get_amd_vram()
            return GpuVendor.AMD, name, vram

        # NVIDIA
        nvidia_match = re.search(r"VGA.*NVIDIA.*?\[(.+?)\]", lspci)
        if nvidia_match:
            name = nvidia_match.group(1)
            vram = _get_nvidia_vram()
            return GpuVendor.NVIDIA, name, vram

        # Intel
        intel_match = re.search(r"VGA.*Intel.*?(\w[\w\s]+)", lspci)
        if intel_match:
            name = intel_match.group(1).strip()
            return GpuVendor.INTEL, name, 2048  # Approximate

    except Exception:
        pass

    return GpuVendor.NONE, "Unknown", 0


def _get_amd_vram() -> int:
    """Get AMD GPU VRAM in MB."""
    try:
        total = open("/sys/class/drm/card1/device/mem_info_vram_total").read().strip()
        return int(total) // (1024 * 1024)
    except Exception:
        try:
            total = open("/sys/class/drm/card0/device/mem_info_vram_total").read().strip()
            return int(total) // (1024 * 1024)
        except Exception:
            return 0


def _get_nvidia_vram() -> int:
    """Get NVIDIA GPU VRAM in MB."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            text=True,
        )
        return int(out.strip())
    except Exception:
        return 0


def detect_cpu() -> tuple[str, int]:
    """Detect CPU name and core count."""
    try:
        cpuinfo = open("/proc/cpuinfo").read()
        name = re.search(r"model name\s*:\s*(.+)", cpuinfo)
        cores = cpuinfo.count("processor\t")
        return name.group(1).strip() if name else "Unknown", cores
    except Exception:
        return "Unknown", 1


def detect_ram() -> int:
    """Detect RAM in MB."""
    try:
        meminfo = open("/proc/meminfo").read()
        match = re.search(r"MemTotal:\s*(\d+)", meminfo)
        return int(match.group(1)) // 1024 if match else 0
    except Exception:
        return 0


def detect_monitors() -> list[MonitorConfig]:
    """Detect connected monitors via Hyprland or wlr-randr."""
    monitors = []
    try:
        import json
        out = subprocess.check_output(
            ["hyprctl", "monitors", "-j"], text=True, stderr=subprocess.DEVNULL
        )
        for m in json.loads(out):
            monitors.append(MonitorConfig(
                name=m["name"],
                resolution=f"{m['width']}x{m['height']}",
                refresh_rate=int(m.get("refreshRate", 60)),
                position=f"{m['x']}x{m['y']}",
                scale=m.get("scale", 1.0),
                transform=m.get("transform", 0),
                primary=(m.get("focused", False)),
            ))
    except Exception:
        pass
    return monitors


def detect_audio_devices() -> tuple[list[str], list[str]]:
    """Detect audio sources (mics) and sinks (speakers)."""
    sources, sinks = [], []
    try:
        out = subprocess.check_output(["wpctl", "status"], text=True, stderr=subprocess.DEVNULL)
        in_sources = False
        in_sinks = False
        for line in out.split("\n"):
            if "Sources:" in line:
                in_sources = True
                in_sinks = False
            elif "Sinks:" in line:
                in_sinks = True
                in_sources = False
            elif "Filters:" in line or "Streams:" in line:
                in_sources = False
                in_sinks = False
            elif in_sources and "." in line:
                name = re.sub(r"[│├└─\s*]+\d+\.\s*", "", line).strip()
                if name and "[vol:" in name:
                    name = name.split("[vol:")[0].strip()
                    sources.append(name)
            elif in_sinks and "." in line:
                name = re.sub(r"[│├└─\s*]+\d+\.\s*", "", line).strip()
                if name and "[vol:" in name:
                    name = name.split("[vol:")[0].strip()
                    sinks.append(name)
    except Exception:
        pass
    return sources, sinks


def detect_all() -> HardwareProfile:
    """Run full hardware detection."""
    gpu_vendor, gpu_name, gpu_vram = detect_gpu()
    cpu_name, cpu_cores = detect_cpu()
    ram = detect_ram()

    return HardwareProfile(
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        gpu_vram_mb=gpu_vram,
        ram_mb=ram,
        cpu_cores=cpu_cores,
        cpu_name=cpu_name,
    )


if __name__ == "__main__":
    hw = detect_all()
    monitors = detect_monitors()
    sources, sinks = detect_audio_devices()

    print(f"CPU: {hw.cpu_name} ({hw.cpu_cores} cores)")
    print(f"RAM: {hw.ram_mb} MB")
    print(f"GPU: {hw.gpu_vendor.value} — {hw.gpu_name} ({hw.gpu_vram_mb} MB VRAM)")
    print(f"Max AI tier: {hw.max_ai_tier.name}")
    models = hw.recommended_models
    print(f"Recommended models: {models.smart_model} (smart) + {models.fast_model} (fast)")
    print(f"Whisper backend: {hw.whisper_backend.value}")
    print(f"Whisper model: {hw.whisper_model}")
    print(f"Monitors: {len(monitors)}")
    for m in monitors:
        print(f"  {m.name}: {m.resolution}@{m.refresh_rate}Hz {'[PRIMARY]' if m.primary else ''}")
    print(f"Mics: {sources}")
    print(f"Speakers: {sinks}")
