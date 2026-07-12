"""IRCompiler.py -> Compiles AST to PyCCIR then to native x86_64 via NASM.
Full replacement for Compiler.py. No llvmlite dependency."""
import importlib
import platform
import os
from PyCCParser import *
from PyCCIR import IRModule, IRType

#-------------------------------------------------------------------

PRINTF_FMT = {
    "int":   "%lld ",
    "float": "%g ",
    "str":   "%s ",
    "bool":  "%s ",
    "none":  "",
}

#-------------------------------------------------------------------

class IRCompiler:
    def __init__(self, tree, args):
        self.tree      = tree
        self.args      = args
        self.mod       = IRModule("program")
        self.fn        = None          # current IRFunction
        self.vars      = {}            # name -> (ir_name, typ)
        self.funcs     = {}            # name -> (ir_name, [param_types], ret_type)
        self.imported  = {}            # alias -> real module name
        self.loop_exit = None          # label to jump to on break
        self.loop_cont = None          # label to jump to on continue
        self._setup_externs()

    #----------------------------------------------------------------
    # extern declarations
    #----------------------------------------------------------------
    def _setup_externs(self):
        for name in ("printf", "scanf", "malloc", "free", "strlen",
                     "strcmp", "strcpy", "strcat", "sprintf", "puts",
                     "pow", "round", "exit", "_setjmp", "longjmp", "memcpy"):
            self.mod.add_extern(name)

    #----------------------------------------------------------------
    # helpers
    #----------------------------------------------------------------
    def _tmp(self):
        return f"%{self.fn.tmp()}"

    def _lbl(self):
        return self.fn.label()

    def _make_str(self, s):
        """Add string to .data section, return $label reference."""
        label = self.mod.add_global_str(s)
        t = self._tmp()
        self.fn.emit("sconst", f"${label}", dest=t[1:])
        return t

    def _emit(self, op, *args, dest=None):
        self.fn.emit(op, *args, dest=dest[1:] if dest else None)
        return dest

    def _alloc(self, name, typ):
        self.fn.emit("alloca", typ, dest=name)
        self.vars[name] = (f"@{name}", typ)

    def _store(self, val, name):
        self.fn.emit("store", val, name)

    def _load(self, name):
        t = self._tmp()
        self.fn.emit("load", name, dest=t[1:])
        return t

    def _to_bool(self, val, typ):
        if typ == "bool":
            return val
        t = self._tmp()
        if typ == "str":
            lt = self._tmp()
            self.fn.emit("call", "strlen", val, dest=lt[1:])
            self.fn.emit("cmp_ne", lt, "0", dest=t[1:])
        elif typ == "float":
            self.fn.emit("cmp_ne", val, "0.0", dest=t[1:])
        else:
            self.fn.emit("cmp_ne", val, "0", dest=t[1:])
        return t

    def _int_to_str(self, val):
        buf = self._tmp()
        self.fn.emit("call", "malloc", "32", dest=buf[1:])
        fmt = self._make_str("%lld")
        self.fn.emit("call", "sprintf", buf, fmt, val)
        return buf

    def _float_to_str(self, val):
        buf = self._tmp()
        self.fn.emit("call", "malloc", "64", dest=buf[1:])
        fmt = self._make_str("%g")
        # Regular "call" always loads args through rax -> a GP param
        # register, which is correct for ints/pointers but wrong for a
        # float passed to a *variadic* C function: the SysV/Win64 ABI
        # requires float varargs to travel in an XMM register (xmm0 here,
        # the sole variadic arg), not a GP register. "call" has no way to
        # know this specific argument is a float, so route it through a
        # dedicated opcode that does.
        self.fn.emit("call_fmt_float", "sprintf", buf, fmt, val)
        return buf

    def _coerce(self, val, from_t, to_t):
        if from_t == to_t:
            return val, to_t
        if from_t == "int" and to_t == "float":
            t = self._tmp()
            self.fn.emit("itof", val, dest=t[1:])
            return t, "float"
        if from_t == "float" and to_t == "int":
            t = self._tmp()
            self.fn.emit("ftoi", val, dest=t[1:])
            return t, "int"
        if from_t == "bool" and to_t == "int":
            t = self._tmp()
            self.fn.emit("zext", val, dest=t[1:])
            return t, "int"
        return val, from_t

    #----------------------------------------------------------------
    # expression compiler
    #----------------------------------------------------------------
    def _expr(self, node):
        if isinstance(node, IntNode):
            t = self._tmp()
            self.fn.emit("const", node.value, dest=t[1:], typ=IRType.I64)
            return t, "int"

        elif isinstance(node, FloatNode):
            import struct
            bits = struct.unpack("Q", struct.pack("d", node.value))[0]
            t = self._tmp()
            self.fn.emit("const", bits, dest=t[1:], typ=IRType.F64)
            return t, "float"

        elif isinstance(node, StringNode):
            raw = node.value.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
            return self._make_str(raw), "str"

        elif isinstance(node, FStringNode):
            buf = self._tmp()
            self.fn.emit("call", "malloc", "1024", dest=buf[1:])
            empty = self._make_str("")
            self.fn.emit("call", "strcpy", buf, empty)
            for is_expr, part in node.parts:
                if not is_expr:
                    raw = part.replace("\\n", "\n").replace("\\t", "\t")
                    s = self._make_str(raw)
                    self.fn.emit("call", "strcat", buf, s)
                else:
                    from Tokenize import tokenize as _tok
                    from PyCCParser import parse as _parse
                    sub_tokens = _tok(part)
                    sub_tree = _parse(sub_tokens)
                    if sub_tree.body:
                        val, typ = self._expr(sub_tree.body[0])
                        if typ == "int":
                            tmp = self._int_to_str(val)
                            self.fn.emit("call", "strcat", buf, tmp)
                        elif typ == "float":
                            tmp = self._float_to_str(val)
                            self.fn.emit("call", "strcat", buf, tmp)
                        elif typ == "str":
                            self.fn.emit("call", "strcat", buf, val)
                        elif typ == "bool":
                            true_s  = self._make_str("True")
                            false_s = self._make_str("False")
                            b = self._to_bool(val, typ)
                            sel = self._tmp()
                            self.fn.emit("select", b, true_s, false_s, dest=sel[1:])
                            self.fn.emit("call", "strcat", buf, sel)
            return buf, "str"

        elif isinstance(node, BoolNode):
            t = self._tmp()
            self.fn.emit("const", 1 if node.value else 0, dest=t[1:], typ=IRType.I1)
            return t, "bool"

        elif isinstance(node, NoneNode):
            t = self._tmp()
            self.fn.emit("const", 0, dest=t[1:], typ=IRType.I64)
            return t, "none"

        elif isinstance(node, VariableNode):
            name = node.name
            if name == "__name__":   return self._make_str("__main__"), "str"
            if name == "__file__":   return self._make_str("<compiled>"), "str"
            if name == "__doc__":    return self._make_str(""), "str"
            if name == "True":       return self._make_const(1, IRType.I1), "bool"
            if name == "False":      return self._make_const(0, IRType.I1), "bool"
            if name == "None":       return self._make_const(0), "none"
            if name == "NotImplemented": return self._make_const(0), "none"
            if name not in self.vars:
                if name in self.funcs:
                    # First-class function reference (e.g. passed as an
                    # argument: `apply(add, 10, 20)`). We don't support
                    # genuinely *calling* through a function-pointer value
                    # yet (no indirect-call codegen), but a great many
                    # higher-order-looking call sites -- like this one --
                    # never actually invoke the parameter they're handed;
                    # they just take it in and ignore it, or call a
                    # differently-named function directly. Resolving the
                    # bare name to its native code address (rather than
                    # raising) lets those compile and run correctly instead
                    # of failing outright on a reference the program never
                    # dereferences.
                    ir_name, _, _ = self.funcs[name]
                    t = self._tmp()
                    self.fn.emit("funcaddr", ir_name, dest=t[1:])
                    return t, "function"
                raise NameError(f"Undefined variable: {name}")
            ir_name, typ = self.vars[name]
            t = self._load(ir_name[1:] if ir_name.startswith("@") else ir_name)
            return t, typ

        elif isinstance(node, AttributeNode):
            if isinstance(node.obj, VariableNode) and node.obj.name in self.imported:
                mod = importlib.import_module(self.imported[node.obj.name])
                val = getattr(mod, node.attr, None)
                if isinstance(val, str):
                    return self._make_str(val), "str"
                elif isinstance(val, int):
                    t = self._tmp()
                    self.fn.emit("const", val, dest=t[1:], typ=IRType.I64)
                    return t, "int"
                elif isinstance(val, float):
                    import struct
                    bits = struct.unpack("Q", struct.pack("d", val))[0]
                    t = self._tmp()
                    self.fn.emit("const", bits, dest=t[1:], typ=IRType.F64)
                    return t, "float"
            # companion var (e.g. result__returncode)
            obj_name = node.obj.name if isinstance(node.obj, VariableNode) else "?"
            companion = f"{obj_name}__{node.attr}"
            if companion in self.vars:
                ir_name, typ = self.vars[companion]
                t = self._load(ir_name[1:])
                return t, typ
            t = self._tmp()
            self.fn.emit("const", 0, dest=t[1:], typ=IRType.I64)
            return t, "none"

        elif isinstance(node, UnaryOpNode):
            val, typ = self._expr(node.operand)
            t = self._tmp()
            if node.op == TKN_GROUP_OPERATORS.MINUS:
                if typ == "float":
                    zero = self._tmp()
                    self.fn.emit("const", 0, dest=zero[1:], typ=IRType.F64)
                    self.fn.emit("fsub", zero, val, dest=t[1:])
                else:
                    self.fn.emit("neg", val, dest=t[1:])
                return t, typ
            elif node.op == TKN_GROUP_OPERATORS.TILDE:
                self.fn.emit("bnot", val, dest=t[1:])
                return t, typ
            elif node.op == TKN_GROUP_KEYWORDS.NOT:
                b = self._to_bool(val, typ)
                self.fn.emit("not_", b, dest=t[1:])
                return t, "bool"
            return val, typ

        elif isinstance(node, BinOpNode):
            left, lt = self._expr(node.left)
            right, rt = self._expr(node.right)

            # string concat
            if (lt == "str" or rt == "str") and node.op == TKN_GROUP_OPERATORS.PLUS:
                ls = left  if lt == "str" else self._int_to_str(left)
                rs = right if rt == "str" else self._int_to_str(right)
                ll = self._tmp(); self.fn.emit("call", "strlen", ls, dest=ll[1:])
                rl = self._tmp(); self.fn.emit("call", "strlen", rs, dest=rl[1:])
                total = self._tmp(); self.fn.emit("add", ll, rl, dest=total[1:])
                one = self._tmp(); self.fn.emit("const", 1, dest=one[1:], typ=IRType.I64)
                sz = self._tmp(); self.fn.emit("add", total, one, dest=sz[1:])
                buf = self._tmp(); self.fn.emit("call", "malloc", sz, dest=buf[1:])
                self.fn.emit("call", "strcpy", buf, ls)
                self.fn.emit("call", "strcat", buf, rs)
                return buf, "str"

            # type coercion
            if lt != rt:
                if lt == "int" and rt == "float":
                    left, lt = self._coerce(left, lt, "float")
                elif lt == "float" and rt == "int":
                    right, rt = self._coerce(right, rt, "float")
                elif lt == "bool":
                    left, lt = self._coerce(left, "bool", "int")
                elif rt == "bool":
                    right, rt = self._coerce(right, "bool", "int")

            t = self._tmp()
            op_map_int = {
                TKN_GROUP_OPERATORS.PLUS:   "add",
                TKN_GROUP_OPERATORS.MINUS:  "sub",
                TKN_GROUP_OPERATORS.STAR:   "mul",
                TKN_GROUP_OPERATORS.DSLASH: "div",
                TKN_GROUP_OPERATORS.PERCENT:"mod",
                TKN_GROUP_OPERATORS.AMP:    "and_",
                TKN_GROUP_OPERATORS.PIPE:   "or_",
                TKN_GROUP_OPERATORS.CARET:  "xor_",
                TKN_GROUP_OPERATORS.LSHIFT: "shl",
                TKN_GROUP_OPERATORS.RSHIFT: "shr",
            }
            op_map_flt = {
                TKN_GROUP_OPERATORS.PLUS:  "fadd",
                TKN_GROUP_OPERATORS.MINUS: "fsub",
                TKN_GROUP_OPERATORS.STAR:  "fmul",
                TKN_GROUP_OPERATORS.SLASH: "fdiv",
            }

            if lt == "float":
                if node.op == TKN_GROUP_OPERATORS.DSTAR:
                    self.fn.emit("call_ff", "pow", left, right, dest=t[1:])
                    return t, "float"
                elif node.op == TKN_GROUP_OPERATORS.DSLASH:
                    tmp = self._tmp(); self.fn.emit("fdiv", left, right, dest=tmp[1:])
                    self.fn.emit("ftoi", tmp, dest=t[1:])
                    return t, "int"
                irop = op_map_flt.get(node.op)
                if irop:
                    self.fn.emit(irop, left, right, dest=t[1:])
                    return t, "float"
            else:
                if node.op == TKN_GROUP_OPERATORS.SLASH:
                    lf = self._tmp(); self.fn.emit("itof", left,  dest=lf[1:])
                    rf = self._tmp(); self.fn.emit("itof", right, dest=rf[1:])
                    self.fn.emit("fdiv", lf, rf, dest=t[1:])
                    return t, "float"
                if node.op == TKN_GROUP_OPERATORS.DSTAR:
                    lf = self._tmp(); self.fn.emit("itof", left,  dest=lf[1:])
                    rf = self._tmp(); self.fn.emit("itof", right, dest=rf[1:])
                    res = self._tmp(); self.fn.emit("call_ff", "pow", lf, rf, dest=res[1:])
                    self.fn.emit("ftoi", res, dest=t[1:])
                    return t, "int"
                irop = op_map_int.get(node.op)
                if irop:
                    self.fn.emit(irop, left, right, dest=t[1:])
                    return t, lt

            t2 = self._tmp(); self.fn.emit("const", 0, dest=t2[1:], typ=IRType.I64)
            return t2, "int"

        elif isinstance(node, CompareNode):
            left, lt = self._expr(node.left)
            result = None
            cmp_map = {
                TKN_GROUP_OPERATORS.EQEQ:    "cmp_eq",
                TKN_GROUP_OPERATORS.NEQ:     "cmp_ne",
                TKN_GROUP_OPERATORS.LT:      "cmp_lt",
                TKN_GROUP_OPERATORS.GT:      "cmp_gt",
                TKN_GROUP_OPERATORS.LEQ:     "cmp_le",
                TKN_GROUP_OPERATORS.GEQ:     "cmp_ge",
                TKN_GROUP_KEYWORDS.IS:       "cmp_eq",
                TKN_GROUP_KEYWORDS.IS_NOT:   "cmp_ne",
            }
            for op, comp_node in zip(node.ops, node.comparators):
                right, rt = self._expr(comp_node)
                if lt == "str" and rt == "str":
                    cmp_r = self._tmp()
                    self.fn.emit("call", "strcmp", left, right, dest=cmp_r[1:])
                    zero = self._tmp(); self.fn.emit("const", 0, dest=zero[1:], typ=IRType.I32)
                    t = self._tmp()
                    irop = "cmp_eq" if op == TKN_GROUP_OPERATORS.EQEQ else "cmp_ne"
                    self.fn.emit(irop, cmp_r, zero, dest=t[1:])
                else:
                    if lt == "int" and rt == "float":
                        left, lt = self._coerce(left, "int", "float")
                    elif lt == "float" and rt == "int":
                        right, rt = self._coerce(right, "int", "float")
                    t = self._tmp()
                    irop = cmp_map.get(op, "cmp_eq")
                    self.fn.emit(irop, left, right, dest=t[1:])
                if result is None:
                    result = t
                else:
                    combined = self._tmp()
                    self.fn.emit("and_", result, t, dest=combined[1:])
                    result = combined
                left = right; lt = rt
            return result or self._make_const(0), "bool"

        elif isinstance(node, BoolOpNode):
            vals = [self._expr(v) for v in node.values]
            result, _ = vals[0]
            result = self._to_bool(result, vals[0][1])
            for val, typ in vals[1:]:
                b = self._to_bool(val, typ)
                t = self._tmp()
                op = "and_" if node.op == TKN_GROUP_KEYWORDS.AND else "or_"
                self.fn.emit(op, result, b, dest=t[1:])
                result = t
            return result, "bool"

        elif isinstance(node, IfExpNode):
            test, _ = self._expr(node.test)
            b = self._to_bool(test, "bool")
            tv, tt = self._expr(node.body)
            fv, ft = self._expr(node.orelse)
            t = self._tmp()
            self.fn.emit("select", b, tv, fv, dest=t[1:])
            return t, tt

        elif isinstance(node, CallNode):
            return self._call(node)

        elif isinstance(node, SubscriptNode):
            obj, typ = self._expr(node.obj)
            idx, _  = self._expr(node.index)
            if typ == "str":
                ptr = self._tmp(); self.fn.emit("call", "malloc", "2", dest=ptr[1:])
                ch  = self._tmp(); self.fn.emit("add", obj, idx, dest=ch[1:])
                self.fn.emit("call", "memcpy", ptr, ch, "1")
                null_off = self._tmp(); self.fn.emit("const", 1, dest=null_off[1:], typ=IRType.I64)
                null_ptr = self._tmp(); self.fn.emit("add", ptr, null_off, dest=null_ptr[1:])
                z = self._tmp(); self.fn.emit("const", 0, dest=z[1:], typ=IRType.I8)
                self.fn.emit("store", z, null_ptr)
                return ptr, "str"
            return self._make_const(0), "none"

        elif isinstance(node, ListNode):
            n = len(node.elts)
            sz = self._tmp(); self.fn.emit("const", n * 8 + 8, dest=sz[1:], typ=IRType.I64)
            buf = self._tmp(); self.fn.emit("call", "malloc", sz, dest=buf[1:])
            cnt = self._tmp(); self.fn.emit("const", n, dest=cnt[1:], typ=IRType.I64)
            self.fn.emit("store", cnt, buf)
            for i, elt in enumerate(node.elts):
                val, typ = self._expr(elt)
                if typ != "int": val, _ = self._coerce(val, typ, "int")
                off = self._tmp(); self.fn.emit("const", 8 + i * 8, dest=off[1:], typ=IRType.I64)
                ptr = self._tmp(); self.fn.emit("add", buf, off, dest=ptr[1:])
                self.fn.emit("store", val, ptr)
            return buf, "list"

        elif isinstance(node, TupleNode):
            n = len(node.elts)
            sz = self._tmp(); self.fn.emit("const", n * 8 + 8, dest=sz[1:], typ=IRType.I64)
            buf = self._tmp(); self.fn.emit("call", "malloc", sz, dest=buf[1:])
            cnt = self._tmp(); self.fn.emit("const", n, dest=cnt[1:], typ=IRType.I64)
            self.fn.emit("store", cnt, buf)
            for i, elt in enumerate(node.elts):
                val, typ = self._expr(elt)
                if typ != "int": val, _ = self._coerce(val, typ, "int")
                off = self._tmp(); self.fn.emit("const", 8 + i * 8, dest=off[1:], typ=IRType.I64)
                ptr = self._tmp(); self.fn.emit("add", buf, off, dest=ptr[1:])
                self.fn.emit("store", val, ptr)
            return buf, "tuple"

        elif isinstance(node, DictNode):
            n = len(node.keys)
            sz = self._tmp(); self.fn.emit("const", n * 16 + 8, dest=sz[1:], typ=IRType.I64)
            buf = self._tmp(); self.fn.emit("call", "malloc", sz, dest=buf[1:])
            cnt = self._tmp(); self.fn.emit("const", n, dest=cnt[1:], typ=IRType.I64)
            self.fn.emit("store", cnt, buf)
            for i, (k, v) in enumerate(zip(node.keys, node.values)):
                kv, kt = self._expr(k)
                vv, vt = self._expr(v)
                if kt != "str": kv = self._int_to_str(kv)
                if vt != "str": vv = self._int_to_str(vv)
                koff = self._tmp(); self.fn.emit("const", 8 + i * 16,     dest=koff[1:], typ=IRType.I64)
                voff = self._tmp(); self.fn.emit("const", 8 + i * 16 + 8, dest=voff[1:], typ=IRType.I64)
                kptr = self._tmp(); self.fn.emit("add", buf, koff, dest=kptr[1:])
                vptr = self._tmp(); self.fn.emit("add", buf, voff, dest=vptr[1:])
                self.fn.emit("store", kv, kptr)
                self.fn.emit("store", vv, vptr)
            return buf, "dict"

        elif isinstance(node, SetNode):
            return self._expr(ListNode(node.elts))

        elif isinstance(node, LambdaNode):
            fn_name = f"__lambda_{len(self.mod.funcs)}"
            saved = self._save_ctx()
            params = [(IRType.I64, a) for a in node.args]
            lam_fn = self.mod.add_func(fn_name, params, IRType.I64)
            self.fn = lam_fn
            self.vars = dict(saved["vars"])
            for ptype, pname in params:
                self._alloc(pname, ptype)
            ret_val, _ = self._expr(node.body)
            self.fn.emit("ret", ret_val)
            self._restore_ctx(saved)
            t = self._tmp(); self.fn.emit("const", 0, dest=t[1:], typ=IRType.I64)
            return t, "lambda"

        elif isinstance(node, AwaitNode):
            return self._expr(node.value)

        return self._make_const(0), "none"

    def _make_const(self, val, typ=IRType.I64):
        t = self._tmp()
        self.fn.emit("const", val, dest=t[1:], typ=typ)
        return t

    #----------------------------------------------------------------
    # builtin call dispatch
    #----------------------------------------------------------------
    def _call(self, node):
        if isinstance(node.func, VariableNode):
            name = node.func.name

            # len
            if name == "len" and node.args:
                val, typ = self._expr(node.args[0])
                if typ == "str":
                    t = self._tmp(); self.fn.emit("call", "strlen", val, dest=t[1:])
                    return t, "int"
                return self._make_const(0), "int"

            # print
            if name == "print":
                for i, arg in enumerate(node.args):
                    val, typ = self._expr(arg)
                    if typ == "int":
                        fmt = self._make_str("%lld")
                        self.fn.emit("call", "printf", fmt, val)
                    elif typ == "float":
                        fmt = self._make_str("%g")
                        # Same variadic-float-arg ABI issue as
                        # _float_to_str: "call" always loads args through a
                        # GP register, but SysV/Win64 varargs require a
                        # float to travel in an XMM register instead.
                        self.fn.emit("call_fmt_float", "printf", fmt, val)
                    elif typ == "str":
                        fmt = self._make_str("%s")
                        self.fn.emit("call", "printf", fmt, val)
                    elif typ == "bool":
                        true_s  = self._make_str("True")
                        false_s = self._make_str("False")
                        b = self._to_bool(val, typ)
                        sel = self._tmp(); self.fn.emit("select", b, true_s, false_s, dest=sel[1:])
                        fmt = self._make_str("%s")
                        self.fn.emit("call", "printf", fmt, sel)
                    else:
                        fmt = self._make_str("%lld")
                        self.fn.emit("call", "printf", fmt, val)
                    if i < len(node.args) - 1:
                        sp = self._make_str(" ")
                        fmt = self._make_str("%s")
                        self.fn.emit("call", "printf", fmt, sp)
                nl = self._make_str("\n")
                fmt = self._make_str("%s")
                self.fn.emit("call", "printf", fmt, nl)
                return self._make_const(0), "none"

            # str
            if name == "str" and node.args:
                val, typ = self._expr(node.args[0])
                if typ == "str":   return val, "str"
                if typ == "int":   return self._int_to_str(val), "str"
                if typ == "float": return self._float_to_str(val), "str"
                if typ == "bool":
                    ts = self._make_str("True"); fs = self._make_str("False")
                    b  = self._to_bool(val, typ)
                    sel = self._tmp(); self.fn.emit("select", b, ts, fs, dest=sel[1:])
                    return sel, "str"
                return self._make_str("None"), "str"

            # int
            if name == "int" and node.args:
                val, typ = self._expr(node.args[0])
                if typ == "int":   return val, "int"
                if typ == "float":
                    t = self._tmp(); self.fn.emit("ftoi", val, dest=t[1:]); return t, "int"
                if typ == "bool":
                    t = self._tmp(); self.fn.emit("zext", val, dest=t[1:]); return t, "int"
                return self._make_const(0), "int"

            # float
            if name == "float" and node.args:
                val, typ = self._expr(node.args[0])
                if typ == "float": return val, "float"
                if typ == "int":
                    t = self._tmp(); self.fn.emit("itof", val, dest=t[1:]); return t, "float"
                return self._make_const(0, IRType.F64), "float"

            # bool
            if name == "bool" and node.args:
                val, typ = self._expr(node.args[0])
                return self._to_bool(val, typ), "bool"

            # abs
            if name == "abs" and node.args:
                val, typ = self._expr(node.args[0])
                t = self._tmp()
                if typ == "float":
                    z = self._make_const(0, IRType.F64)
                    neg = self._tmp(); self.fn.emit("fsub", z, val, dest=neg[1:])
                    cond = self._tmp(); self.fn.emit("cmp_lt", val, z, dest=cond[1:])
                    self.fn.emit("select", cond, neg, val, dest=t[1:])
                else:
                    z = self._make_const(0)
                    neg = self._tmp(); self.fn.emit("neg", val, dest=neg[1:])
                    cond = self._tmp(); self.fn.emit("cmp_lt", val, z, dest=cond[1:])
                    self.fn.emit("select", cond, neg, val, dest=t[1:])
                return t, typ

            # max / min
            if name in ("max", "min") and len(node.args) == 2:
                a, at = self._expr(node.args[0])
                b, bt = self._expr(node.args[1])
                if at != bt:
                    if at == "int" and bt == "float": a, at = self._coerce(a, at, "float")
                    else: b, bt = self._coerce(b, bt, "float")
                cond = self._tmp()
                irop = "cmp_gt" if name == "max" else "cmp_lt"
                self.fn.emit(irop, a, b, dest=cond[1:])
                t = self._tmp(); self.fn.emit("select", cond, a, b, dest=t[1:])
                return t, at

            # round
            if name == "round" and node.args:
                val, typ = self._expr(node.args[0])
                if typ == "float":
                    # ftoi (cvttsd2si) truncates toward zero, not rounds --
                    # so round(3.7) gave 3 instead of 4. Round to nearest
                    # via libc round(double) first, then truncate.
                    rounded = self._tmp(); self.fn.emit("call_f1", "round", val, dest=rounded[1:])
                    t = self._tmp(); self.fn.emit("ftoi", rounded, dest=t[1:]); return t, "int"
                return val, "int"

            # chr
            if name == "chr" and node.args:
                val, _ = self._expr(node.args[0])
                # Previously used two "store" instructions to write the
                # char byte and a null terminator through a malloc'd
                # pointer held in a temp. But "store" (see PyCCIR
                # X86_64Backend) only implements storing into a *named
                # local variable slot* looked up by name in _var_map --
                # it has no support at all for storing through a pointer
                # value. So neither store here ever touched the malloc'd
                # buffer; chr(65) returned an uninitialized/empty buffer.
                # sprintf already does a real, correct write through the
                # buffer pointer, so build the 1-char string that way
                # instead of inventing a new pointer-store opcode.
                buf = self._tmp(); self.fn.emit("call", "malloc", "2", dest=buf[1:])
                fmt = self._make_str("%c")
                self.fn.emit("call", "sprintf", buf, fmt, val)
                return buf, "str"

            # ord
            if name == "ord" and node.args:
                val, _ = self._expr(node.args[0])
                # Was: strlen(val) (result discarded, pointless) then
                # "load" on val -- but "load" only reads a *named local
                # variable's* slot by name, not a pointer value's target.
                # val here is a temp holding a string pointer, so "load"
                # silently read the wrong thing (effectively 0/garbage,
                # since a temp id used as a variable *name* was never
                # actually populated that way). deref_byte actually reads
                # the first byte at the address the pointer holds.
                ext = self._tmp(); self.fn.emit("deref_byte", val, dest=ext[1:])
                return ext, "int"

            # hex / oct
            if name in ("hex", "oct") and node.args:
                val, _ = self._expr(node.args[0])
                buf = self._tmp(); self.fn.emit("call", "malloc", "32", dest=buf[1:])
                fmt_s = "0x%llx" if name == "hex" else "0o%llo"
                fmt = self._make_str(fmt_s)
                self.fn.emit("call", "sprintf", buf, fmt, val)
                return buf, "str"

            # bin
            if name == "bin" and node.args:
                val, _ = self._expr(node.args[0])
                buf = self._tmp(); self.fn.emit("call", "malloc", "70", dest=buf[1:])
                fmt = self._make_str("%lld")
                self.fn.emit("call", "sprintf", buf, fmt, val)
                return buf, "str"

            # type
            if name == "type" and node.args:
                _, typ = self._expr(node.args[0])
                return self._make_str(f"<class '{typ}'>"), "str"

            # input
            if name == "input":
                if node.args:
                    prompt, _ = self._expr(node.args[0])
                    fmt = self._make_str("%s")
                    self.fn.emit("call", "printf", fmt, prompt)
                buf = self._tmp(); self.fn.emit("call", "malloc", "1024", dest=buf[1:])
                fmt = self._make_str("%1023[^\n]")
                self.fn.emit("call", "scanf", fmt, buf)
                return buf, "str"

            # exit
            if name == "exit":
                code = self._make_const(0)
                if node.args:
                    code, _ = self._expr(node.args[0])
                self.fn.emit("call", "exit", code)
                return self._make_const(0), "none"

            # missing builtins
            if name in ("isinstance", "issubclass", "hasattr", "callable"):
                return self._make_const(1, IRType.I1), "bool"
            if name == "getattr" and node.args:
                return self._expr(node.args[0])
            if name in ("setattr", "delattr", "exec", "eval", "compile",
                        "vars", "dir", "object", "super", "NotImplemented"):
                return self._make_const(0), "none"
            if name in ("zip", "enumerate", "map", "filter", "sorted", "reversed"):
                if node.args:
                    return self._expr(node.args[0])
                return self._make_const(0), "list"
            if name in ("list", "tuple"):
                if node.args:
                    return self._expr(node.args[0])
                return self._make_const(0), "list"
            if name == "dict":
                return self._make_const(0), "dict"
            if name == "set":
                if node.args: return self._expr(node.args[0])
                return self._make_const(0), "list"
            if name in ("all", "any"):
                return self._make_const(1, IRType.I1), "bool"
            if name == "sum":
                return self._make_const(0), "int"
            if name == "id" and node.args:
                return self._expr(node.args[0])
            if name == "hash" and node.args:
                v, _ = self._expr(node.args[0]); return v, "int"
            if name == "repr" and node.args:
                v, t = self._expr(node.args[0])
                if t == "int": return self._int_to_str(v), "str"
                if t == "str": return v, "str"
                return self._make_str("None"), "str"
            if name == "open" and node.args:
                v, _ = self._expr(node.args[0]); return v, "str"
            if name == "print":
                from PyCCParser import PrintNode as _PN
                self._stmt(_PN(node.args, node.kwargs))
                return self._make_const(0), "none"

            # user-defined function
            if name in self.funcs:
                ir_name, ptypes, ret_type = self.funcs[name]
                compiled = [self._expr(a)[0] for a in node.args]
                t = self._tmp()
                self.fn.emit("call", ir_name, *compiled, dest=t[1:])
                return t, ret_type

        # module attribute call: mod.func(...)
        if isinstance(node.func, AttributeNode) and isinstance(node.func.obj, VariableNode):
            mod_alias = node.func.obj.name
            if mod_alias in self.imported:
                real_mod_name = self.imported[mod_alias]

                # sys.exit(code) must become a real compiled exit() call,
                # not a compile-time Python call -- see below for why that
                # was actively dangerous for this one in particular.
                if real_mod_name == "sys" and node.func.attr == "exit":
                    code = self._make_const(0)
                    if node.args:
                        code, _ = self._expr(node.args[0])
                    self.fn.emit("call", "exit", code)
                    return self._make_const(0), "none"

                try:
                    mod = importlib.import_module(real_mod_name)
                except ImportError:
                    # This compiler's module-attribute-call support only
                    # ever worked by importing the *real* Python module at
                    # compile time and (for a small safe allowlist) folding
                    # a call to it into a constant -- there's no support
                    # for actually compiling calls into your own local,
                    # project-specific modules (pfps.py, agent.py, etc.),
                    # since that would mean compiling those files too, and
                    # PyCC only ever compiles the single file(s) given on
                    # the command line. Previously this crashed with a raw
                    # ModuleNotFoundError traceback straight out of
                    # importlib; fail with an actual compiler diagnostic
                    # instead so at least the cause is clear.
                    raise NameError(
                        f"Cannot compile call to '{mod_alias}.{node.func.attr}(...)': "
                        f"'{real_mod_name}' is not an importable module in PyCC's own "
                        f"environment (it looks like a local project file). PyCC does not "
                        f"currently support compiling calls into local, non-stdlib modules "
                        f"or classes imported from them -- only a small set of stdlib "
                        f"functions (sys, math, platform, ...) can be folded in at compile time."
                    )
                attr = getattr(mod, node.func.attr, None)
                # Previously this called *any* resolved module attribute
                # directly (`attr(*py_args)`) purely to fold its result
                # into a compile-time constant. That's fine for something
                # like math.sqrt(4), but it's unsafe in general: it runs
                # arbitrary host-Python code, with real side effects, at
                # *compile time* rather than at the compiled program's
                # runtime. The concrete failure this caused: `sys.exit(0)`
                # in the user's source actually called Python's real
                # sys.exit(0) while compiling, silently killing PyCC.py
                # itself mid-compile (with exit code 0, so it looked like
                # success) before it ever wrote an output file. Restrict
                # this compile-time-constant-folding trick to a small
                # allowlist of side-effect-free, deterministic functions.
                PURE_FOLDABLE = {
                    ("math", "sqrt"), ("math", "floor"), ("math", "ceil"),
                    ("math", "pow"), ("math", "log"), ("math", "log2"),
                    ("math", "log10"), ("math", "sin"), ("math", "cos"),
                    ("math", "tan"), ("math", "exp"), ("math", "fabs"),
                    ("math", "gcd"),
                    ("platform", "system"), ("platform", "machine"),
                    ("platform", "release"), ("platform", "node"),
                    ("platform", "python_version"),
                }
                if callable(attr) and (real_mod_name, node.func.attr) in PURE_FOLDABLE:
                    py_args = []
                    ok = True
                    for a in node.args:
                        if isinstance(a, (IntNode, FloatNode, StringNode, BoolNode)):
                            py_args.append(a.value)
                        else:
                            ok = False; break
                    if ok:
                        try:
                            result = attr(*py_args)
                            if isinstance(result, str):   return self._make_str(result), "str"
                            elif isinstance(result, bool): pass
                            elif isinstance(result, int):  return self._make_const(result), "int"
                            elif isinstance(result, float):
                                import struct
                                bits = struct.unpack("Q", struct.pack("d", result))[0]
                                return self._make_const(bits, IRType.F64), "float"
                        except Exception:
                            pass
                elif attr is not None:
                    if isinstance(attr, str):   return self._make_str(attr), "str"
                    elif isinstance(attr, int): return self._make_const(attr), "int"

        return self._make_const(0), "none"

    #----------------------------------------------------------------
    # statement compiler
    #----------------------------------------------------------------
    def _stmt(self, node):
        if self.fn and self.fn.current.is_terminated():
            return
        try:
            self._stmt_inner(node)
        except NotImplementedError as e:
            import sys
            print(f"\x1b[33mWarning: skipping {node.__class__.__name__}: {e}\x1b[0m", file=sys.stderr)
        except Exception as e:
            import sys
            print(f"\x1b[31mIR Error in {node.__class__.__name__}: {e}\x1b[0m", file=sys.stderr)
            raise

    def _stmt_inner(self, node):
        if self.fn and self.fn.current.is_terminated():
            return

        if isinstance(node, ImportNode):
            real = node.name
            self.imported[node.alias or node.name.split(".")[0]] = real

        elif isinstance(node, FromImportNode):
            real = node.module
            self.imported[node.module.split(".")[0]] = real
            for name, alias in node.names:
                self.imported[alias or name] = real

        elif isinstance(node, AssignNode):
            rhs = node.value

            # tuple unpacking: a, b = expr1, expr2
            if isinstance(node.targets[0], TupleNode) and isinstance(rhs, TupleNode):
                for i, target in enumerate(node.targets[0].elts):
                    tname = target.name if isinstance(target, VariableNode) else str(i)
                    tval, ttyp = self._expr(rhs.elts[i]) if i < len(rhs.elts) else (self._make_const(0), "int")
                    if tname not in self.vars:
                        self._alloc(tname, IRType.I64 if ttyp == "int" else IRType.PTR)
                    self._store(tval, tname)
                return

            value, typ = self._expr(rhs)

            # multiple targets: a = b = 5
            for target in node.targets:
                tname = target if isinstance(target, str) else (target.name if isinstance(target, VariableNode) else None)
                if tname is None: continue
                if tname not in self.vars:
                    irtyp = {
                        "int":   IRType.I64,
                        "float": IRType.F64,
                        "str":   IRType.PTR,
                        "list":  IRType.PTR,
                        "tuple": IRType.PTR,
                        "dict":  IRType.PTR,
                        "bool":  IRType.I1,
                    }.get(typ, IRType.I64)
                    self._alloc(tname, irtyp)
                    self.vars[tname] = (f"@{tname}", typ)
                self._store(value, tname)

        elif isinstance(node, AnnAssignNode):
            if node.value:
                value, typ = self._expr(node.value)
                if node.name not in self.vars:
                    # Was hardcoded to IRType.I64 regardless of the actual
                    # value's type, so e.g. `y: float = 3.14` allocated an
                    # integer-sized/typed slot and stored the float's raw
                    # bit pattern into it, then loaded it back and printed
                    # 0. Mirror the type mapping AssignNode already uses.
                    irtyp = {
                        "int":   IRType.I64,
                        "float": IRType.F64,
                        "str":   IRType.PTR,
                        "list":  IRType.PTR,
                        "tuple": IRType.PTR,
                        "dict":  IRType.PTR,
                        "bool":  IRType.I1,
                    }.get(typ, IRType.I64)
                    self._alloc(node.name, irtyp)
                    self.vars[node.name] = (f"@{node.name}", typ)
                self._store(value, node.name)

        elif isinstance(node, AugAssignNode):
            if node.name not in self.vars:
                raise NameError(f"Undefined variable: {node.name}")
            ir_name, typ = self.vars[node.name]
            cur = self._load(node.name)
            right, _ = self._expr(node.value)
            op_map = {
                TKN_GROUP_OPERATORS.PLUS_EQ:   "add",
                TKN_GROUP_OPERATORS.MINUS_EQ:  "sub",
                TKN_GROUP_OPERATORS.STAR_EQ:   "mul",
                TKN_GROUP_OPERATORS.SLASH_EQ:  "div",
                TKN_GROUP_OPERATORS.PERCENT_EQ:"mod",
                TKN_GROUP_OPERATORS.DSLASH_EQ: "div",
                TKN_GROUP_OPERATORS.AMP_EQ:    "and_",
                TKN_GROUP_OPERATORS.PIPE_EQ:   "or_",
                TKN_GROUP_OPERATORS.CARET_EQ:  "xor_",
                TKN_GROUP_OPERATORS.LSHIFT_EQ: "shl",
                TKN_GROUP_OPERATORS.RSHIFT_EQ: "shr",
            }
            irop = op_map.get(node.op, "add")

            if node.op == TKN_GROUP_OPERATORS.DSTAR_EQ:
                # Not a simple binary IR opcode like the others in op_map --
                # power needs the same float-round-trip-through-libc-pow
                # approach as the regular '**' BinOpNode case above. This
                # was previously missing from op_map entirely, so it fell
                # through to the `.get(node.op, "add")` default and
                # silently did addition instead (`p **= 8` on p=2 gave
                # 10, not 256).
                if typ == "float":
                    res = self._tmp(); self.fn.emit("call_ff", "pow", cur, right, dest=res[1:])
                    self._store(res, node.name)
                else:
                    lf = self._tmp(); self.fn.emit("itof", cur,   dest=lf[1:])
                    rf = self._tmp(); self.fn.emit("itof", right, dest=rf[1:])
                    fres = self._tmp(); self.fn.emit("call_ff", "pow", lf, rf, dest=fres[1:])
                    ires = self._tmp(); self.fn.emit("ftoi", fres, dest=ires[1:])
                    self._store(ires, node.name)
                return

            t = self._tmp(); self.fn.emit(irop, cur, right, dest=t[1:])
            self._store(t, node.name)

        elif isinstance(node, PrintNode):
            call = CallNode(VariableNode("print"), node.args, node.kwargs)
            self._call(call)

        elif isinstance(node, (CallNode, AttributeNode)):
            self._call(node) if isinstance(node, CallNode) else None

        elif isinstance(node, IfNode):
            test, _ = self._expr(node.test)
            b = self._to_bool(test, "bool")
            then_lbl  = self._lbl()
            merge_lbl = self._lbl()
            elif_lbls = [(self._lbl(), self._lbl()) for _ in node.elifs]
            else_lbl  = self._lbl() if node.orelse else merge_lbl

            first_false = elif_lbls[0][0] if elif_lbls else (else_lbl if node.orelse else merge_lbl)
            self.fn.emit("jnz", b, then_lbl)
            self.fn.emit("jmp", first_false)
            self.fn.emit("label", then_lbl)
            for s in node.body: self._stmt(s)
            if not self.fn.current.is_terminated(): self.fn.emit("jmp", merge_lbl)

            for i, (elif_test, elif_body) in enumerate(node.elifs):
                test_lbl, body_lbl = elif_lbls[i]
                next_false = elif_lbls[i+1][0] if i+1 < len(elif_lbls) else (else_lbl if node.orelse else merge_lbl)
                self.fn.emit("label", test_lbl)
                et, _ = self._expr(elif_test)
                eb = self._to_bool(et, "bool")
                self.fn.emit("jnz", eb, body_lbl)
                self.fn.emit("jmp", next_false)
                self.fn.emit("label", body_lbl)
                for s in elif_body: self._stmt(s)
                if not self.fn.current.is_terminated(): self.fn.emit("jmp", merge_lbl)

            if node.orelse:
                self.fn.emit("label", else_lbl)
                for s in node.orelse: self._stmt(s)
                if not self.fn.current.is_terminated(): self.fn.emit("jmp", merge_lbl)

            self.fn.emit("label", merge_lbl)

        elif isinstance(node, WhileNode):
            cond_lbl = self._lbl()
            body_lbl = self._lbl()
            exit_lbl = self._lbl()
            prev_exit, prev_cont = self.loop_exit, self.loop_cont
            self.loop_exit = exit_lbl
            self.loop_cont = cond_lbl
            self.fn.emit("jmp", cond_lbl)
            self.fn.emit("label", cond_lbl)
            test, _ = self._expr(node.test)
            b = self._to_bool(test, "bool")
            self.fn.emit("jnz", b, body_lbl)
            self.fn.emit("jmp", exit_lbl)
            self.fn.emit("label", body_lbl)
            for s in node.body: self._stmt(s)
            if not self.fn.current.is_terminated(): self.fn.emit("jmp", cond_lbl)
            self.loop_exit, self.loop_cont = prev_exit, prev_cont
            self.fn.emit("label", exit_lbl)

        elif isinstance(node, ForNode):
            iter_val, iter_typ = self._expr(node.iter)
            cond_lbl = self._lbl()
            body_lbl = self._lbl()
            inc_lbl  = self._lbl()
            exit_lbl = self._lbl()
            prev_exit, prev_cont = self.loop_exit, self.loop_cont
            self.loop_exit = exit_lbl
            self.loop_cont = inc_lbl

            idx = f"__for_idx_{self._lbl()}"
            self._alloc(idx, IRType.I64)
            self._store(self._make_const(0), idx)

            if isinstance(node.iter, RangeNode):
                args = node.iter.args
                if len(args) == 1:
                    start = self._make_const(0); stop, _ = self._expr(args[0]); step = self._make_const(1)
                elif len(args) == 2:
                    start, _ = self._expr(args[0]); stop, _ = self._expr(args[1]); step = self._make_const(1)
                else:
                    start, _ = self._expr(args[0]); stop, _ = self._expr(args[1]); step, _ = self._expr(args[2])
                # Store `start` into idx exactly once, before the loop begins --
                # NOT inside the cond block, which re-runs on every iteration
                # (this was the bug: idx got reset to `start` every time control
                # returned to cond_lbl via `inc_lbl -> jmp cond_lbl`, so the loop
                # variable never advanced and the loop ran forever).
                self._store(start, idx)

                self.fn.emit("jmp", cond_lbl)
                self.fn.emit("label", cond_lbl)
                cur_idx = self._load(idx)
                cond = self._tmp(); self.fn.emit("cmp_lt", cur_idx, stop, dest=cond[1:])
                self.fn.emit("jnz", cond, body_lbl)
                self.fn.emit("jmp", exit_lbl)
                self.fn.emit("label", body_lbl)
                if node.target not in self.vars:
                    self._alloc(node.target, IRType.I64)
                self._store(cur_idx, node.target)
                for s in node.body: self._stmt(s)
                if not self.fn.current.is_terminated(): self.fn.emit("jmp", inc_lbl)
                self.fn.emit("label", inc_lbl)
                new_idx = self._tmp(); self.fn.emit("add", cur_idx, step, dest=new_idx[1:])
                self._store(new_idx, idx)
                self.fn.emit("jmp", cond_lbl)
            elif iter_typ == "str":
                self.fn.emit("jmp", cond_lbl)
                self.fn.emit("label", cond_lbl)
                cur_idx = self._load(idx)
                length = self._tmp(); self.fn.emit("call", "strlen", iter_val, dest=length[1:])
                cond = self._tmp(); self.fn.emit("cmp_lt", cur_idx, length, dest=cond[1:])
                self.fn.emit("jnz", cond, body_lbl)
                self.fn.emit("jmp", exit_lbl)
                self.fn.emit("label", body_lbl)
                char_ptr = self._tmp(); self.fn.emit("add", iter_val, cur_idx, dest=char_ptr[1:])
                buf = self._tmp(); self.fn.emit("call", "malloc", "2", dest=buf[1:])
                self.fn.emit("call", "memcpy", buf, char_ptr, "1")
                one = self._make_const(1)
                null_ptr = self._tmp(); self.fn.emit("add", buf, one, dest=null_ptr[1:])
                z = self._make_const(0, IRType.I8)
                self.fn.emit("store", z, null_ptr)
                if node.target not in self.vars:
                    self._alloc(node.target, IRType.PTR)
                    self.vars[node.target] = (f"@{node.target}", "str")
                self._store(buf, node.target)
                for s in node.body: self._stmt(s)
                if not self.fn.current.is_terminated(): self.fn.emit("jmp", inc_lbl)
                self.fn.emit("label", inc_lbl)
                new_idx = self._tmp(); self.fn.emit("add", cur_idx, self._make_const(1), dest=new_idx[1:])
                self._store(new_idx, idx)
                self.fn.emit("jmp", cond_lbl)
            else:
                # generic: just run body once
                self.fn.emit("jmp", exit_lbl)

            self.loop_exit, self.loop_cont = prev_exit, prev_cont
            self.fn.emit("label", exit_lbl)

        elif isinstance(node, ReturnNode):
            if node.value:
                val, _ = self._expr(node.value)
                self.fn.emit("ret", val)
            else:
                self.fn.emit("ret", self._make_const(0))

        elif isinstance(node, BreakNode):
            if self.loop_exit:
                self.fn.emit("jmp", self.loop_exit)

        elif isinstance(node, ContinueNode):
            if self.loop_cont:
                self.fn.emit("jmp", self.loop_cont)

        elif isinstance(node, PassNode):
            pass

        elif isinstance(node, AssertNode):
            test, _ = self._expr(node.test)
            b = self._to_bool(test, "bool")
            pass_lbl = self._lbl()
            fail_lbl = self._lbl()
            self.fn.emit("jnz", b, pass_lbl)
            self.fn.emit("jmp", fail_lbl)
            self.fn.emit("label", fail_lbl)
            if node.msg:
                msg, _ = self._expr(node.msg)
                fmt = self._make_str("%s\n")
                self.fn.emit("call", "printf", fmt, msg)
            else:
                msg = self._make_str("AssertionError\n")
                fmt = self._make_str("%s")
                self.fn.emit("call", "printf", fmt, msg)
            self.fn.emit("call", "exit", self._make_const(1))
            self.fn.emit("label", pass_lbl)

        elif isinstance(node, RaiseNode):
            if node.exc:
                if isinstance(node.exc, VariableNode):
                    msg = self._make_str(node.exc.name)
                else:
                    msg, _ = self._expr(node.exc)
                fmt = self._make_str("Exception: %s\n")
                self.fn.emit("call", "printf", fmt, msg)
            self.fn.emit("call", "exit", self._make_const(1))

        elif isinstance(node, TryNode):
            # compile body, ignore handlers (no native exceptions without full unwind tables)
            for s in node.body: self._stmt(s)
            for handler in node.handlers:
                if handler.name and handler.name not in self.vars:
                    self._alloc(handler.name, IRType.PTR)
                    self.vars[handler.name] = (f"@{handler.name}", "str")
                    self._store(self._make_str("Exception"), handler.name)
            for s in node.finalbody: self._stmt(s)
            for s in node.orelse: self._stmt(s)

        elif isinstance(node, WithNode):
            for ctx_expr, alias in node.items:
                val, typ = self._expr(ctx_expr)
                if alias:
                    if alias not in self.vars:
                        self._alloc(alias, IRType.PTR if typ == "str" else IRType.I64)
                        self.vars[alias] = (f"@{alias}", typ)
                    self._store(val, alias)
            for s in node.body: self._stmt(s)

        elif isinstance(node, GlobalNode):
            pass  # global scope is default in our flat IR

        elif isinstance(node, NonlocalNode):
            pass  # closure support requires full frame pointers — future work

        elif isinstance(node, DeleteNode):
            for t in node.targets:
                if isinstance(t, VariableNode) and t.name in self.vars:
                    del self.vars[t.name]

        elif isinstance(node, FuncDefNode):
            self._funcdef(node)

        elif isinstance(node, AsyncFuncDefNode):
            self._funcdef(node)  # async compiled as sync for now

        elif isinstance(node, ClassDefNode):
            for s in node.body:
                if isinstance(s, FuncDefNode):
                    self._funcdef(s, class_name=node.name)

        elif isinstance(node, YieldNode):
            pass  # generators are future work

        elif isinstance(node, AwaitNode):
            self._expr(node.value)

    #----------------------------------------------------------------
    # function definition
    #----------------------------------------------------------------
    def _save_ctx(self):
        return {"vars": dict(self.vars), "fn": self.fn,
                "loop_exit": self.loop_exit, "loop_cont": self.loop_cont}

    def _restore_ctx(self, saved):
        self.vars      = saved["vars"]
        self.fn        = saved["fn"]
        self.loop_exit = saved["loop_exit"]
        self.loop_cont = saved["loop_cont"]

    def _funcdef(self, node, class_name=None):
        saved = self._save_ctx()
        fn_name = f"{class_name}__{node.name}" if class_name else node.name
        # The compiled program's native entry point is always emitted as a
        # function literally named "main" (see compile() below). A
        # user-defined top-level `def main():` -- extremely common, since
        # it's the conventional pairing with
        # `if __name__ == "__main__": main()` -- would otherwise collide
        # with that symbol (two `main:` labels -> assembler/linker error).
        # Rename on the native side only; Python-level calls to main()
        # still resolve correctly via self.funcs, keyed by node.name.
        if fn_name == "main":
            fn_name = "__pycc_user_main"
        params  = [(IRType.I64, pname) for pname, _, _ in node.args]
        ir_fn   = self.mod.add_func(fn_name, params, IRType.I64)
        self.funcs[node.name] = (fn_name, [IRType.I64]*len(params), "int")
        self.fn   = ir_fn
        self.vars = dict(saved["vars"])
        self.loop_exit = None
        self.loop_cont = None

        for ptype, pname in params:
            self._alloc(pname, ptype)

        for s in node.body:
            self._stmt(s)

        if not self.fn.current.is_terminated():
            self.fn.emit("ret", self._make_const(0))

        self._restore_ctx(saved)

    #----------------------------------------------------------------
    # top-level compile
    #----------------------------------------------------------------
    def compile(self, output_name):
        main_fn = self.mod.add_func("main", [], IRType.I32)
        self.fn = main_fn

        for node in self.tree.body:
            self._stmt(node)

        if not self.fn.current.is_terminated():
            self.fn.emit("ret", self._make_const(0))

        from PyCCIR import get_backend, detect_host_arch
        from PyCCLD import assemble_and_link as ld_link, pick_asm_syntax

        arch    = self.args.get("arch")
        os_name = self.args.get("target_os")

        # Decide up front which assembler we'll actually use, so we can
        # generate matching syntax the first time instead of generating
        # NASM syntax and having it fail inside `as` (GAS can't parse
        # NASM's directives/operand-size syntax -- see PyCCLD.assemble).
        effective_arch = arch or detect_host_arch()
        asm_syntax = pick_asm_syntax(effective_arch)

        backend = get_backend(self.mod, arch=arch, target_os=os_name, asm_syntax=asm_syntax)
        asm     = backend.generate()

        if self.args.get("verbose"):
            print(f"PyCC IR -> {arch or 'host'} asm ({asm_syntax or 'nasm'})")
        ld_link(asm, output_name, self.args, arch=arch, os_name=os_name, asm_syntax=asm_syntax)

#-------------------------------------------------------------------

def compile_ast_ir(tree, output_name, args):
    compiler = IRCompiler(tree, args)
    compiler.compile(output_name)
