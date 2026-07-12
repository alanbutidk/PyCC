"""
PyCC.py
Python to native compiler. Default backend: PyCCIR (custom IR + asm).
Use --ir llvm for LLVM/llvmlite backend.
"""
import sys
import os
import time

from Tokenize import tokenize
from PyCCParser import parse, ProgramNode, IfNode, CompareNode, StringNode, VariableNode, PyCCSyntaxError

VERSION = "1.1.0"


def _format_syntax_error(path, source, err):
    """
    Render a parse error the way a person can actually act on:
        Line N:
          <the offending source line, as written>
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        <message>
    instead of a bare, unlocatable "at position 317" token index (token
    indices are into the post-SKIP_TOKENS-filtered stream, so they don't
    correspond to a byte offset, a token-per-line count, or anything else
    you could grep for -- finding the actual line previously meant
    re-running the tokenizer by hand and counting).
    """
    line_no = getattr(err, "pycc_line", None)
    msg = str(err)
    if line_no is None or not source:
        return f"\x1b[31mSyntax error in {path}: {msg}\x1b[0m"

    src_lines = source.splitlines()
    idx = line_no - 1
    code_line = src_lines[idx] if 0 <= idx < len(src_lines) else ""
    stripped = code_line.strip()
    underline = "~" * max(1, min(len(stripped) if stripped else 40, 80))

    out = []
    out.append(f"\x1b[33mLine {line_no}\x1b[0m:")
    out.append(f"  {stripped}")
    out.append(f"\x1b[31m{underline}\x1b[0m")
    out.append(f"\x1b[31mSyntax error in {path}: {msg}\x1b[0m")
    return "\n".join(out)


def parse_args(argv):
    args = {
        "inputs":    [],
        "output":    None,
        "static":    False,
        "opt_level": 0,
        "pyh":       [],
        "pyl":       [],
        "npdb":      False,
        "nobj":      False,
        "noobj":     False,
        "ir":        "pycc",
        "verbose":   False,
        "runtime":   False,
        "arch":      None,
        "target_os": None,
    }
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "-o":
            i += 1
            if i >= len(argv):
                _die("-o requires a filename")
            args["output"] = argv[i]
        elif arg == "--static":
            args["static"] = True
        elif arg.startswith("-O") and len(arg) > 2:
            try:
                args["opt_level"] = int(arg[2:])
            except ValueError:
                _die(f"invalid opt level: {arg}")
        elif arg.startswith("-PyH"):
            args["pyh"].append(arg[4:])
        elif arg.startswith("-PyL"):
            args["pyl"].append(arg[4:])
        elif arg in ("-npdb", "--npdb"):
            args["npdb"] = True
        elif arg in ("-nobj", "-no", "--nobj"):
            args["nobj"] = args["noobj"] = True
        elif arg == "-runtime" or arg == "--runtime":
            args["runtime"] = True
        elif arg.startswith("--arch="):
            args["arch"] = arg[7:]
        elif arg.startswith("--target-os="):
            args["target_os"] = arg[12:]
        elif arg == "--ir":
            i += 1
            if i >= len(argv):
                _die("--ir requires a backend name (pycc or llvm)")
            args["ir"] = argv[i].lower()
            if args["ir"] not in ("pycc", "llvm"):
                _die(f"unknown IR backend: {args['ir']}. Use 'pycc' or 'llvm'")
        elif arg in ("-v", "--verbose"):
            args["verbose"] = True
        elif arg == "--help":
            _print_help()
            sys.exit(0)
        elif arg == "--version":
            _print_version()
            sys.exit(0)
        elif arg.endswith(".py"):
            args["inputs"].append(arg)
        else:
            _die(f"unknown argument: {arg}")
        i += 1
    return args


def _die(msg):
    print(f"\x1b[31mError: {msg}\x1b[0m", file=sys.stderr)
    sys.exit(1)


def _print_version():
    print(f"PyCC {VERSION}")
    print(f"Python {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")


