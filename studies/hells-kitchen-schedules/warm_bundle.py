"""Extract and verify the Minecraft server's immutable JVM artifacts once."""
import argparse
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archive", type=Path)
    args = ap.parse_args()
    out = args.archive / "bundle"
    with ZipFile(args.archive / "server.jar") as bundled:
        count = 0
        for category in ("libraries", "versions"):
            lines = bundled.read(f"META-INF/{category}.list").decode().splitlines()
            for line in lines:
                checksum, _, relative = line.split()
                destination = out / category / relative
                if not destination.resolve().is_relative_to(out.resolve()):
                    raise ValueError("Minecraft bundle contains a path outside its cache")
                contents = bundled.read(f"META-INF/{category}/{relative}")
                if sha256(contents).hexdigest() != checksum:
                    raise ValueError(f"Minecraft bundle hash mismatch for {relative}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                temp = destination.with_suffix(destination.suffix + ".tmp")
                temp.write_bytes(contents)
                temp.replace(destination)
                count += 1
    print(f"Verified {count} packaged Minecraft artifacts.")


if __name__ == "__main__":
    main()
