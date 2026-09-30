from pathlib import Path

def strip_bom(path):
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
        path.write_bytes(raw)
        print(f"  STRIPPED BOM: {path}")
    else:
        print(f"  OK:           {path}")

for p in Path("data").rglob("*.json"):
    strip_bom(p)
print("\nDone.")