def _print_help():
    print(f"PyCC {VERSION} - Python to Native Compiler")
    print()
    print("Usage:")
    print("  PyCC.py <file.py> [files...] [options]")
    print()
    print("Options:")
    print("  -o <output>       Output binary name")
    print("  --static          Link statically")
    print("  -O0..3            Optimization level (llvm backend only)")
    print("  -PyH<dir>         .py import search path")
    print("  -PyL<dir>         Library search path")
    print("  -npdb             Delete .pdb after compile")
    print("  -nobj / -no       Delete .o and .asm after compile")
    print("  -runtime          Link PyCCRuntime (full syscall/socket/thread support)")
    print("  --arch=<arch>     Target arch: x86_64, aarch64, x86, riscv64")
    print("  --target-os=<os>  Target OS: Windows, Linux, Darwin")
    print("  --ir <backend>    IR backend: pycc (default), llvm")
    print("  -v / --verbose    Verbose output")
    print("  --version         Print version")
    print("  --help            This help")
    print()
    print("Examples:")
    print("  PyCC.py hello.py")
    print("  PyCC.py hello.py -no -npdb -runtime")
    print("  PyCC.py hello.py --arch=aarch64 --target-os=Linux")
    print("  PyCC.py hello.py --ir llvm -O2")


def _strip_main_guard(body):
    result = []
    for node in body:
        if (isinstance(node, IfNode) and
                isinstance(node.test, CompareNode) and
                isinstance(node.test.left, VariableNode) and
                node.test.left.name == "__name__" and
                len(node.test.comparators) == 1 and
                isinstance(node.test.comparators[0], StringNode) and
                node.test.comparators[0].value == "__main__"):
            result.extend(node.body)
        else:
            result.append(node)
    return result


def main():
    args = parse_args(sys.argv)

    if not args["inputs"]:
        _print_help()
        sys.exit(0)

    missing = [f for f in args["inputs"] if not os.path.exists(f)]
    if missing:
        for f in missing:
            print(f"\x1b[31mFile not found: {f}\x1b[0m", file=sys.stderr)
        sys.exit(1)

    if not args["output"]:
        base = os.path.splitext(args["inputs"][0])[0]
        args["output"] = base + (".exe" if sys.platform == "win32" else "")

    if args["verbose"]:
        print(f"\x1b[36mPyCC {VERSION}\x1b[0m")
        print(f"  Input:   {', '.join(args['inputs'])}")
        print(f"  Output:  {args['output']}")
        print(f"  Backend: {args['ir'].upper()}")
        if args["arch"]:      print(f"  Arch:    {args['arch']}")
        if args["target_os"]: print(f"  OS:      {args['target_os']}")
        if args["runtime"]:   print(f"  Runtime: PyCCRuntime")

    t0 = time.time()

    combined_body = []
    for path in args["inputs"]:
        resolved = path
        if not os.path.exists(path):
            for d in args["pyh"]:
                c = os.path.join(d, path)
                if os.path.exists(c):
                    resolved = c
                    break
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                source = f.read()
            tokens = tokenize(source)
            tree   = parse(tokens)
            combined_body.extend(tree.body)
        except SyntaxError as e:
            print(_format_syntax_error(path, source, e), file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"\x1b[31mParse error in {path}: {e}\x1b[0m", file=sys.stderr)
            sys.exit(1)

    combined_body = _strip_main_guard(combined_body)
    combined_tree  = ProgramNode(combined_body)

    try:
        if args["ir"] == "llvm":
            from Compiler import compile_ast
            compile_ast(combined_tree, args["output"], args)
        else:
            from IRCompiler import compile_ast_ir
            compile_ast_ir(combined_tree, args["output"], args)
    except Exception as e:
        print(f"\x1b[31mCompilation failed: {e}\x1b[0m", file=sys.stderr)
        if args["verbose"]:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    if args["verbose"]:
        print(f"  Time:    {time.time()-t0:.2f}s")


if __name__ == "__main__":
    main()
