"""
PyCCLD.py
PyCC Linker. Assembles .asm to .o, links .o to binary.
Tries: nasm/gas/zig-cc for assembly, zig/clang/gcc for linking.
Auto-links PyCCRuntime when present or requested.
"""
import os
import platform
import shutil
import subprocess
import sys


def _which(name):
    return shutil.which(name)


def _find_nasm():
    found = _which("nasm")
    if found:
        return found
    candidates = {
        "Windows": [
            r"C:\Program Files\NASM\nasm.exe",
            r"C:\nasm\nasm.exe",
            os.path.join(os.path.dirname(__file__), "nasm.exe"),
        ],
        "Darwin":  ["/usr/local/bin/nasm", "/opt/homebrew/bin/nasm"],
        "Linux":   ["/usr/bin/nasm", "/usr/local/bin/nasm"],
    }.get(platform.system(), [])
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _find_zig():
    found = _which("zig")
    if found:
        return found
    candidates = {
        "Windows": [r"C:\zig\zig.exe", os.path.join(os.path.dirname(__file__), "..", "zig.exe")],
        "Darwin":  ["/usr/local/bin/zig", "/opt/homebrew/bin/zig"],
        "Linux":   ["/usr/bin/zig", "/usr/local/bin/zig", os.path.expanduser("~/zig/zig")],
    }.get(platform.system(), [])
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _find_linker():
    for name in ("zig", "clang", "gcc", "cc"):
        found = _which(name)
        if found:
            return found
    return None


def _find_gas():
    return _which("as") or _which("gas")


def _zig_triple(arch, os_name):
    arch_map = {
        "x86_64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64",
        "x86": "x86", "i686": "x86", "riscv64": "riscv64",
    }
    os_map = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}
    a = arch_map.get(arch, arch)
    o = os_map.get(os_name, os_name.lower())
    abi = "gnu" if o == "linux" else ""
    return f"{a}-{o}-{abi}" if abi else f"{a}-{o}"


def _find_runtime_lib(arch, os_name):
    base = os.path.join(os.path.dirname(__file__), "..", "runtime", "lib")
    if os_name == "Windows":
        names = [f"PyCCRuntime_{arch}.lib", f"PyCCRuntime_{arch}.dll"]
    elif os_name == "Darwin":
        names = [f"libPyCCRuntime_{arch}.a", f"libPyCCRuntime_{arch}.dylib"]
    else:
        names = [f"libPyCCRuntime_{arch}.a", f"libPyCCRuntime_{arch}.so"]
    for n in names:
        p = os.path.join(base, n)
        if os.path.exists(p):
            return p
    return None


def pick_asm_syntax(arch):
    """
    Decide, up front, which assembler + syntax we'll actually use for this
    build, so the backend can generate matching text on the first try
    instead of generating NASM syntax that GAS then fails to parse.

    Only x86_64 has two competing syntaxes (NASM vs GAS-Intel) in this
    codebase; other arches only have one backend/assembler pairing.
    Returns "nasm", "gas", or None (meaning: no assembler at all, or a
    non-x86_64 arch where the choice doesn't apply).
    """
    if arch != "x86_64":
        return None
    if _find_nasm():
        return "nasm"
    if _find_gas():
        return "gas"
    # No native assembler; PyCCLD.assemble() will still try zig-cc, which
    # can assemble NASM-style text itself isn't guaranteed, but zig cc -x
    # assembler expects GAS/Intel-with-.intel_syntax style too, so prefer
    # gas-flavored output if we're going to fall through to it.
    return "gas"


