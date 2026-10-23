"""Build a small, explicit, reproducible plugin archive with no local state."""
import hashlib
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ("main.py", "limiter.py", "metadata.yaml", "_conf_schema.json",
         "logo.png", "README.md", "CHANGELOG.md", "LICENSE")


def build():
    version = re.search(r"^version: ([0-9]+\.[0-9]+\.[0-9]+)$", (ROOT/"metadata.yaml").read_text(encoding="utf-8-sig"), re.M).group(1)
    out = ROOT/"dist"
    out.mkdir(exist_ok=True)
    archive = out/f"astrbot_plugin_anti_laowu-v{version}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            data = (ROOT/name).read_bytes()
            if name.endswith((".py", ".md", ".yaml", ".json")):
                data = data.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
            info = zipfile.ZipInfo(f"astrbot_plugin_anti_laowu/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    assert archive.stat().st_size < 16*1024*1024, "Marketplace ZIP exceeds 16MiB"
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(FILES)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out/"SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"{archive.name}: {archive.stat().st_size} bytes\nSHA256 {digest}")


if __name__ == "__main__":
    build()
