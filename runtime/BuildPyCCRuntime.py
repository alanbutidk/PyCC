"""BuildPyCCRuntime.py - Builds PyCCRuntime.dll/.so for all target architectures.
Usage:
  python BuildPyCCRuntime.py                  # build for host arch
  python BuildPyCCRuntime.py --arch x86_64    # cross-compile x86_64
  python BuildPyCCRuntime.py --arch aarch64   # cross-compile ARM64
  python BuildPyCCRuntime.py --arch x86       # cross-compile 32-bit x86
  python BuildPyCCRuntime.py --all            # build all supported arches
  python BuildPyCCRuntime.py --clean          # remove build artifacts
"""
import sys
import os; os.system("")
import platform
import subprocess
import shutil
import argparse

RUNTIME_DIR  = os.path.dirname(os.path.abspath(__file__))
SRC          = os.path.join(RUNTIME_DIR, "PyCCRuntime.c")
HEADER       = os.path.join(RUNTIME_DIR, "PyCCRuntime.h")
OUT_DIR      = os.path.join(RUNTIME_DIR, "lib")

HOST_OS   = platform.system()   # Windows / Linux / Darwin
HOST_ARCH = platform.machine()  # x86_64 / AMD64 / aarch64 / arm64

SUPPORTED_ARCHES = ["x86_64", "aarch64", "x86", "riscv64", "armv7"]

def _find_zig():
    zig = shutil.which("zig")
    if zig:
        return zig
    candidates = []
    if HOST_OS == "Windows":
        candidates = [
            r"C:\zig\zig.exe",
            os.path.join(os.path.dirname(sys.executable), "zig.exe"),
        ]
    else:
        candidates = ["/usr/local/bin/zig", "/usr/bin/zig", os.path.expanduser("~/zig/zig")]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def _zig_target(arch, os_name):
    """Map (arch, os) to Zig target triple.
    Always use gnu ABI — zig ships its own libc for all gnu targets
    so no Windows SDK, no system headers needed. Cross-compile just works.
    """
    arch_map = {
        "x86_64":  "x86_64",
        "aarch64": "aarch64",
        "arm64":   "aarch64",
        "x86":     "x86",
        "i686":    "x86",
        "riscv64": "riscv64",
        "armv7":   "arm",
    }
    os_map = {
        "Windows": "windows",
        "Linux":   "linux",
        "Darwin":  "macos",
    }
    a = arch_map.get(arch, arch)
    o = os_map.get(os_name, os_name.lower())

    # gnu ABI everywhere — zig bundles musl/mingw so no host SDK required
    if o == "windows":
        abi = "gnu"       # mingw, not msvc — avoids LibCStdLibHeaderNotFound
    elif o == "linux":
        abi = "gnu"
    elif o == "macos":
        abi = None        # macos doesn't use an ABI suffix
    else:
        abi = "gnu"

    if abi:
        return f"{a}-{o}-{abi}"
    return f"{a}-{o}"

def _output_name(arch, os_name):
    if os_name == "Windows":
        return f"PyCCRuntime_{arch}.dll"
    elif os_name == "Darwin":
        return f"libPyCCRuntime_{arch}.dylib"
    else:
        return f"libPyCCRuntime_{arch}.so"

