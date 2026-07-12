# Test34 - pathlib.Path
from pathlib import Path

p = Path(".")
print(p)

p2 = Path("/usr/local")
print(p2)

exists = p.exists()
print(exists)

name = p.name
print(name)

parent = p.parent
print(parent)

resolved = p.resolve()
print(len(resolved) > 0)

p3 = Path("pycc_path_test.txt")
p3.write_text("Hello pathlib!\n")
content = p3.read_text()
print(content)
p3.unlink()
