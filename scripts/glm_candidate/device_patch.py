"""Build-time H100 adaptation; safe to verify/apply repeatedly without importing CUDA."""
from pathlib import Path

OLD = "torch.cuda.set_device(0)"
NEW = 'torch.cuda.set_device(int(os.environ.get("TF_GLM_DEVICE", "0")))'


def adapt(text: str) -> str:
    if text.count(NEW) == 1 and OLD not in text:
        return text
    if text.count(OLD) != 1 or NEW in text:
        raise ValueError("unexpected GLM device-selection source; refusing an ambiguous patch")
    if "import os" not in text:
        raise ValueError("GLM engine must import os before using the device selector")
    return text.replace(OLD, NEW, 1)


if __name__ == "__main__":
    import importlib.util

    spec = importlib.util.find_spec("tensorfold")
    root = Path(next(iter(spec.submodule_search_locations)))
    engine = root / "families/glm5_next/cuda/engine.py"
    text = adapt(engine.read_text())
    compile(text, str(engine), "exec")
    engine.write_text(text)
    print("H100 device selection installed and syntax checked")
