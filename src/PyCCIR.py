"""
PyCCIR.py
Custom IR for PyCC. Emits x86_64, AArch64, RISC-V 64 assembly.
No LLVM dependency.
"""
import os
import platform
import shutil
import subprocess
import struct

ARCH_X86_64  = "x86_64"
ARCH_AARCH64 = "aarch64"
ARCH_X86     = "x86"
ARCH_RISCV64 = "riscv64"


class IRType:
    I1   = "i1"
    I8   = "i8"
    I32  = "i32"
    I64  = "i64"
    F64  = "f64"
    PTR  = "ptr"
    VOID = "void"


class IRInstr:
    def __init__(self, op, *args, dest=None, typ=None):
        self.op   = op
        self.args = args
        # IRCompiler emits temp dests as e.g. `t[1:]` where t is "%3" --
        # i.e. it passes the *string* "3", not the int 3. Every x86_64
        # backend's _store_dest() branches on `isinstance(dest, int)` to
        # decide "reuse the numbered temp slot" vs "allocate a new named
        # local", so a str dest silently takes the wrong branch: it
        # allocates a *new* local keyed by the string "3" instead of
        # reusing temp slot 3, and separately, any later `%3` arg
        # reference resolves via _get_tmp(3) (a real int, parsed out of
        # the "%3" syntax) and allocates yet another, different slot.
        # Net effect: two IR references to the same temp end up in two
        # different stack slots, and reads pull uninitialized garbage.
        # Coercing purely-numeric string dests back to int here is the
        # single choke point that fixes this for every caller/backend at
        # once, without touching the ~100 emit() call sites that do this.
        if isinstance(dest, str) and dest.lstrip("-").isdigit():
            dest = int(dest)
        self.dest = dest
        self.typ  = typ

    def __repr__(self):
        d = f"%{self.dest} = " if self.dest is not None else ""
        a = " ".join(str(x) for x in self.args)
        return f"  {d}{self.op} {a}"


class IRBlock:
    def __init__(self, label):
        self.label  = label
        self.instrs = []

    def emit(self, instr):
        self.instrs.append(instr)

    def is_terminated(self):
        if not self.instrs:
            return False
        return self.instrs[-1].op in ("ret", "jmp", "jz", "jnz")


class IRFunction:
    def __init__(self, name, params, ret_type):
        self.name     = name
        self.params   = params
        self.ret_type = ret_type
        self.blocks   = []
        self._tmp     = 0
        self._lbl     = 0
        self.current  = None
        self._new_block("entry")

    def _new_block(self, label=None):
        if label is None:
            label = f"L{self._lbl}"
            self._lbl += 1
        blk = IRBlock(label)
        self.blocks.append(blk)
        self.current = blk
        return blk

    def tmp(self):
        t = self._tmp
        self._tmp += 1
        return t

    def label(self):
        n = self._lbl
        self._lbl += 1
        return f"L{n}"

    def emit(self, op, *args, dest=None, typ=None):
        self.current.emit(IRInstr(op, *args, dest=dest, typ=typ))

    def switch_to(self, blk):
        self.current = blk


class IRModule:
    def __init__(self, name="module"):
        self.name     = name
        self.funcs    = []
        self.externs  = []
        self.globals  = []
        self._str_ctr = 0

    def add_func(self, name, params, ret_type):
        fn = IRFunction(name, params, ret_type)
        self.funcs.append(fn)
        return fn

    def add_extern(self, name):
        if name not in self.externs:
            self.externs.append(name)

    def add_global_str(self, value):
        label = f"__str_{self._str_ctr}"
        self._str_ctr += 1
        self.globals.append(("str", label, value))
        return label

    def add_global_int(self, name, value):
        self.globals.append(("i64", name, value))


def detect_host_arch():
    m = platform.machine().lower()
    if m in ("x86_64", "amd64"):     return ARCH_X86_64
    if m in ("aarch64", "arm64"):    return ARCH_AARCH64
    if m in ("i386", "i686", "x86"): return ARCH_X86
    if m == "riscv64":               return ARCH_RISCV64
    return ARCH_X86_64


def detect_host_os():
    return platform.system()


def _encode_str_for_nasm(value):
    parts = []
    buf   = ""
    for ch in value:
        code = ord(ch)
        if 32 <= code <= 126 and ch != '"':
            buf += ch
        else:
            if buf:
                parts.append(f'"{buf}"')
                buf = ""
            parts.append(str(code))
    if buf:
        parts.append(f'"{buf}"')
    parts.append("0")
    return ", ".join(parts)