def _find_cc():
    """Fallback native compiler for host-only builds when zig isn't installed.
    Cross-compiling to a different arch/OS still requires zig (for the bundled
    libc + cross target support); this is only used for `build_host()`.
    """
    for name in ("cc", "gcc", "clang"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _cc_output_names(out_file):
    """Map the requested output filename to a native-cc-buildable
    (shared_ext, static_ext) pair for the *host* platform only."""
    static_name = (out_file
                   .replace(".dll",   ".a")
                   .replace(".so",    ".a")
                   .replace(".dylib", ".a"))
    return static_name


def build_with_native_cc(cc, verbose=False, cpython=False):
    """Host-only build path used when zig is not available. Straightforward
    native gcc/clang compile -- no cross-compilation, no bundled libc, just
    whatever the local toolchain already has (this environment's PyCCRuntime.c
    compiles clean under plain gcc with no changes needed).
    """
    os.makedirs(OUT_DIR, exist_ok=True)
    arch = HOST_ARCH.lower()
    if arch == "amd64": arch = "x86_64"
    if arch == "arm64": arch = "aarch64"
    out_file = os.path.join(OUT_DIR, _output_name(arch, HOST_OS))

    print(f"\x1b[36mBuilding PyCCRuntime for host ({arch}-{HOST_OS}) via {os.path.basename(cc)} "
          f"[zig not found -- host-only build, no cross-compilation]{'  +CPython' if cpython else ''}...\x1b[0m")

    py_cflags = []
    py_lflags = []
    if cpython:
        import sysconfig
        inc    = sysconfig.get_path("include")
        lib    = sysconfig.get_config_var("LIBDIR") or ""
        pyver  = sysconfig.get_config_var("LDVERSION") or sysconfig.get_config_var("py_version_short")
        if inc:    py_cflags += [f"-I{inc}"]
        if lib:    py_lflags += [f"-L{lib}"]
        if pyver:  py_lflags += [f"-lpython{pyver}"]
        py_cflags += ["-DPYCC_CPYTHON"]

    cmd = [cc, "-O2", "-fPIC", "-shared", "-o", out_file, SRC, "-lm", "-DPYCC_RUNTIME_BUILD"] + py_cflags + py_lflags
    if HOST_OS == "Linux":
        cmd += ["-lpthread", "-ldl"]
    elif HOST_OS == "Darwin":
        cmd += ["-framework", "CoreFoundation"]
    elif HOST_OS == "Windows":
        # PyCCRuntime.c's PYCC_WIN branch calls into Winsock (WSAStartup,
        # socket, bind, connect, send, recv, ...) for its socket wrapper
        # functions, but nothing linked ws2_32 -- that's the whole
        # Winsock import library, and without it every one of those
        # symbols comes back as "undefined reference to __imp_<name>"
        # at link time (the exact failure this fixes). advapi32 covers a
        # couple of registry/misc calls some mingw runtimes pull in
        # transitively; harmless to include even if unused here.
        cmd += ["-lws2_32", "-ladvapi32", "-static-libgcc"]

    if verbose:
        print("  CMD:", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"\x1b[31mBuild FAILED:\x1b[0m")
        print(result.stderr)
        return False
    print(f"\x1b[33m  -> {out_file}\x1b[0m")

    static_name = _cc_output_names(out_file)
    obj_file = out_file + ".o"
    static_cmd = [cc, "-O2", "-fPIC", "-c", "-o", obj_file, SRC, "-lm", "-DPYCC_RUNTIME_BUILD"] + py_cflags
    subprocess.run(static_cmd, capture_output=True)
    ar = shutil.which("ar")
    if ar and os.path.exists(obj_file):
        subprocess.run([ar, "rcs", static_name, obj_file], capture_output=True)
        os.remove(obj_file)
        if os.path.exists(static_name):
            print(f"\x1b[33m  -> {static_name} (static)\x1b[0m")

    return True


def build(arch, os_name, zig, verbose=False, cpython=False):
    os.makedirs(OUT_DIR, exist_ok=True)
    out_file = os.path.join(OUT_DIR, _output_name(arch, os_name))
    target   = _zig_target(arch, os_name)

    print(f"\x1b[36mBuilding PyCCRuntime for {arch}-{os_name}{'  +CPython' if cpython else ''}...\x1b[0m")

    py_cflags = []
    py_lflags = []
    if cpython:
        import sysconfig
        inc    = sysconfig.get_path("include")
        lib    = sysconfig.get_config_var("LIBDIR") or ""
        pyver  = sysconfig.get_config_var("LDVERSION") or sysconfig.get_config_var("py_version_short")
        if inc:    py_cflags += [f"-I{inc}"]
        if lib:    py_lflags += [f"-L{lib}"]
        if pyver:  py_lflags += [f"-lpython{pyver}"]
        py_cflags += ["-DPYCC_CPYTHON"]
        print(f"  Python include: {inc}")
        print(f"  Python lib:     {lib}")

    cmd = [
        zig, "cc",
        "-O2",
        "-shared",
        "-target", target,
        "-o", out_file,
        SRC,
        "-lm",
        "-DPYCC_RUNTIME_BUILD",
    ] + py_cflags + py_lflags

    if os_name == "Linux":
        cmd += ["-lpthread", "-ldl"]
    elif os_name == "Windows":
        # mingw target — link against standard Windows import libs
        cmd += ["-lws2_32", "-ladvapi32", "-luser32", "-lkernel32"]
    elif os_name == "Darwin":
        cmd += ["-framework", "CoreFoundation"]

    if verbose:
        print("  CMD:", " ".join(cmd))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"\x1b[31mBuild FAILED for {arch}-{os_name}:\x1b[0m")
            print(result.stderr)
            return False
        print(f"\x1b[33m  -> {out_file}\x1b[0m")

        # build static lib alongside the shared one
        static_name = (out_file
                       .replace(".dll",   ".lib")
                       .replace(".so",    ".a")
                       .replace(".dylib", ".a"))
        obj_file = out_file + ".o"
        static_cmd = [
            zig, "cc",
            "-O2",
            "-c",
            "-target", target,
            "-o", obj_file,
            SRC,
            "-lm",
            "-DPYCC_RUNTIME_BUILD",
        ] + py_cflags
        subprocess.run(static_cmd, capture_output=True)
        ar_cmd = [zig, "ar", "rcs", static_name, obj_file]
        subprocess.run(ar_cmd, capture_output=True)
        if os.path.exists(obj_file):
            os.remove(obj_file)
        if os.path.exists(static_name):
            print(f"\x1b[33m  -> {static_name} (static)\x1b[0m")

        return True
    except FileNotFoundError:
        print(f"\x1b[31mzig not found at: {zig}\x1b[0m")
        return False

