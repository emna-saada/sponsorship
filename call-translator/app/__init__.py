"""Live Call Translator.

On Windows, CTranslate2 needs NVIDIA's cuBLAS and cuDNN DLLs to use the GPU.
start.bat installs them with pip (nvidia-cublas-cu12, nvidia-cudnn-cu12) when an
NVIDIA card is present; this makes their folders visible before anything
imports ctranslate2.
"""

import os
import sys
from pathlib import Path


def _add_nvidia_dll_dirs() -> None:
    if sys.platform != "win32":
        return
    roots = {Path(sys.prefix) / "Lib" / "site-packages"}
    roots.update(Path(p) for p in sys.path if p.endswith("site-packages"))
    for root in roots:
        for bin_dir in (root / "nvidia").glob("*/bin"):
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(str(bin_dir))
            except OSError:
                pass


_add_nvidia_dll_dirs()