class X86_64Backend:
    """
    x86_64 NASM backend.
    Bugs fixed vs previous version:
      1. ret: use 'leave' instead of 'mov rsp,rbp / pop rbp'
      2. Stack frame size is computed once and 16-byte aligned
      3. call: RSP aligned to 16 bytes before every call instruction
    """
    def __init__(self, module: IRModule, target_os=None):
        self.module    = module
        self.target_os = target_os or detect_host_os()
        self.out       = []

    def _w(self, line=""):
        self.out.append(line)

    def _pfx(self):
        return "_" if self.target_os == "Darwin" else ""

    def generate(self) -> str:
        self._w("bits 64")
        self._w("default rel")
        self._w("")
        self._w("section .data")
        for kind, label, value in self.module.globals:
            if kind == "str":
                self._w(f"  {label}: db {_encode_str_for_nasm(value)}")
            else:
                self._w(f"  {label}: dq {value}")
        self._w("")
        self._w("section .bss")
        self._w("")
        self._w("section .text")
        pfx = self._pfx()
        for ext in self.module.externs:
            self._w(f"  extern {pfx}{ext}")
        self._w("")
        for fn in self.module.funcs:
            self._w(f"  global {pfx}{fn.name}")
        self._w("")
        for fn in self.module.funcs:
            self._emit_func(fn)
        return "\n".join(self.out)

    def _count_slots(self, fn):
        # Count how many 8-byte slots the function needs by dry-running
        # the exact same allocation decisions _emit_func/_emit_instr will
        # make, instead of re-deriving the rules separately (which drifts
        # out of sync with the real emitter -- see history: dest-only
        # counting misses 'store' targets since store carries no dest;
        # and dest-only *also* misses temps that are only ever read via
        # a "%N" arg reference and never appear as a dest in this scope,
        # since _load_arg lazily allocates those through _get_tmp too).
        #
        # A slot is consumed the first time a name/temp is touched via:
        #   - a param binding
        #   - an 'alloca' dest, a 'store' target (args[1]), or any other
        #     non-int dest  -> named local (_alloc_local)
        #   - an int dest, or a "%N" arg reference on ANY instruction
        #     (not just its own dest) -> temp (_alloc_tmp / _get_tmp)
        names = set(pname for _, pname in fn.params)
        tmp_ids = set()

        def touch_arg(a):
            if isinstance(a, str) and a.startswith("%"):
                try:
                    tmp_ids.add(int(a[1:]))
                except ValueError:
                    pass

        for blk in fn.blocks:
            for instr in blk.instrs:
                if instr.dest is not None:
                    if isinstance(instr.dest, int):
                        tmp_ids.add(instr.dest)
                    else:
                        names.add(instr.dest)
                if instr.op in ("store", "alloca") and instr.args:
                    # store target is args[1] (or the alloca's own dest,
                    # already handled above); still cover args[1] safely
                    if instr.op == "store" and len(instr.args) > 1:
                        names.add(str(instr.args[1]))
                for a in instr.args:
                    touch_arg(a)

        n = len(names) + len(tmp_ids) + 8
        return n

    def _emit_func(self, fn: IRFunction):
        pfx = self._pfx()
        self._w(f"{pfx}{fn.name}:")
        self._w("  push rbp")
        self._w("  mov rbp, rsp")

        slots  = self._count_slots(fn)
        frame  = (slots * 8 + 15) & ~15
        if frame:
            self._w(f"  sub rsp, {frame}")
        self._w("")

        self._var_map   = {}
        self._tmp_map   = {}
        self._local_idx = 0
        self._frame_sz  = frame

        # System V AMD64: rdi rsi rdx rcx r8 r9
        # Windows x64:    rcx rdx r8 r9
        if self.target_os == "Windows":
            param_regs = ["rcx", "rdx", "r8", "r9"]
        else:
            param_regs = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]

        for i, (_, pname) in enumerate(fn.params):
            if i < len(param_regs):
                off = self._alloc_local(pname)
                self._w(f"  mov qword [rbp-{off}], {param_regs[i]}")

        for blk in fn.blocks:
            if blk.label != "entry":
                self._w(f".{fn.name}_{blk.label}:")
            for instr in blk.instrs:
                self._emit_instr(instr, fn)

        self._w("")

    def _alloc_local(self, name):
        self._local_idx += 1
        off = self._local_idx * 8
        self._var_map[name] = off
        return off

    def _alloc_tmp(self, tid):
        self._local_idx += 1
        off = self._local_idx * 8
        self._tmp_map[tid] = off
        return off

    def _get_tmp(self, tid):
        if tid not in self._tmp_map:
            self._alloc_tmp(tid)
        return self._tmp_map[tid]

    def _load_arg(self, arg, reg="rax"):
        if isinstance(arg, str) and arg.startswith("%"):
            off = self._get_tmp(int(arg[1:]))
            self._w(f"  mov {reg}, qword [rbp-{off}]")
        elif isinstance(arg, str) and arg.startswith("@"):
            name = arg[1:]
            if name in self._var_map:
                self._w(f"  mov {reg}, qword [rbp-{self._var_map[name]}]")
            else:
                self._w(f"  mov {reg}, [{name}]")
        elif isinstance(arg, str) and arg.startswith("$"):
            lbl = arg[1:]
            self._w(f"  lea {reg}, [{lbl}]")
        elif isinstance(arg, int):
            # large immediates need mov reg, imm64 with 'mov' not 'mov reg, imm32'
            if arg < -(1 << 31) or arg > (1 << 31) - 1:
                self._w(f"  mov {reg}, {arg}")
            else:
                self._w(f"  mov {reg}, {arg}")
        else:
            self._w(f"  mov {reg}, {arg}")

    def _store_dest(self, dest, reg="rax"):
        if isinstance(dest, int):
            off = self._get_tmp(dest)
            self._w(f"  mov qword [rbp-{off}], {reg}")
        else:
            if dest not in self._var_map:
                self._alloc_local(dest)
            self._w(f"  mov qword [rbp-{self._var_map[dest]}], {reg}")

    def _emit_instr(self, instr: IRInstr, fn: IRFunction):
        op  = instr.op
        pfx = self._pfx()

        if op == "const":
            val = instr.args[0]
            if isinstance(val, float):
                bits = struct.unpack("Q", struct.pack("d", val))[0]
                self._w(f"  mov rax, {bits}")
            else:
                self._w(f"  mov rax, {val}")
            self._store_dest(instr.dest)

        elif op == "sconst":
            lbl = instr.args[0]
            clean = lbl[1:] if lbl.startswith("$") else lbl
            self._w(f"  lea rax, [{clean}]")
            self._store_dest(instr.dest)

        elif op == "funcaddr":
            # Bare reference to a function name as a value (e.g. passed as
            # an argument). We don't support indirect calls through this
            # value yet, but loading its address lets the reference itself
            # compile instead of raising "Undefined variable".
            fn_label = instr.args[0]
            self._w(f"  lea rax, [{self._pfx()}{fn_label}]")
            self._store_dest(instr.dest)

        elif op == "alloca":
            if instr.dest not in self._var_map:
                self._alloc_local(instr.dest)

        elif op == "store":
            self._load_arg(instr.args[0], "rax")
            name = str(instr.args[1])
            if name not in self._var_map:
                self._alloc_local(name)
            self._w(f"  mov qword [rbp-{self._var_map[name]}], rax")

        elif op == "load":
            name = str(instr.args[0])
            if name in self._var_map:
                self._w(f"  mov rax, qword [rbp-{self._var_map[name]}]")
            else:
                self._w(f"  mov rax, 0")
            self._store_dest(instr.dest)

        elif op == "deref_byte":
            # Reads a single byte through a pointer *value* (e.g. a
            # malloc'd buffer address held in a temp) -- distinct from
            # "load" above, which reads a named local variable's own
            # stack slot by name. ord("A") needs this: the string arg is
            # a temp holding a pointer, and there was previously no
            # opcode at all for dereferencing a pointer value, only for
            # loading a named variable (so ord() silently read garbage/0
            # via a misuse of "load" that didn't do what was needed).
            self._load_arg(instr.args[0], "rax")   # rax = pointer value
            self._w("  movzx rax, byte ptr [rax]")
            self._store_dest(instr.dest)

        elif op == "add":
            self._load_arg(instr.args[0], "rax")
            self._load_arg(instr.args[1], "rcx")
            self._w("  add rax, rcx")
            self._store_dest(instr.dest)

        elif op == "sub":
            self._load_arg(instr.args[0], "rax")
            self._load_arg(instr.args[1], "rcx")
            self._w("  sub rax, rcx")
            self._store_dest(instr.dest)

        elif op == "mul":
            self._load_arg(instr.args[0], "rax")
            self._load_arg(instr.args[1], "rcx")
            self._w("  imul rax, rcx")
            self._store_dest(instr.dest)

        elif op == "div":
            self._load_arg(instr.args[0], "rax")
            self._load_arg(instr.args[1], "rcx")
            self._w("  cqo")
            self._w("  idiv rcx")
            self._store_dest(instr.dest)

        elif op == "mod":
            self._load_arg(instr.args[0], "rax")
            self._load_arg(instr.args[1], "rcx")
            self._w("  cqo")
            self._w("  idiv rcx")
            self._w("  mov rax, rdx")
            self._store_dest(instr.dest)

        elif op == "neg":
            self._load_arg(instr.args[0], "rax")
            self._w("  neg rax")
            self._store_dest(instr.dest)

        elif op == "fadd":
            self._load_arg(instr.args[0], "rax"); self._w("  movq xmm0, rax")
            self._load_arg(instr.args[1], "rax"); self._w("  movq xmm1, rax")
            self._w("  addsd xmm0, xmm1")
            self._w("  movq rax, xmm0")
            self._store_dest(instr.dest)

        elif op == "fsub":
            self._load_arg(instr.args[0], "rax"); self._w("  movq xmm0, rax")
            self._load_arg(instr.args[1], "rax"); self._w("  movq xmm1, rax")
            self._w("  subsd xmm0, xmm1")
            self._w("  movq rax, xmm0")
            self._store_dest(instr.dest)

        elif op == "fmul":
            self._load_arg(instr.args[0], "rax"); self._w("  movq xmm0, rax")
            self._load_arg(instr.args[1], "rax"); self._w("  movq xmm1, rax")
            self._w("  mulsd xmm0, xmm1")
            self._w("  movq rax, xmm0")
            self._store_dest(instr.dest)

        elif op == "fdiv":
            self._load_arg(instr.args[0], "rax"); self._w("  movq xmm0, rax")
            self._load_arg(instr.args[1], "rax"); self._w("  movq xmm1, rax")
            self._w("  divsd xmm0, xmm1")
            self._w("  movq rax, xmm0")
            self._store_dest(instr.dest)

        elif op in ("cmp_eq", "cmp_ne", "cmp_lt", "cmp_gt", "cmp_le", "cmp_ge"):
            self._load_arg(instr.args[0], "rax")
            self._load_arg(instr.args[1], "rcx")
            self._w("  cmp rax, rcx")
            setcc = {
                "cmp_eq": "sete",  "cmp_ne": "setne",
                "cmp_lt": "setl",  "cmp_gt": "setg",
                "cmp_le": "setle", "cmp_ge": "setge",
            }[op]
            self._w(f"  {setcc} al")
            self._w("  movzx rax, al")
            self._store_dest(instr.dest)

        elif op == "and_":
            self._load_arg(instr.args[0], "rax")
            self._load_arg(instr.args[1], "rcx")
            self._w("  and rax, rcx")
            self._store_dest(instr.dest)

        elif op == "or_":
            self._load_arg(instr.args[0], "rax")
            self._load_arg(instr.args[1], "rcx")
            self._w("  or rax, rcx")
            self._store_dest(instr.dest)

        elif op == "xor_":
            self._load_arg(instr.args[0], "rax")
            self._load_arg(instr.args[1], "rcx")
            self._w("  xor rax, rcx")
            self._store_dest(instr.dest)

        elif op == "not_":
            self._load_arg(instr.args[0], "rax")
            self._w("  test rax, rax")
            self._w("  sete al")
            self._w("  movzx rax, al")
            self._store_dest(instr.dest)

        elif op == "bnot":
            # True bitwise complement (Python's `~x`), distinct from the
            # logical/boolean "not_" above. Previously `~x` was wired
            # straight to "not_", which does boolean negation (any
            # non-zero -> 0, zero -> 1) instead of flipping every bit --
            # so `~5` produced 0 instead of the correct -6.
            self._load_arg(instr.args[0], "rax")
            self._w("  not rax")
            self._store_dest(instr.dest)

        elif op == "shl":
            self._load_arg(instr.args[0], "rax")
            self._load_arg(instr.args[1], "rcx")
            self._w("  shl rax, cl")
            self._store_dest(instr.dest)

        elif op == "shr":
            self._load_arg(instr.args[0], "rax")
            self._load_arg(instr.args[1], "rcx")
            self._w("  sar rax, cl")
            self._store_dest(instr.dest)

        elif op == "itof":
            self._load_arg(instr.args[0], "rax")
            self._w("  cvtsi2sd xmm0, rax")
            self._w("  movq rax, xmm0")
            self._store_dest(instr.dest)

        elif op == "ftoi":
            self._load_arg(instr.args[0], "rax")
            self._w("  movq xmm0, rax")
            self._w("  cvttsd2si rax, xmm0")
            self._store_dest(instr.dest)

        elif op == "zext":
            self._load_arg(instr.args[0], "rax")
            self._w("  movzx rax, al")
            self._store_dest(instr.dest)

        elif op == "trunc":
            self._load_arg(instr.args[0], "rax")
            self._w("  and rax, 0xFF")
            self._store_dest(instr.dest)

        elif op == "jmp":
            self._w(f"  jmp .{fn.name}_{instr.args[0]}")

        elif op == "jz":
            self._load_arg(instr.args[0], "rax")
            self._w("  test rax, rax")
            self._w(f"  jz .{fn.name}_{instr.args[1]}")

        elif op == "jnz":
            self._load_arg(instr.args[0], "rax")
            self._w("  test rax, rax")
            self._w(f"  jnz .{fn.name}_{instr.args[1]}")

        elif op == "call_f1":
            # Fixed-signature call with exactly one float arg (e.g. libc
            # round(double)). Same xmm-register requirement as call_ff,
            # just for a single argument -> xmm0 only.
            name = instr.args[0]
            a0 = instr.args[1]

            shadow = 32 if self.target_os == "Windows" else 0
            self._w("  and rsp, -16")
            if shadow:
                self._w(f"  sub rsp, {shadow}")

            self._load_arg(a0, "rax"); self._w("  movq xmm0, rax")

            self._w(f"  call {self._pfx()}{name}")

            if shadow:
                self._w(f"  add rsp, {shadow}")
            self._w(f"  lea rsp, [rbp-{self._frame_sz}]")
            self._w("  movq rax, xmm0")

            if instr.dest is not None:
                self._store_dest(instr.dest)

        elif op == "call_ff":
            # Fixed-signature call with exactly two float args (currently
            # only used for libc pow(double, double)). Unlike
            # call_fmt_float, this isn't variadic -- pow's signature is
            # fixed, so per SysV/Win64 ABI *both* args go in XMM registers
            # (xmm0, xmm1), never GP registers, and there's no AL vector-
            # count convention to set (that's a varargs-only rule). The
            # plain "call" opcode always routes args through GP registers,
            # so `2 ** 8` -> pow(2.0, 8.0) was silently computing garbage
            # (the float bit patterns landed in rdi/rsi instead of
            # xmm0/xmm1) -- e.g. 2**8 returned 8 instead of 256.
            name = instr.args[0]
            a0, a1 = instr.args[1], instr.args[2]

            shadow = 32 if self.target_os == "Windows" else 0
            self._w("  and rsp, -16")
            if shadow:
                self._w(f"  sub rsp, {shadow}")

            self._load_arg(a0, "rax"); self._w("  movq xmm0, rax")
            self._load_arg(a1, "rax"); self._w("  movq xmm1, rax")

            self._w(f"  call {self._pfx()}{name}")

            if shadow:
                self._w(f"  add rsp, {shadow}")
            self._w(f"  lea rsp, [rbp-{self._frame_sz}]")
            self._w("  movq rax, xmm0")

            if instr.dest is not None:
                self._store_dest(instr.dest)

        elif op == "call_fmt_float":
            # Like "call", except the *last* argument is a float being
            # passed to a variadic C function (printf/sprintf's "%g" arg).
            # SysV x86_64 requires variadic float args to arrive in an XMM
            # register, not a GP register, with AL set to the count of
            # vector registers used -- "call" doesn't know any of that
            # since it has no per-argument type info; this opcode exists
            # specifically for the one call shape that needs it.
            name  = instr.args[0]
            cargs = instr.args[1:]
            float_arg = cargs[-1]
            gp_cargs  = cargs[:-1]

            if self.target_os == "Windows":
                param_regs = ["rcx", "rdx", "r8", "r9"]
                shadow = 32
            else:
                param_regs = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]
                shadow = 0

            self._w("  and rsp, -16")
            if shadow:
                self._w(f"  sub rsp, {shadow}")

            for i, arg in enumerate(gp_cargs):
                if i < len(param_regs):
                    self._load_arg(arg, "rax")
                    self._w(f"  mov {param_regs[i]}, rax")

            # Float arg: load its raw bit pattern into a GP reg, then move
            # it into xmm0 as bits (movq, not cvt -- it's already an
            # IEEE-754 double bit pattern, not an integer to convert).
            self._load_arg(float_arg, "rax")
            self._w("  movq xmm0, rax")
            if self.target_os == "Windows":
                # Win64 varargs ABI: float args are duplicated into the
                # matching integer register (whatever GP slot this
                # position would occupy) *and* the FP register.
                fp_slot = len(gp_cargs)
                if fp_slot < len(param_regs):
                    self._w(f"  movq {param_regs[fp_slot]}, xmm0")
                self._w("  xor eax, eax")
            else:
                self._w("  mov al, 1")  # 1 vector register used (xmm0)

            self._w(f"  call {self._pfx()}{name}")

            if shadow:
                self._w(f"  add rsp, {shadow}")
            self._w(f"  lea rsp, [rbp-{self._frame_sz}]")

            if instr.dest is not None:
                self._store_dest(instr.dest)

        elif op == "call":
            # bug fix: align stack to 16 bytes before call
            # RSP must satisfy RSP % 16 == 0 at the call instruction
            # after 'push rbp' + 'sub rsp, frame' RSP is already aligned
            # but we push an extra alignment slot when needed
            name  = instr.args[0]
            cargs = instr.args[1:]
            n_args = len(cargs)

            if self.target_os == "Windows":
                param_regs = ["rcx", "rdx", "r8", "r9"]
                # Windows x64 requires 32-byte shadow space
                shadow = 32
            else:
                param_regs = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]
                shadow = 0

            # align rsp: after all pushes, rsp+8 (for return addr) must be 16-aligned
            # simplest: ensure rsp is 16-aligned here
            self._w("  and rsp, -16")
            if shadow:
                self._w(f"  sub rsp, {shadow}")

            for i, arg in enumerate(cargs):
                if i < len(param_regs):
                    self._load_arg(arg, "rax")
                    self._w(f"  mov {param_regs[i]}, rax")

            # xor eax,eax = al=0 (vararg float count)
            self._w("  xor eax, eax")
            self._w(f"  call {pfx}{name}")

            if shadow:
                self._w(f"  add rsp, {shadow}")

            # restore rsp to frame-relative position
            self._w(f"  lea rsp, [rbp-{self._frame_sz}]")

            if instr.dest is not None:
                self._store_dest(instr.dest)

        elif op == "ret":
            if instr.args:
                self._load_arg(instr.args[0], "rax")
            # bug fix: use 'leave' which correctly does mov rsp,rbp + pop rbp
            self._w("  leave")
            self._w("  ret")

        elif op == "label":
            self._w(f".{fn.name}_{instr.args[0]}:")

        elif op == "select":
            self._load_arg(instr.args[0], "rax")
            self._w("  test rax, rax")
            self._load_arg(instr.args[1], "rcx")
            self._load_arg(instr.args[2], "rdx")
            self._w("  cmovz rcx, rdx")
            self._w("  mov rax, rcx")
            self._store_dest(instr.dest)


