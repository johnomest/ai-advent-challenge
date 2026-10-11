"""Windows llama.cpp lifecycle and measured resource samples for Day 29."""

import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".local-archive/models-cleanup-20261011-3UZ0qB/llama-b11514-no-prefetch-cuda13.0/llama-server.exe"
MODELS = {
    "Q8_0": ROOT / "models/Qwen3.5-9B-Q8_0/Qwen_Qwen3.5-9B-Q8_0.gguf",
    "Q4_K_M-requant": ROOT / "models/Qwen3.5-9B-Q4_K_M-requant/Qwen3.5-9B-Q4_K_M-requant.gguf",
}


def processes():
    if sys.platform != "win32":
        raise RuntimeError("Use the Windows .venv/Scripts/python.exe for runtime measurements.")
    command = "Get-CimInstance Win32_Process -Filter \"Name='llama-server.exe'\" | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
    output = subprocess.check_output(["powershell.exe", "-NoProfile", "-Command", command],
                                     encoding="utf-8", timeout=20).strip()
    data = json.loads(output) if output else []
    return data if isinstance(data, list) else [data]


def split_command(command):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not pointer:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [pointer[i] for i in range(count.value)]
    finally:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))


def set_option(arguments, name, value):
    result = list(arguments)
    position = result.index(name)
    result[position + 1] = str(value)
    return result


class Server:
    """Restart only the verified project server, then restore its exact arguments."""

    def __init__(self, request, folder):
        self.request = request
        self.folder = folder
        matches = [item for item in processes() if item.get("ExecutablePath") and Path(item["ExecutablePath"]) == RUNTIME]
        matches = [(item, split_command(item["CommandLine"])) for item in matches]
        matches = [(item, argv) for item, argv in matches
                   if "--port" in argv and argv[argv.index("--port") + 1:argv.index("--port") + 2] == ["8080"]]
        if len(matches) != 1:
            raise RuntimeError("Start the project Qwen server on port 8080 before benchmarking.")
        process, self.original = matches[0]
        self.pid = process["ProcessId"]
        props = request("http://127.0.0.1:8080", "/props")
        if (Path(props["model_path"]) not in MODELS.values() or props["total_slots"] != 1
                or "--host" not in self.original or self.original[self.original.index("--host") + 1] != "127.0.0.1"):
            raise RuntimeError("Benchmark requires the known local Qwen runtime with one slot.")
        self.current = self.original
        self.child = None

    def stop(self):
        if not self.pid:
            return
        current = next((item for item in processes() if item["ProcessId"] == self.pid), None)
        if current:
            if Path(current["ExecutablePath"]) != RUNTIME:
                raise RuntimeError("Server PID no longer belongs to the project runtime; refusing to stop it.")
            subprocess.run(["taskkill.exe", "/PID", str(self.pid), "/F"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
        if self.child:
            self.child.wait(timeout=20)
        self.pid = None

    def start(self, arguments):
        self.stop()
        log_path = self.folder / f"server-{int(time.time() * 1000)}.log"
        with log_path.open("wb") as log:
            self.child = subprocess.Popen(arguments, stdout=log, stderr=subprocess.STDOUT,
                                          creationflags=subprocess.CREATE_NO_WINDOW)
        self.pid = self.child.pid
        self.current = arguments
        started = time.perf_counter()
        while time.perf_counter() - started < 120:
            if self.child.poll() is not None:
                raise RuntimeError(f"llama.cpp failed to start; inspect {log_path}")
            try:
                self.request("http://127.0.0.1:8080", "/health")
                return round(time.perf_counter() - started, 3)
            except RuntimeError:
                time.sleep(.5)
        raise RuntimeError(f"llama.cpp startup timeout; inspect {log_path}")

    def configure(self, quantization, context, force=False):
        if not MODELS[quantization].is_file():
            raise RuntimeError(f"Model is missing: {MODELS[quantization]}")
        arguments = set_option(self.original, "--model", MODELS[quantization])
        arguments = set_option(arguments, "--alias", f"Qwen3.5-9B-{quantization}")
        arguments = set_option(arguments, "--ctx-size", context)
        return self.start(arguments) if force or arguments != self.current else 0

    def restore(self):
        if self.current != self.original or not self.pid:
            self.start(self.original)


def memory(pid):
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x410, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"working_set_mib": round(counters.WorkingSetSize / 1048576, 1),
                "private_mib": round(counters.PrivateUsage / 1048576, 1)}
    finally:
        kernel.CloseHandle(handle)


class Monitor:
    def __init__(self, pid):
        self.pid = pid
        self.samples = []
        self.finished = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        while not self.finished.is_set():
            try:
                gpu = subprocess.check_output([
                    "nvidia-smi.exe", "--query-gpu=memory.used,utilization.gpu,power.draw",
                    "--format=csv,noheader,nounits"], encoding="utf-8", timeout=5).splitlines()[0]
                used, utilization, power = (float(item.strip()) for item in gpu.split(","))
                self.samples.append({**memory(self.pid), "gpu_used_mib": used,
                                     "gpu_utilization_percent": utilization, "gpu_power_w": power})
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                self.samples.append({"error": str(error)})
            self.finished.wait(1)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *unused):
        self.finished.set()
        self.thread.join(timeout=7)

    def summary(self):
        valid = [sample for sample in self.samples if "error" not in sample]
        return {"samples": len(valid), "errors": len(self.samples) - len(valid),
                "peak_working_set_mib": max((s["working_set_mib"] for s in valid), default=None),
                "peak_private_mib": max((s["private_mib"] for s in valid), default=None),
                "peak_gpu_used_mib": max((s["gpu_used_mib"] for s in valid), default=None),
                "gpu_scope": "Whole GPU, including embeddings and desktop; not isolated model VRAM."}