def build_host(zig, verbose=False, cpython=False):
    arch = HOST_ARCH.lower()
    if arch == "amd64": arch = "x86_64"
    if arch == "arm64": arch = "aarch64"
    return build(arch, HOST_OS, zig, verbose, cpython)

def build_all(zig, verbose=False, cpython=False):
    results = {}
    for arch in SUPPORTED_ARCHES:
        for os_name in ["Linux", "Windows", "Darwin"]:
            key = f"{arch}-{os_name}"
            results[key] = build(arch, os_name, zig, verbose, cpython)
    print("\n\x1b[36mBuild summary:\x1b[0m")
    for k, v in results.items():
        status = "\x1b[32mOK\x1b[0m" if v else "\x1b[31mFAIL\x1b[0m"
        print(f"  {k}: {status}")

def clean():
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
        print(f"Cleaned {OUT_DIR}")
    for f in os.listdir(RUNTIME_DIR):
        if f.endswith((".o", ".obj", ".pdb")):
            os.remove(os.path.join(RUNTIME_DIR, f))
            print(f"Removed {f}")

def main():
    parser = argparse.ArgumentParser(description="Build PyCCRuntime library")
    parser.add_argument("--arch",    help="Target architecture (x86_64, aarch64, x86, riscv64, armv7)")
    parser.add_argument("--os",      help="Target OS (Windows, Linux, Darwin)", default=HOST_OS)
    parser.add_argument("--all",     action="store_true", help="Build for all architectures and OSes")
    parser.add_argument("--clean",   action="store_true", help="Clean build artifacts")
    parser.add_argument("--verbose", action="store_true", help="Show build commands")
    parser.add_argument("--zig",     help="Path to zig binary")
    parser.add_argument("--cpython", action="store_true", help="Embed CPython for full Python support")
    args = parser.parse_args()

    if args.clean:
        clean()
        return

    zig = args.zig or _find_zig()
    if not zig:
        # Cross-compiling (--all, or --arch/--os different from host) genuinely
        # needs zig for its bundled libc/cross-target support -- there's no
        # good native fallback for that. But a plain host-only build (the
        # common case: no --arch/--os/--all given) doesn't need zig at all;
        # whatever gcc/clang is already on the machine is enough, and this is
        # the only path this environment (no zig installed) can actually use.
        wants_cross = args.all or (args.arch and args.arch != HOST_ARCH.lower()) or (args.os != HOST_OS)
        if not wants_cross:
            cc = _find_cc()
            if cc:
                print("\x1b[33mzig not found -- falling back to native compiler for host-only build.\x1b[0m")
                print(f"Using: {cc}")
                ok = build_with_native_cc(cc, args.verbose, args.cpython)
                sys.exit(0 if ok else 1)
        print("\x1b[31mError: zig not found. Install zig or pass --zig <path>\x1b[0m")
        print("  Download: https://ziglang.org/download/")
        if not wants_cross:
            print("  (Alternatively, install gcc or clang for a host-only build without zig.)")
        sys.exit(1)

    print(f"Using zig: {zig}")
    print(f"Host: {HOST_OS} {HOST_ARCH}")
    print(f"Output: {OUT_DIR}")
    print()

    if args.all:
        build_all(zig, args.verbose, args.cpython)
    elif args.arch:
        build(args.arch, args.os, zig, args.verbose, args.cpython)
    else:
        ok = build_host(zig, args.verbose, args.cpython)
        sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()