class X86_64GASBackend(X86_64Backend):
    """
    x86_64 GNU-as (GAS) backend, for environments without NASM
    (e.g. plain UCRT64/MSYS2, most Linux distros' binutils-only setups).

    Reuses all of X86_64Backend's instruction-selection logic (it's already
    Intel-syntax) and only overrides the parts GAS needs written differently:
      - header/footer directives (.intel_syntax noprefix, .section, .globl)
      - data section emission (db/dq -> .byte/.quad, string encoding)
      - a strict `qword [..]` -> `qword ptr [..]` fixup, since GAS's Intel
        mode requires the explicit 'ptr' keyword that NASM doesn't use.
    """

    def _w_fix(self, line):
        # GAS Intel-syntax requires 'qword ptr [...]' / 'byte ptr [...]'
        # etc, whereas NASM just uses 'qword [...]'. Patch on the way out
        # rather than rewriting every call site above.
        for kw in ("qword", "dword", "word", "byte"):
            line = line.replace(f"{kw} [", f"{kw} ptr [")
        return line

    def _w(self, line=""):
        self.out.append(self._w_fix(line))

    def generate(self) -> str:
        self._w(".intel_syntax noprefix")
        self._w("")
        self._w(".section .data")
        for kind, label, value in self.module.globals:
            if kind == "str":
                self._w(f"  {label}: .asciz {_encode_str_for_gas(value)}")
            else:
                self._w(f"  {label}: .quad {value}")
        self._w("")
        self._w(".section .bss")
        self._w("")
        self._w(".section .text")
        pfx = self._pfx()
        for ext in self.module.externs:
            self._w(f"  .extern {pfx}{ext}")
        self._w("")
        for fn in self.module.funcs:
            self._w(f"  .globl {pfx}{fn.name}")
        self._w("")
        for fn in self.module.funcs:
            self._emit_func(fn)
        return "\n".join(self.out)