def assemble(asm_file, obj_file, arch, os_name, asm_syntax=None):
    """
    Assemble asm_file (already generated in the syntax matching
    asm_syntax) into obj_file. asm_syntax should match whatever the
    IR backend actually emitted -- see IRCompiler.compile / pick_asm_syntax.
    Falls back through nasm -> gas -> zig cc, but only tries the
    assembler(s) compatible with the syntax the file was written in.
    Returns True on success.
    """
    if arch == "x86_64" and asm_syntax in (None, "nasm"):
        nasm = _find_nasm()
        if nasm:
            fmt = {"Windows": "win64", "Darwin": "macho64"}.get(os_name, "elf64")
            r = subprocess.run([nasm, "-f", fmt, asm_file, "-o", obj_file],
                               capture_output=True, text=True)
            if r.returncode == 0:
                return True
            print(f"\x1b[33mNASM: {r.stderr.strip()}\x1b[0m", file=sys.stderr)

    if arch != "x86_64" or asm_syntax in (None, "gas"):
        gas = _find_gas()
        if gas:
            r = subprocess.run([gas, asm_file, "-o", obj_file],
                               capture_output=True, text=True)
            if r.returncode == 0:
                return True
            print(f"\x1b[33mGAS: {r.stderr.strip()}\x1b[0m", file=sys.stderr)

    zig = _find_zig()
    if zig:
        triple = _zig_triple(arch, os_name)
        r = subprocess.run([zig, "cc", "-target", triple, "-c", asm_file, "-o", obj_file],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return True
        print(f"\x1b[33mZig-CC: {r.stderr.strip()}\x1b[0m", file=sys.stderr)

    print("\x1b[31mNo assembler found. Install nasm, gas, or zig.\x1b[0m", file=sys.stderr)
    return False


def link(obj_files, output, arch, os_name, args):
    """
    Link object files to binary.
    Auto-links PyCCRuntime if -runtime or if runtime lib exists.
    """
    linker = _find_linker()
    if not linker:
        print("\x1b[31mNo linker found. Install zig, clang, or gcc.\x1b[0m", file=sys.stderr)
        return False

    if linker.endswith("zig") or os.path.basename(linker) == "zig":
        cmd = [linker, "cc", "-w"] + list(obj_files) + ["-o", output]
        triple = _zig_triple(arch, os_name)
        cmd += ["-target", triple]
    else:
        cmd = [linker, "-w"] + list(obj_files) + ["-o", output]

    # The generated code uses absolute (non-RIP-relative) addressing for
    # globals/strings -- fine for a normal non-PIE executable, but modern
    # gcc/clang default to PIE on Linux, which requires position-independent
    # addressing and rejects these relocations at link time
    # ("relocation R_X86_64_32S against `.data' can not be used when making
    # a PIE object"). -no-pie matches what the codegen actually emits.
    if os_name == "Linux" and "zig" not in os.path.basename(linker):
        cmd.append("-no-pie")

    if args.get("static"):
        cmd.append("-static")

    for d in args.get("pyl", []):
        cmd += ["-L", d]

    runtime_lib = None
    if args.get("runtime"):
        runtime_lib = _find_runtime_lib(arch, os_name)
        if not runtime_lib:
            print("\x1b[33mWarning: -runtime set but PyCCRuntime not built. Run: python runtime/BuildPyCCRuntime.py\x1b[0m",
                  file=sys.stderr)
    else:
        runtime_lib = _find_runtime_lib(arch, os_name)

    if runtime_lib:
        cmd.append(runtime_lib)

    cmd.append("-lm")
    if os_name == "Linux":
        cmd += ["-lpthread", "-ldl"]
    elif os_name == "Windows":
        cmd += ["-lws2_32", "-ladvapi32", "-luser32"]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"\x1b[31mLinker error:\x1b[0m\n{r.stderr}", file=sys.stderr)
            return False
        return True
    except KeyboardInterrupt:
        print("\x1b[33mLinking cancelled.\x1b[0m", file=sys.stderr)
        return False


def assemble_and_link(asm_src, output_name, args, arch=None, os_name=None, asm_syntax=None):
    from PyCCIR import detect_host_arch, detect_host_os
    arch    = arch    or detect_host_arch()
    os_name = os_name or detect_host_os()

    base     = output_name.replace(".exe", "").replace(".out", "")
    asm_file = base + ".asm"
    obj_file = base + ".o"

    with open(asm_file, "w") as f:
        f.write(asm_src)

    ok = assemble(asm_file, obj_file, arch, os_name, asm_syntax=asm_syntax)
    if not ok:
        return

    ok = link([obj_file], output_name, arch, os_name, args)
    if ok:
        print(f"\x1b[33mCompiled -> {output_name}\x1b[0m")

    if args.get("noobj") or args.get("nobj"):
        for f in (asm_file, obj_file):
            try:
                os.remove(f)
            except FileNotFoundError:
                pass

    if args.get("npdb") and os_name == "Windows":
        pdb = output_name.replace(".exe", ".pdb")
        try:
            os.remove(pdb)
        except FileNotFoundError:
            pass