def _encode_str_for_gas(value):
    escaped = []
    for ch in value:
        code = ord(ch)
        if ch == '\\':
            escaped.append('\\\\')
        elif ch == '"':
            escaped.append('\\"')
        elif ch == '\n':
            escaped.append('\\n')
        elif ch == '\t':
            escaped.append('\\t')
        elif 32 <= code <= 126:
            escaped.append(ch)
        else:
            escaped.append('\\%03o' % code)
    return '"' + "".join(escaped) + '"'


class AArch64Backend:
    def __init__(self, module: IRModule, target_os=None):
        self.module    = module
        self.target_os = target_os or detect_host_os()
        self.out       = []

    def _w(self, l=""):
        self.out.append(l)

    def generate(self) -> str:
        self._w(".arch armv8-a")
        self._w(".text")
        for fn in self.module.funcs:
            self._w(f".global {fn.name}")
        self._w(".data")
        for kind, label, value in self.module.globals:
            if kind == "str":
                esc = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
                self._w(f'{label}: .asciz "{esc}"')
            else:
                self._w(f"{label}: .quad {value}")
        self._w(".text")
        for fn in self.module.funcs:
            self._emit_func(fn)
        return "\n".join(self.out)

    def _emit_func(self, fn):
        self._w(f"{fn.name}:")
        self._w("  stp x29, x30, [sp, #-16]!")
        self._w("  mov x29, sp")
        slots = len(fn.params) + 32
        frame = (slots * 8 + 15) & ~15
        self._w(f"  sub sp, sp, #{frame}")
        self._var_map   = {}
        self._tmp_map   = {}
        self._local_idx = 0
        self._frame_sz  = frame
        pregs = ["x0","x1","x2","x3","x4","x5","x6","x7"]
        for i, (_, pname) in enumerate(fn.params):
            if i < len(pregs):
                off = self._alloc_local(pname)
                self._w(f"  str {pregs[i]}, [x29, #-{off}]")
        for blk in fn.blocks:
            if blk.label != "entry":
                self._w(f".{fn.name}_{blk.label}:")
            for instr in blk.instrs:
                self._emit_instr(instr, fn)
        self._w("")

    def _alloc_local(self, name):
        self._local_idx += 1
        off = self._local_idx * 8
        self._var_map[name] = off
        return off

    def _alloc_tmp(self, tid):
        self._local_idx += 1
        off = self._local_idx * 8
        self._tmp_map[tid] = off
        return off

    def _get_tmp(self, tid):
        if tid not in self._tmp_map:
            self._alloc_tmp(tid)
        return self._tmp_map[tid]

    def _load_arg(self, arg, reg="x0"):
        if isinstance(arg, str) and arg.startswith("%"):
            off = self._get_tmp(int(arg[1:]))
            self._w(f"  ldr {reg}, [x29, #-{off}]")
        elif isinstance(arg, str) and arg.startswith("@"):
            name = arg[1:]
            if name in self._var_map:
                self._w(f"  ldr {reg}, [x29, #-{self._var_map[name]}]")
            else:
                self._w(f"  adrp {reg}, {name}"); self._w(f"  add {reg}, {reg}, :lo12:{name}")
        elif isinstance(arg, str) and arg.startswith("$"):
            lbl = arg[1:]
            self._w(f"  adrp {reg}, {lbl}"); self._w(f"  add {reg}, {reg}, :lo12:{lbl}")
        elif isinstance(arg, int):
            if -65535 <= arg <= 65535:
                self._w(f"  mov {reg}, #{arg}")
            else:
                self._w(f"  mov {reg}, #{arg & 0xFFFF}")
                self._w(f"  movk {reg}, #{(arg >> 16) & 0xFFFF}, lsl #16")
        else:
            self._w(f"  mov {reg}, #0")

    def _store_dest(self, dest, reg="x0"):
        if isinstance(dest, int):
            off = self._get_tmp(dest)
            self._w(f"  str {reg}, [x29, #-{off}]")
        else:
            if dest not in self._var_map:
                self._alloc_local(dest)
            self._w(f"  str {reg}, [x29, #-{self._var_map[dest]}]")

    def _emit_instr(self, instr, fn):
        op = instr.op
        if op == "const":
            self._load_arg(instr.args[0], "x0"); self._store_dest(instr.dest)
        elif op == "sconst":
            lbl = instr.args[0][1:] if instr.args[0].startswith("$") else instr.args[0]
            self._w(f"  adrp x0, {lbl}"); self._w(f"  add x0, x0, :lo12:{lbl}")
            self._store_dest(instr.dest)
        elif op == "alloca":
            if instr.dest not in self._var_map: self._alloc_local(instr.dest)
        elif op == "store":
            self._load_arg(instr.args[0], "x0")
            name = str(instr.args[1])
            if name not in self._var_map: self._alloc_local(name)
            self._w(f"  str x0, [x29, #-{self._var_map[name]}]")
        elif op == "load":
            name = str(instr.args[0])
            if name in self._var_map: self._w(f"  ldr x0, [x29, #-{self._var_map[name]}]")
            else: self._w("  mov x0, #0")
            self._store_dest(instr.dest)
        elif op == "add":
            self._load_arg(instr.args[0], "x0"); self._load_arg(instr.args[1], "x1")
            self._w("  add x0, x0, x1"); self._store_dest(instr.dest)
        elif op == "sub":
            self._load_arg(instr.args[0], "x0"); self._load_arg(instr.args[1], "x1")
            self._w("  sub x0, x0, x1"); self._store_dest(instr.dest)
        elif op == "mul":
            self._load_arg(instr.args[0], "x0"); self._load_arg(instr.args[1], "x1")
            self._w("  mul x0, x0, x1"); self._store_dest(instr.dest)
        elif op == "div":
            self._load_arg(instr.args[0], "x0"); self._load_arg(instr.args[1], "x1")
            self._w("  sdiv x0, x0, x1"); self._store_dest(instr.dest)
        elif op == "mod":
            self._load_arg(instr.args[0], "x0"); self._load_arg(instr.args[1], "x1")
            self._w("  sdiv x2, x0, x1"); self._w("  msub x0, x2, x1, x0")
            self._store_dest(instr.dest)
        elif op == "neg":
            self._load_arg(instr.args[0], "x0"); self._w("  neg x0, x0"); self._store_dest(instr.dest)
        elif op in ("cmp_eq","cmp_ne","cmp_lt","cmp_gt","cmp_le","cmp_ge"):
            self._load_arg(instr.args[0], "x0"); self._load_arg(instr.args[1], "x1")
            self._w("  cmp x0, x1")
            cset = {"cmp_eq":"eq","cmp_ne":"ne","cmp_lt":"lt","cmp_gt":"gt","cmp_le":"le","cmp_ge":"ge"}[op]
            self._w(f"  cset x0, {cset}"); self._store_dest(instr.dest)
        elif op == "and_":
            self._load_arg(instr.args[0], "x0"); self._load_arg(instr.args[1], "x1")
            self._w("  and x0, x0, x1"); self._store_dest(instr.dest)
        elif op == "or_":
            self._load_arg(instr.args[0], "x0"); self._load_arg(instr.args[1], "x1")
            self._w("  orr x0, x0, x1"); self._store_dest(instr.dest)
        elif op == "xor_":
            self._load_arg(instr.args[0], "x0"); self._load_arg(instr.args[1], "x1")
            self._w("  eor x0, x0, x1"); self._store_dest(instr.dest)
        elif op == "not_":
            self._load_arg(instr.args[0], "x0")
            self._w("  cmp x0, #0"); self._w("  cset x0, eq"); self._store_dest(instr.dest)
        elif op == "shl":
            self._load_arg(instr.args[0], "x0"); self._load_arg(instr.args[1], "x1")
            self._w("  lsl x0, x0, x1"); self._store_dest(instr.dest)
        elif op == "shr":
            self._load_arg(instr.args[0], "x0"); self._load_arg(instr.args[1], "x1")
            self._w("  asr x0, x0, x1"); self._store_dest(instr.dest)
        elif op == "itof":
            self._load_arg(instr.args[0], "x0")
            self._w("  scvtf d0, x0"); self._w("  fmov x0, d0"); self._store_dest(instr.dest)
        elif op == "ftoi":
            self._load_arg(instr.args[0], "x0")
            self._w("  fmov d0, x0"); self._w("  fcvtzs x0, d0"); self._store_dest(instr.dest)
        elif op == "zext":
            self._load_arg(instr.args[0], "x0"); self._w("  and x0, x0, #0xFF"); self._store_dest(instr.dest)
        elif op == "jmp":
            self._w(f"  b .{fn.name}_{instr.args[0]}")
        elif op == "jz":
            self._load_arg(instr.args[0], "x0"); self._w(f"  cbz x0, .{fn.name}_{instr.args[1]}")
        elif op == "jnz":
            self._load_arg(instr.args[0], "x0"); self._w(f"  cbnz x0, .{fn.name}_{instr.args[1]}")
        elif op == "call":
            cargs = instr.args[1:]
            regs  = ["x0","x1","x2","x3","x4","x5","x6","x7"]
            for i, arg in enumerate(cargs):
                if i < len(regs): self._load_arg(arg, regs[i])
            self._w(f"  bl {instr.args[0]}")
            if instr.dest is not None: self._store_dest(instr.dest)
        elif op == "ret":
            if instr.args: self._load_arg(instr.args[0], "x0")
            self._w(f"  add sp, sp, #{self._frame_sz}")
            self._w("  ldp x29, x30, [sp], #16")
            self._w("  ret")
        elif op == "label":
            self._w(f".{fn.name}_{instr.args[0]}:")
        elif op == "select":
            self._load_arg(instr.args[0], "x0"); self._w("  cmp x0, #0")
            self._load_arg(instr.args[1], "x1"); self._load_arg(instr.args[2], "x2")
            self._w("  csel x0, x1, x2, ne"); self._store_dest(instr.dest)


class RISCV64Backend:
    def __init__(self, module, target_os=None):
        self.module    = module
        self.target_os = target_os or detect_host_os()
        self.out       = []

    def _w(self, l=""): self.out.append(l)

    def generate(self):
        self._w(".option nopic")
        self._w(".text")
        for fn in self.module.funcs: self._w(f".global {fn.name}")
        self._w(".section .rodata")
        for kind, label, value in self.module.globals:
            if kind == "str":
                esc = value.replace('"','\\"').replace("\n","\\n").replace("\t","\\t")
                self._w(f'{label}: .asciz "{esc}"')
        self._w(".text")
        for fn in self.module.funcs: self._emit_func(fn)
        return "\n".join(self.out)

    def _emit_func(self, fn):
        self._w(f"{fn.name}:")
        self._w("  addi sp, sp, -256")
        self._w("  sd ra, 248(sp)")
        self._w("  sd s0, 240(sp)")
        self._w("  addi s0, sp, 256")
        self._var_map = {}; self._tmp_map = {}; self._local_idx = 0
        pregs = ["a0","a1","a2","a3","a4","a5","a6","a7"]
        for i, (_, pn) in enumerate(fn.params):
            if i < len(pregs):
                off = self._alloc_local(pn)
                self._w(f"  sd {pregs[i]}, -{off}(s0)")
        for blk in fn.blocks:
            if blk.label != "entry": self._w(f".{fn.name}_{blk.label}:")
            for instr in blk.instrs: self._emit_instr(instr, fn)
        self._w("")

    def _alloc_local(self, n):
        self._local_idx += 1; off = self._local_idx * 8; self._var_map[n] = off; return off

    def _alloc_tmp(self, t):
        self._local_idx += 1; off = self._local_idx * 8; self._tmp_map[t] = off; return off

    def _get_tmp(self, t):
        if t not in self._tmp_map: self._alloc_tmp(t)
        return self._tmp_map[t]

    def _load_arg(self, arg, reg="a0"):
        if isinstance(arg, str) and arg.startswith("%"):
            off = self._get_tmp(int(arg[1:])); self._w(f"  ld {reg}, -{off}(s0)")
        elif isinstance(arg, str) and arg.startswith("@"):
            n = arg[1:]
            if n in self._var_map: self._w(f"  ld {reg}, -{self._var_map[n]}(s0)")
            else: self._w(f"  la {reg}, {n}")
        elif isinstance(arg, str) and arg.startswith("$"):
            self._w(f"  la {reg}, {arg[1:]}")
        elif isinstance(arg, int):
            self._w(f"  li {reg}, {arg}")
        else:
            self._w(f"  li {reg}, 0")

    def _store_dest(self, dest, reg="a0"):
        if isinstance(dest, int):
            off = self._get_tmp(dest); self._w(f"  sd {reg}, -{off}(s0)")
        else:
            if dest not in self._var_map: self._alloc_local(dest)
            self._w(f"  sd {reg}, -{self._var_map[dest]}(s0)")

    def _emit_instr(self, instr, fn):
        op = instr.op
        if op == "const": self._load_arg(instr.args[0], "a0"); self._store_dest(instr.dest)
        elif op == "sconst": self._w(f"  la a0, {instr.args[0][1:] if instr.args[0].startswith('$') else instr.args[0]}"); self._store_dest(instr.dest)
        elif op == "alloca":
            if instr.dest not in self._var_map: self._alloc_local(instr.dest)
        elif op == "store":
            self._load_arg(instr.args[0], "a0")
            n = str(instr.args[1])
            if n not in self._var_map: self._alloc_local(n)
            self._w(f"  sd a0, -{self._var_map[n]}(s0)")
        elif op == "load":
            n = str(instr.args[0])
            if n in self._var_map: self._w(f"  ld a0, -{self._var_map[n]}(s0)")
            else: self._w("  li a0, 0")
            self._store_dest(instr.dest)
        elif op == "add":
            self._load_arg(instr.args[0],"a0"); self._load_arg(instr.args[1],"a1")
            self._w("  add a0, a0, a1"); self._store_dest(instr.dest)
        elif op == "sub":
            self._load_arg(instr.args[0],"a0"); self._load_arg(instr.args[1],"a1")
            self._w("  sub a0, a0, a1"); self._store_dest(instr.dest)
        elif op == "mul":
            self._load_arg(instr.args[0],"a0"); self._load_arg(instr.args[1],"a1")
            self._w("  mul a0, a0, a1"); self._store_dest(instr.dest)
        elif op == "div":
            self._load_arg(instr.args[0],"a0"); self._load_arg(instr.args[1],"a1")
            self._w("  div a0, a0, a1"); self._store_dest(instr.dest)
        elif op == "mod":
            self._load_arg(instr.args[0],"a0"); self._load_arg(instr.args[1],"a1")
            self._w("  rem a0, a0, a1"); self._store_dest(instr.dest)
        elif op == "neg":
            self._load_arg(instr.args[0],"a0"); self._w("  neg a0, a0"); self._store_dest(instr.dest)
        elif op in ("cmp_eq","cmp_ne","cmp_lt","cmp_gt","cmp_le","cmp_ge"):
            self._load_arg(instr.args[0],"a0"); self._load_arg(instr.args[1],"a1")
            self._w("  sub a0, a0, a1")
            if op == "cmp_eq": self._w("  seqz a0, a0")
            elif op == "cmp_ne": self._w("  snez a0, a0")
            elif op == "cmp_lt": self._w("  sltz a0, a0")
            elif op == "cmp_gt": self._w("  sgtz a0, a0")
            else: self._w("  snez a0, a0")
            self._store_dest(instr.dest)
        elif op == "call":
            cargs = instr.args[1:]; regs = ["a0","a1","a2","a3","a4","a5","a6","a7"]
            for i, arg in enumerate(cargs):
                if i < len(regs): self._load_arg(arg, regs[i])
            self._w(f"  call {instr.args[0]}")
            if instr.dest is not None: self._store_dest(instr.dest)
        elif op == "ret":
            if instr.args: self._load_arg(instr.args[0], "a0")
            self._w("  ld ra, 248(sp)"); self._w("  ld s0, 240(sp)")
            self._w("  addi sp, sp, 256"); self._w("  ret")
        elif op == "jmp": self._w(f"  j .{fn.name}_{instr.args[0]}")
        elif op == "jz":
            self._load_arg(instr.args[0],"a0"); self._w(f"  beqz a0, .{fn.name}_{instr.args[1]}")
        elif op == "jnz":
            self._load_arg(instr.args[0],"a0"); self._w(f"  bnez a0, .{fn.name}_{instr.args[1]}")
        elif op == "label": self._w(f".{fn.name}_{instr.args[0]}:")
        elif op == "and_":
            self._load_arg(instr.args[0],"a0"); self._load_arg(instr.args[1],"a1")
            self._w("  and a0, a0, a1"); self._store_dest(instr.dest)
        elif op == "or_":
            self._load_arg(instr.args[0],"a0"); self._load_arg(instr.args[1],"a1")
            self._w("  or a0, a0, a1"); self._store_dest(instr.dest)
        elif op == "select":
            self._load_arg(instr.args[0],"a0"); self._load_arg(instr.args[1],"a1"); self._load_arg(instr.args[2],"a2")
            self._w("  bnez a0, 1f"); self._w("  mv a1, a2"); self._w("1:"); self._w("  mv a0, a1")
            self._store_dest(instr.dest)


def get_backend(module, arch=None, target_os=None, asm_syntax=None):
    """
    asm_syntax: None/"nasm" (default) -> X86_64Backend (NASM syntax)
                "gas"                 -> X86_64GASBackend (GNU as, Intel syntax)
    Only affects x86_64; other arches only ever had one assembler target.
    """
    arch = arch or detect_host_arch()
    if arch in (ARCH_X86_64,):
        if asm_syntax == "gas":
            return X86_64GASBackend(module, target_os)
        return X86_64Backend(module, target_os)
    if arch in (ARCH_AARCH64, "arm64"): return AArch64Backend(module, target_os)
    if arch in (ARCH_RISCV64,):        return RISCV64Backend(module, target_os)
    return X86_64Backend(module, target_os)
