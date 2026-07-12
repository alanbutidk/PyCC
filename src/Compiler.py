import subprocess
import platform
import importlib
import llvmlite.ir as ir
import llvmlite.binding as llvm
from Tokenize import BUILTIN_EXCEPTIONS, EXCEPTION_TOKEN_NAME
from PyCCParser import *

llvm.initialize_native_target()
llvm.initialize_native_asmprinter()

INT1 = ir.IntType(1)
INT8 = ir.IntType(8)
INT32 = ir.IntType(32)
INT64 = ir.IntType(64)
DOUBLE = ir.DoubleType()
VOID = ir.VoidType()
PTR = ir.PointerType(INT8)

class Compiler:
    def __init__(self, tree, args):
        self.tree = tree
        self.args = args
        self.module = ir.Module(name="program")
        self.module.triple = llvm.get_default_triple()
        self.builder = None
        self.vars = {}
        self.funcs = {}
        self.imported = {}
        self.current_func = None
        self.loop_exit_block = None
        self.loop_continue_block = None
        self._declare_externs()

    def _declare_externs(self):
        self.printf = ir.Function(self.module, ir.FunctionType(INT32, [PTR], var_arg=True), name="printf")
        self.malloc = ir.Function(self.module, ir.FunctionType(PTR, [INT64]), name="malloc")
        self.free = ir.Function(self.module, ir.FunctionType(VOID, [PTR]), name="free")
        self.memcpy = ir.Function(self.module, ir.FunctionType(PTR, [PTR, PTR, INT64]), name="memcpy")
        self.strlen = ir.Function(self.module, ir.FunctionType(INT64, [PTR]), name="strlen")
        self.strcmp = ir.Function(self.module, ir.FunctionType(INT32, [PTR, PTR]), name="strcmp")
        self.sprintf = ir.Function(self.module, ir.FunctionType(INT32, [PTR, PTR], var_arg=True), name="sprintf")
        self.strcat = ir.Function(self.module, ir.FunctionType(PTR, [PTR, PTR]), name="strcat")
        self.strcpy = ir.Function(self.module, ir.FunctionType(PTR, [PTR, PTR]), name="strcpy")
        self.pow_f = ir.Function(self.module, ir.FunctionType(DOUBLE, [DOUBLE, DOUBLE]), name="pow")
        self.exit_f = ir.Function(self.module, ir.FunctionType(VOID, [INT32]), name="exit")

    def _make_string(self, s):
        s = s + "\0"
        buf = bytearray(s.encode("utf8"))
        t = ir.ArrayType(INT8, len(buf))
        g = ir.GlobalVariable(self.module, t, name=f"str_{len(list(self.module.global_values))}")
        g.linkage = "internal"
        g.global_constant = True
        g.initializer = ir.Constant(t, buf)
        return self.builder.gep(g, [ir.Constant(INT32, 0), ir.Constant(INT32, 0)])

    def _alloc_string(self, s_ptr):
        size = self.builder.call(self.strlen, [s_ptr])
        size_plus = self.builder.add(size, ir.Constant(INT64, 1))
        buf = self.builder.call(self.malloc, [size_plus])
        self.builder.call(self.strcpy, [buf, s_ptr])
        return buf

    def _coerce(self, val, from_typ, to_typ):
        if from_typ == to_typ:
            return val, to_typ
        if from_typ == "int" and to_typ == "float":
            return self.builder.sitofp(val, DOUBLE), "float"
        if from_typ == "float" and to_typ == "int":
            return self.builder.fptosi(val, INT64), "int"
        return val, from_typ

    def _compile_expr(self, node):
        if isinstance(node, IntNode):
            return ir.Constant(INT64, node.value), "int"

        elif isinstance(node, FloatNode):
            return ir.Constant(DOUBLE, node.value), "float"

        elif isinstance(node, StringNode):
            raw = node.value.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
            return self._make_string(raw), "str"

        elif isinstance(node, FStringNode):
            # Build f-string by concatenating parts
            # Start with an empty 1024-byte buffer
            buf = self.builder.call(self.malloc, [ir.Constant(INT64, 1024)])
            # Store null terminator at start
            self.builder.store(ir.Constant(INT8, 0), buf)
            for is_expr, part in node.parts:
                if not is_expr:
                    raw = part.replace("\\n", "\n").replace("\\t", "\t")
                    s_ptr = self._make_string(raw)
                    self.builder.call(self.strcat, [buf, s_ptr])
                else:
                    # parse and compile the expression inside {}
                    from Tokenize import tokenize as _tok
                    from PyCCParser import parse as _parse
                    sub_tokens = _tok(part)
                    sub_tree = _parse(sub_tokens)
                    if sub_tree.body:
                        val, typ = self._compile_expr(sub_tree.body[0])
                        if typ == "int":
                            tmp = self.builder.call(self.malloc, [ir.Constant(INT64, 32)])
                            self.builder.store(ir.Constant(INT8, 0), tmp)
                            fmt = self._make_string("%lld")
                            self.builder.call(self.sprintf, [tmp, fmt, val])
                            self.builder.call(self.strcat, [buf, tmp])
                        elif typ == "float":
                            tmp = self.builder.call(self.malloc, [ir.Constant(INT64, 64)])
                            self.builder.store(ir.Constant(INT8, 0), tmp)
                            fmt = self._make_string("%g")
                            self.builder.call(self.sprintf, [tmp, fmt, val])
                            self.builder.call(self.strcat, [buf, tmp])
                        elif typ == "str":
                            self.builder.call(self.strcat, [buf, val])
                        elif typ == "bool":
                            val_ext = self.builder.zext(val, INT64)
                            true_s = self._make_string("True")
                            false_s = self._make_string("False")
                            s = self.builder.select(
                                self.builder.icmp_signed("!=", val_ext, ir.Constant(INT64, 0)),
                                true_s, false_s)
                            self.builder.call(self.strcat, [buf, s])
            return buf, "str"

        elif isinstance(node, BoolNode):
            return ir.Constant(INT1, int(node.value)), "bool"

        elif isinstance(node, NoneNode):
            return ir.Constant(INT64, 0), "none"

        elif isinstance(node, VariableNode):
            if node.name not in self.vars:
                raise NameError(f"Undefined variable: {node.name}")
            ptr, typ = self.vars[node.name]
            return self.builder.load(ptr), typ

        elif isinstance(node, AttributeNode):
            if isinstance(node.obj, VariableNode):
                var_name = node.obj.name
                # resolve alias to real module name
                real_mod = self.imported.get(var_name)
                if real_mod and isinstance(real_mod, str):
                    try:
                        mod = importlib.import_module(real_mod)
                        val = getattr(mod, node.attr, None)
                        if val is not None and not callable(val):
                            if isinstance(val, str):
                                return self._make_string(val), "str"
                            elif isinstance(val, int):
                                return ir.Constant(INT64, val), "int"
                            elif isinstance(val, float):
                                return ir.Constant(DOUBLE, val), "float"
                    except Exception:
                        pass
                # runtime variable attribute access (e.g. a.returncode)
                # look up the variable and try to access its known fields
                if var_name in self.vars:
                    ptr, typ = self.vars[var_name]
                    val = self.builder.load(ptr)
                    # for struct-like runtime objects we store as int (returncode)
                    # or str (stdout/stderr). Since we dont have real structs yet,
                    # store companion vars: varname__attr
                    companion = f"{var_name}__{node.attr}"
                    if companion in self.vars:
                        cptr, ctyp = self.vars[companion]
                        return self.builder.load(cptr), ctyp
                    # fallback: return 0
                    return ir.Constant(INT64, 0), "int"
            # fallback
            return ir.Constant(INT64, 0), "int"

        elif isinstance(node, UnaryOpNode):
            operand, typ = self._compile_expr(node.operand)
            if node.op == TKN_GROUP_OPERATORS.MINUS:
                if typ == "float":
                    return self.builder.fsub(ir.Constant(DOUBLE, 0.0), operand), typ
                return self.builder.neg(operand), typ
            elif node.op == TKN_GROUP_OPERATORS.TILDE:
                return self.builder.not_(operand), typ
            elif node.op == TKN_GROUP_KEYWORDS.NOT:
                if typ == "bool":
                    return self.builder.not_(operand), "bool"
                cmp = self.builder.icmp_signed("==", operand, ir.Constant(INT64, 0))
                return cmp, "bool"

        elif isinstance(node, BinOpNode):
            left, lt = self._compile_expr(node.left)
            right, rt = self._compile_expr(node.right)
            if lt == "str" or rt == "str":
                if node.op == TKN_GROUP_OPERATORS.PLUS:
                    l_ptr = left if lt == "str" else self._int_to_str(left)
                    r_ptr = right if rt == "str" else self._int_to_str(right)
                    l_len = self.builder.call(self.strlen, [l_ptr])
                    r_len = self.builder.call(self.strlen, [r_ptr])
                    total = self.builder.add(self.builder.add(l_len, r_len), ir.Constant(INT64, 1))
                    buf = self.builder.call(self.malloc, [total])
                    self.builder.call(self.strcpy, [buf, l_ptr])
                    self.builder.call(self.strcat, [buf, r_ptr])
                    return buf, "str"
            if lt != rt:
                if lt == "int" and rt == "float":
                    left = self.builder.sitofp(left, DOUBLE)
                    lt = "float"
                elif lt == "float" and rt == "int":
                    right = self.builder.sitofp(right, DOUBLE)
                    rt = "float"
            if lt == "float":
                if node.op == TKN_GROUP_OPERATORS.PLUS:
                    return self.builder.fadd(left, right), "float"
                elif node.op == TKN_GROUP_OPERATORS.MINUS:
                    return self.builder.fsub(left, right), "float"
                elif node.op == TKN_GROUP_OPERATORS.STAR:
                    return self.builder.fmul(left, right), "float"
                elif node.op == TKN_GROUP_OPERATORS.SLASH:
                    return self.builder.fdiv(left, right), "float"
                elif node.op == TKN_GROUP_OPERATORS.DSTAR:
                    return self.builder.call(self.pow_f, [left, right]), "float"
                elif node.op == TKN_GROUP_OPERATORS.DSLASH:
                    d = self.builder.fdiv(left, right)
                    return self.builder.fptosi(d, INT64), "int"
                elif node.op == TKN_GROUP_OPERATORS.PERCENT:
                    return self.builder.frem(left, right), "float"
            else:
                if node.op == TKN_GROUP_OPERATORS.PLUS:
                    return self.builder.add(left, right), lt
                elif node.op == TKN_GROUP_OPERATORS.MINUS:
                    return self.builder.sub(left, right), lt
                elif node.op == TKN_GROUP_OPERATORS.STAR:
                    return self.builder.mul(left, right), lt
                elif node.op == TKN_GROUP_OPERATORS.SLASH:
                    lf = self.builder.sitofp(left, DOUBLE)
                    rf = self.builder.sitofp(right, DOUBLE)
                    return self.builder.fdiv(lf, rf), "float"
                elif node.op == TKN_GROUP_OPERATORS.DSLASH:
                    return self.builder.sdiv(left, right), lt
                elif node.op == TKN_GROUP_OPERATORS.PERCENT:
                    return self.builder.srem(left, right), lt
                elif node.op == TKN_GROUP_OPERATORS.DSTAR:
                    lf = self.builder.sitofp(left, DOUBLE)
                    rf = self.builder.sitofp(right, DOUBLE)
                    res = self.builder.call(self.pow_f, [lf, rf])
                    return self.builder.fptosi(res, INT64), "int"
                elif node.op == TKN_GROUP_OPERATORS.AMP:
                    return self.builder.and_(left, right), lt
                elif node.op == TKN_GROUP_OPERATORS.PIPE:
                    return self.builder.or_(left, right), lt
                elif node.op == TKN_GROUP_OPERATORS.CARET:
                    return self.builder.xor(left, right), lt
                elif node.op == TKN_GROUP_OPERATORS.LSHIFT:
                    return self.builder.shl(left, right), lt
                elif node.op == TKN_GROUP_OPERATORS.RSHIFT:
                    return self.builder.ashr(left, right), lt

        elif isinstance(node, CompareNode):
            left, lt = self._compile_expr(node.left)
            result = None
            for op, comp_node in zip(node.ops, node.comparators):
                right, rt = self._compile_expr(comp_node)
                if lt == "float" or rt == "float":
                    if lt == "int":
                        left = self.builder.sitofp(left, DOUBLE)
                    if rt == "int":
                        right = self.builder.sitofp(right, DOUBLE)
                    cmp_map = {
                        TKN_GROUP_OPERATORS.EQEQ: "==",
                        TKN_GROUP_OPERATORS.NEQ: "!=",
                        TKN_GROUP_OPERATORS.LT: "<",
                        TKN_GROUP_OPERATORS.GT: ">",
                        TKN_GROUP_OPERATORS.LEQ: "<=",
                        TKN_GROUP_OPERATORS.GEQ: ">=",
                    }
                    cmp = self.builder.fcmp_ordered(cmp_map[op], left, right)
                elif lt == "str":
                    cmp_result = self.builder.call(self.strcmp, [left, right])
                    zero = ir.Constant(INT32, 0)
                    if op == TKN_GROUP_OPERATORS.EQEQ:
                        cmp = self.builder.icmp_signed("==", cmp_result, zero)
                    elif op == TKN_GROUP_OPERATORS.NEQ:
                        cmp = self.builder.icmp_signed("!=", cmp_result, zero)
                    else:
                        cmp = self.builder.icmp_signed("==", cmp_result, zero)
                else:
                    cmp_map = {
                        TKN_GROUP_OPERATORS.EQEQ: "==",
                        TKN_GROUP_OPERATORS.NEQ: "!=",
                        TKN_GROUP_OPERATORS.LT: "<",
                        TKN_GROUP_OPERATORS.GT: ">",
                        TKN_GROUP_OPERATORS.LEQ: "<=",
                        TKN_GROUP_OPERATORS.GEQ: ">=",
                        TKN_GROUP_KEYWORDS.IS: "==",
                        TKN_GROUP_KEYWORDS.IS_NOT: "!=",
                    }
                    cmp = self.builder.icmp_signed(cmp_map.get(op, "=="), left, right)
                result = cmp if result is None else self.builder.and_(result, cmp)
                left = right
                lt = rt
            return result, "bool"

        elif isinstance(node, BoolOpNode):
            if node.op == TKN_GROUP_KEYWORDS.AND:
                left, lt = self._compile_expr(node.values[0])
                left_bool = self._to_bool(left, lt)
                for v in node.values[1:]:
                    right, rt = self._compile_expr(v)
                    right_bool = self._to_bool(right, rt)
                    left_bool = self.builder.and_(left_bool, right_bool)
                return left_bool, "bool"
            elif node.op == TKN_GROUP_KEYWORDS.OR:
                left, lt = self._compile_expr(node.values[0])
                left_bool = self._to_bool(left, lt)
                for v in node.values[1:]:
                    right, rt = self._compile_expr(v)
                    right_bool = self._to_bool(right, rt)
                    left_bool = self.builder.or_(left_bool, right_bool)
                return left_bool, "bool"

        elif isinstance(node, IfExpNode):
            test, _ = self._compile_expr(node.test)
            test_bool = self._to_bool(test, "bool")
            then_val, then_typ = self._compile_expr(node.body)
            else_val, else_typ = self._compile_expr(node.orelse)
            return self.builder.select(test_bool, then_val, else_val), then_typ

        elif isinstance(node, CallNode):
            return self._compile_call(node)

        elif isinstance(node, SubscriptNode):
            obj, typ = self._compile_expr(node.obj)
            idx, _ = self._compile_expr(node.index)
            if typ == "str":
                ptr = self.builder.gep(obj, [idx])
                ch = self.builder.load(ptr)
                buf = self.builder.call(self.malloc, [ir.Constant(INT64, 2)])
                self.builder.store(ch, buf)
                null_ptr = self.builder.gep(buf, [ir.Constant(INT64, 1)])
                self.builder.store(ir.Constant(INT8, 0), null_ptr)
                return buf, "str"
            raise NotImplementedError("Subscript only supported on str currently")

        elif isinstance(node, RangeNode):
            # Evaluate and return range args as a tuple of LLVM values
            # We store as a special "range" type with (start, stop, step) in a malloc'd 3-int64 buffer
            compiled = []
            for a in node.args:
                v, _ = self._compile_expr(a)
                compiled.append(v)
            if len(compiled) == 1:
                start = ir.Constant(INT64, 0)
                stop = compiled[0]
                step = ir.Constant(INT64, 1)
            elif len(compiled) == 2:
                start, stop = compiled
                step = ir.Constant(INT64, 1)
            else:
                start, stop, step = compiled[0], compiled[1], compiled[2]
            buf = self.builder.call(self.malloc, [ir.Constant(INT64, 24)])
            p0 = self.builder.bitcast(buf, ir.PointerType(INT64))
            self.builder.store(start, p0)
            p1 = self.builder.gep(p0, [ir.Constant(INT64, 1)])
            self.builder.store(stop, p1)
            p2 = self.builder.gep(p0, [ir.Constant(INT64, 2)])
            self.builder.store(step, p2)
            return buf, "range"

        elif isinstance(node, ListNode):
            size = ir.Constant(INT64, len(node.elts) * 8)
            buf = self.builder.call(self.malloc, [size])
            for idx, elt in enumerate(node.elts):
                val, typ = self._compile_expr(elt)
                if typ != "int":
                    val, _ = self._coerce(val, typ, "int")
                ptr = self.builder.gep(buf, [ir.Constant(INT64, idx * 8)])
                int_ptr = self.builder.bitcast(ptr, ir.PointerType(INT64))
                self.builder.store(val, int_ptr)
            return buf, "list"

        elif isinstance(node, TupleNode):
            size = ir.Constant(INT64, len(node.elts) * 8)
            buf = self.builder.call(self.malloc, [size])
            for idx, elt in enumerate(node.elts):
                val, typ = self._compile_expr(elt)
                if typ != "int":
                    val, _ = self._coerce(val, typ, "int")
                ptr = self.builder.gep(buf, [ir.Constant(INT64, idx * 8)])
                int_ptr = self.builder.bitcast(ptr, ir.PointerType(INT64))
                self.builder.store(val, int_ptr)
            return buf, "tuple"

        elif isinstance(node, DictNode):
            return ir.Constant(INT64, 0), "dict"

        elif isinstance(node, LambdaNode):
            return ir.Constant(INT64, 0), "lambda"

        raise NotImplementedError(f"Unsupported expr: {node.__class__.__name__}")

    def _int_to_str(self, val):
        buf = self.builder.call(self.malloc, [ir.Constant(INT64, 32)])
        fmt = self._make_string("%lld")
        self.builder.call(self.sprintf, [buf, fmt, val])
        return buf

    def _float_to_str(self, val):
        buf = self.builder.call(self.malloc, [ir.Constant(INT64, 64)])
        fmt = self._make_string("%f")
        self.builder.call(self.sprintf, [buf, fmt, val])
        return buf

    def _to_bool(self, val, typ):
        if typ == "bool":
            return val
        elif typ == "int":
            return self.builder.icmp_signed("!=", val, ir.Constant(INT64, 0))
        elif typ == "float":
            return self.builder.fcmp_ordered("!=", val, ir.Constant(DOUBLE, 0.0))
        elif typ == "str":
            length = self.builder.call(self.strlen, [val])
            return self.builder.icmp_signed("!=", length, ir.Constant(INT64, 0))
        return self.builder.icmp_signed("!=", val, ir.Constant(INT64, 0))

    def _compile_call(self, node):
        if isinstance(node.func, AttributeNode):
            if isinstance(node.func.obj, VariableNode):
                var_name = node.func.obj.name
                real_mod = self.imported.get(var_name)
                if real_mod and isinstance(real_mod, str):
                    try:
                        mod = importlib.import_module(real_mod)
                        attr = getattr(mod, node.func.attr, None)
                        if callable(attr):
                            # compile-time call with Python args where possible
                            py_args = []
                            ok = True
                            for a in node.args:
                                if isinstance(a, (IntNode, FloatNode, StringNode, BoolNode)):
                                    py_args.append(a.value)
                                else:
                                    ok = False; break
                            py_kwargs = {}
                            for k, v in node.kwargs.items():
                                if isinstance(v, (IntNode, FloatNode, StringNode, BoolNode)):
                                    py_kwargs[k] = v.value
                                elif isinstance(v, BoolNode):
                                    py_kwargs[k] = v.value
                            if ok:
                                try:
                                    result = attr(*py_args, **py_kwargs)
                                    if isinstance(result, str):
                                        return self._make_string(result), "str"
                                    elif isinstance(result, int):
                                        return ir.Constant(INT64, result), "int"
                                    elif isinstance(result, float):
                                        return ir.Constant(DOUBLE, result), "float"
                                except Exception:
                                    pass
                            # for calls we cant eval at compile time (e.g. subprocess.run)
                            # store the result's known integer fields as companion vars
                            # returncode companion stored as 0 by default
                            return ir.Constant(INT64, 0), "none"
                        elif attr is not None:
                            if isinstance(attr, str):
                                return self._make_string(attr), "str"
                            elif isinstance(attr, int):
                                return ir.Constant(INT64, attr), "int"
                    except Exception:
                        pass
            return ir.Constant(INT64, 0), "none"
        if isinstance(node.func, VariableNode):
            name = node.func.name
            if name in self.funcs:
                fn, arg_types, ret_type = self.funcs[name]
                compiled_args = []
                for arg in node.args:
                    v, t = self._compile_expr(arg)
                    compiled_args.append(v)
                result = self.builder.call(fn, compiled_args)
                return result, ret_type
        return ir.Constant(INT64, 0), "none"

    def _compile_stmt(self, node):
        if self.builder and self.builder.block and self.builder.block.is_terminated:
            return

        if isinstance(node, ImportNode):
            real = node.name.split(".")[0]
            self.imported[real] = real
            if node.alias:
                self.imported[node.alias] = real  # alias -> real name

        elif isinstance(node, FromImportNode):
            real = node.module.split(".")[0]
            self.imported[real] = real

        elif isinstance(node, AssignNode):
            rhs = node.value
            name = node.targets[0] if isinstance(node.targets[0], str) else node.targets[0].name

            # special case: a = module.func(...) where we can run it at compile time
            # and store all result attributes as companion vars (e.g. a__returncode)
            if isinstance(rhs, CallNode) and isinstance(rhs.func, AttributeNode):
                if isinstance(rhs.func.obj, VariableNode):
                    real_mod = self.imported.get(rhs.func.obj.name)
                    if real_mod and isinstance(real_mod, str):
                        try:
                            mod = importlib.import_module(real_mod)
                            attr = getattr(mod, rhs.func.attr, None)
                            if callable(attr):
                                # try to call with compile-time args
                                py_args = []
                                py_kwargs = {}
                                ok = True
                                for a in rhs.args:
                                    if isinstance(a, (IntNode, FloatNode, StringNode, BoolNode)):
                                        py_args.append(a.value)
                                    elif isinstance(a, ListNode):
                                        # list of string literals
                                        lst = []
                                        for e in a.elts:
                                            if isinstance(e, StringNode):
                                                lst.append(e.value)
                                            else:
                                                ok = False; break
                                        if ok:
                                            py_args.append(lst)
                                    else:
                                        ok = False; break
                                for k, v in rhs.kwargs.items():
                                    if isinstance(v, (IntNode, FloatNode, StringNode)):
                                        py_kwargs[k] = v.value
                                    elif isinstance(v, BoolNode):
                                        py_kwargs[k] = v.value
                                    elif isinstance(v, (TKN_GROUP_DATATYPES.__class__,)):
                                        pass
                                    else:
                                        # skip unknown kwargs, just pass True as default
                                        py_kwargs[k] = True
                                if ok:
                                    try:
                                        result = attr(*py_args, **py_kwargs)
                                        # store a dummy int var for the object itself
                                        ptr = self.builder.alloca(INT64, name=name)
                                        self.builder.store(ir.Constant(INT64, 0), ptr)
                                        self.vars[name] = (ptr, "none")
                                        # store all int/str/float attributes as companions
                                        for field in dir(result):
                                            if field.startswith("_"):
                                                continue
                                            try:
                                                fval = getattr(result, field)
                                                companion = f"{name}__{field}"
                                                if isinstance(fval, int):
                                                    cptr = self.builder.alloca(INT64, name=companion)
                                                    self.builder.store(ir.Constant(INT64, fval), cptr)
                                                    self.vars[companion] = (cptr, "int")
                                                elif isinstance(fval, str):
                                                    cptr = self.builder.alloca(PTR, name=companion)
                                                    self.builder.store(self._make_string(fval), cptr)
                                                    self.vars[companion] = (cptr, "str")
                                                elif isinstance(fval, float):
                                                    cptr = self.builder.alloca(DOUBLE, name=companion)
                                                    self.builder.store(ir.Constant(DOUBLE, fval), cptr)
                                                    self.vars[companion] = (cptr, "float")
                                            except Exception:
                                                pass
                                        return  # done
                                    except Exception:
                                        pass
                        except Exception:
                            pass

            value, typ = self._compile_expr(rhs)
            if name not in self.vars:
                if typ == "int":
                    ptr = self.builder.alloca(INT64, name=name)
                elif typ == "float":
                    ptr = self.builder.alloca(DOUBLE, name=name)
                elif typ in ("str", "list", "tuple", "dict"):
                    ptr = self.builder.alloca(PTR, name=name)
                elif typ == "bool":
                    ptr = self.builder.alloca(INT1, name=name)
                else:
                    ptr = self.builder.alloca(INT64, name=name)
                self.vars[name] = (ptr, typ)
            ptr, _ = self.vars[name]
            self.builder.store(value, ptr)

        elif isinstance(node, AnnAssignNode):
            if node.value:
                value, typ = self._compile_expr(node.value)
                if node.name not in self.vars:
                    if typ == "int":
                        ptr = self.builder.alloca(INT64, name=node.name)
                    elif typ == "float":
                        ptr = self.builder.alloca(DOUBLE, name=node.name)
                    else:
                        ptr = self.builder.alloca(INT64, name=node.name)
                    self.vars[node.name] = (ptr, typ)
                ptr, _ = self.vars[node.name]
                self.builder.store(value, ptr)

        elif isinstance(node, AugAssignNode):
            if node.name not in self.vars:
                raise NameError(f"Undefined variable: {node.name}")
            ptr, typ = self.vars[node.name]
            current = self.builder.load(ptr)
            right, _ = self._compile_expr(node.value)
            result = current
            if node.op == TKN_GROUP_OPERATORS.PLUS_EQ:
                result = self.builder.add(current, right)
            elif node.op == TKN_GROUP_OPERATORS.MINUS_EQ:
                result = self.builder.sub(current, right)
            elif node.op == TKN_GROUP_OPERATORS.STAR_EQ:
                result = self.builder.mul(current, right)
            elif node.op == TKN_GROUP_OPERATORS.SLASH_EQ:
                result = self.builder.sdiv(current, right)
            elif node.op == TKN_GROUP_OPERATORS.PERCENT_EQ:
                result = self.builder.srem(current, right)
            elif node.op == TKN_GROUP_OPERATORS.DSLASH_EQ:
                result = self.builder.sdiv(current, right)
            elif node.op == TKN_GROUP_OPERATORS.AMP_EQ:
                result = self.builder.and_(current, right)
            elif node.op == TKN_GROUP_OPERATORS.PIPE_EQ:
                result = self.builder.or_(current, right)
            elif node.op == TKN_GROUP_OPERATORS.CARET_EQ:
                result = self.builder.xor(current, right)
            elif node.op == TKN_GROUP_OPERATORS.LSHIFT_EQ:
                result = self.builder.shl(current, right)
            elif node.op == TKN_GROUP_OPERATORS.RSHIFT_EQ:
                result = self.builder.ashr(current, right)
            self.builder.store(result, ptr)

        elif isinstance(node, PrintNode):
            for idx, arg in enumerate(node.args):
                val, typ = self._compile_expr(arg)
                sep = self._make_string(" ") if idx < len(node.args) - 1 else None
                if typ == "int":
                    self.builder.call(self.printf, [self._make_string("%lld"), val])
                elif typ == "float":
                    self.builder.call(self.printf, [self._make_string("%g"), val])
                elif typ == "str":
                    self.builder.call(self.printf, [self._make_string("%s"), val])
                elif typ == "bool":
                    val = self.builder.zext(val, INT64)
                    true_str = self._make_string("True")
                    false_str = self._make_string("False")
                    str_val = self.builder.select(
                        self.builder.icmp_signed("!=", val, ir.Constant(INT64, 0)),
                        true_str, false_str)
                    self.builder.call(self.printf, [self._make_string("%s"), str_val])
                else:
                    self.builder.call(self.printf, [self._make_string("%lld"), val])
                if sep:
                    self.builder.call(self.printf, [sep])
            self.builder.call(self.printf, [self._make_string("\n")])

        elif isinstance(node, CallNode):
            self._compile_call(node)

        elif isinstance(node, IfNode):
            test, _ = self._compile_expr(node.test)
            test_bool = self._to_bool(test, "bool")
            fn = self.builder.function
            then_block = fn.append_basic_block("if.then")
            merge_block = fn.append_basic_block("if.merge")
            elif_blocks = []
            for i, (elif_test, elif_body) in enumerate(node.elifs):
                elif_blocks.append((fn.append_basic_block(f"elif.{i}.test"),
                                    fn.append_basic_block(f"elif.{i}.body")))
            else_block = fn.append_basic_block("if.else") if node.orelse else None
            first_false = elif_blocks[0][0] if elif_blocks else (else_block if else_block else merge_block)
            self.builder.cbranch(test_bool, then_block, first_false)
            self.builder.position_at_end(then_block)
            for s in node.body:
                self._compile_stmt(s)
            if not self.builder.block.is_terminated:
                self.builder.branch(merge_block)
            for i, (elif_test, elif_body) in enumerate(node.elifs):
                test_blk, body_blk = elif_blocks[i]
                next_false = elif_blocks[i+1][0] if i+1 < len(elif_blocks) else (else_block if else_block else merge_block)
                self.builder.position_at_end(test_blk)
                et, _ = self._compile_expr(elif_test)
                et_bool = self._to_bool(et, "bool")
                self.builder.cbranch(et_bool, body_blk, next_false)
                self.builder.position_at_end(body_blk)
                for s in elif_body:
                    self._compile_stmt(s)
                if not self.builder.block.is_terminated:
                    self.builder.branch(merge_block)
            if else_block:
                self.builder.position_at_end(else_block)
                for s in node.orelse:
                    self._compile_stmt(s)
                if not self.builder.block.is_terminated:
                    self.builder.branch(merge_block)
            self.builder.position_at_end(merge_block)

        elif isinstance(node, WhileNode):
            fn = self.builder.function
            cond_block = fn.append_basic_block("while.cond")
            body_block = fn.append_basic_block("while.body")
            exit_block = fn.append_basic_block("while.exit")
            prev_exit = self.loop_exit_block
            prev_cont = self.loop_continue_block
            self.loop_exit_block = exit_block
            self.loop_continue_block = cond_block
            self.builder.branch(cond_block)
            self.builder.position_at_end(cond_block)
            test, _ = self._compile_expr(node.test)
            test_bool = self._to_bool(test, "bool")
            self.builder.cbranch(test_bool, body_block, exit_block)
            self.builder.position_at_end(body_block)
            for s in node.body:
                self._compile_stmt(s)
            if not self.builder.block.is_terminated:
                self.builder.branch(cond_block)
            self.loop_exit_block = prev_exit
            self.loop_continue_block = prev_cont
            self.builder.position_at_end(exit_block)

        elif isinstance(node, ForNode):
            fn = self.builder.function
            iter_val, iter_typ = self._compile_expr(node.iter)

            prev_exit = self.loop_exit_block
            prev_cont = self.loop_continue_block

            cond_block = fn.append_basic_block("for.cond")
            body_block = fn.append_basic_block("for.body")
            inc_block  = fn.append_basic_block("for.inc")
            exit_block = fn.append_basic_block("for.exit")
            self.loop_exit_block    = exit_block
            self.loop_continue_block = inc_block

            target = node.target  # str or list of str

            if iter_typ == "range":
                # load start/stop/step from the 3-int64 buffer
                p0 = self.builder.bitcast(iter_val, ir.PointerType(INT64))
                p1 = self.builder.gep(p0, [ir.Constant(INT64, 1)])
                p2 = self.builder.gep(p0, [ir.Constant(INT64, 2)])
                range_start = self.builder.load(p0)
                range_stop  = self.builder.load(p1)
                range_step  = self.builder.load(p2)

                # loop var
                var_name = target if isinstance(target, str) else target[0]
                if var_name not in self.vars:
                    ptr = self.builder.alloca(INT64, name=var_name)
                    self.vars[var_name] = (ptr, "int")
                self.builder.store(range_start, self.vars[var_name][0])
                self.builder.branch(cond_block)

                self.builder.position_at_end(cond_block)
                cur = self.builder.load(self.vars[var_name][0])
                # step can be negative: if step > 0 check cur < stop else cur > stop
                step_pos = self.builder.icmp_signed(">", range_step, ir.Constant(INT64, 0))
                cond_fwd = self.builder.icmp_signed("<", cur, range_stop)
                cond_bwd = self.builder.icmp_signed(">", cur, range_stop)
                cond = self.builder.select(step_pos, cond_fwd, cond_bwd)
                self.builder.cbranch(cond, body_block, exit_block)

                self.builder.position_at_end(body_block)
                for s in node.body:
                    self._compile_stmt(s)
                if not self.builder.block.is_terminated:
                    self.builder.branch(inc_block)

                self.builder.position_at_end(inc_block)
                cur2 = self.builder.load(self.vars[var_name][0])
                nxt  = self.builder.add(cur2, range_step)
                self.builder.store(nxt, self.vars[var_name][0])
                self.builder.branch(cond_block)

            elif iter_typ == "str":
                idx_ptr = self.builder.alloca(INT64, name="for_str_idx")
                self.builder.store(ir.Constant(INT64, 0), idx_ptr)
                self.builder.branch(cond_block)

                self.builder.position_at_end(cond_block)
                idx = self.builder.load(idx_ptr)
                length = self.builder.call(self.strlen, [iter_val])
                cond = self.builder.icmp_signed("<", idx, length)
                self.builder.cbranch(cond, body_block, exit_block)

                self.builder.position_at_end(body_block)
                idx2 = self.builder.load(idx_ptr)
                char_ptr = self.builder.gep(iter_val, [idx2])
                char_val = self.builder.load(char_ptr)
                char_buf = self.builder.call(self.malloc, [ir.Constant(INT64, 2)])
                self.builder.store(char_val, char_buf)
                null_ptr = self.builder.gep(char_buf, [ir.Constant(INT64, 1)])
                self.builder.store(ir.Constant(INT8, 0), null_ptr)
                var_name = target if isinstance(target, str) else target[0]
                if var_name not in self.vars:
                    ptr = self.builder.alloca(PTR, name=var_name)
                    self.vars[var_name] = (ptr, "str")
                self.builder.store(char_buf, self.vars[var_name][0])
                for s in node.body:
                    self._compile_stmt(s)
                if not self.builder.block.is_terminated:
                    self.builder.branch(inc_block)

                self.builder.position_at_end(inc_block)
                old_idx = self.builder.load(idx_ptr)
                self.builder.store(self.builder.add(old_idx, ir.Constant(INT64, 1)), idx_ptr)
                self.builder.branch(cond_block)

            else:
                # unsupported iter type: just skip body
                self.builder.branch(exit_block)

            self.loop_exit_block    = prev_exit
            self.loop_continue_block = prev_cont
            self.builder.position_at_end(exit_block)

        elif isinstance(node, ReturnNode):
            if node.value:
                val, typ = self._compile_expr(node.value)
                self.builder.ret(val)
            else:
                self.builder.ret(ir.Constant(INT32, 0))

        elif isinstance(node, BreakNode):
            if self.loop_exit_block:
                self.builder.branch(self.loop_exit_block)

        elif isinstance(node, ContinueNode):
            if self.loop_continue_block:
                self.builder.branch(self.loop_continue_block)

        elif isinstance(node, PassNode):
            pass

        elif isinstance(node, AssertNode):
            test, _ = self._compile_expr(node.test)
            test_bool = self._to_bool(test, "bool")
            fn = self.builder.function
            fail_block = fn.append_basic_block("assert.fail")
            pass_block = fn.append_basic_block("assert.pass")
            self.builder.cbranch(test_bool, pass_block, fail_block)
            self.builder.position_at_end(fail_block)
            msg = "AssertionError\n\0"
            if node.msg:
                m, _ = self._compile_expr(node.msg)
                self.builder.call(self.printf, [self._make_string("%s\n"), m])
            else:
                self.builder.call(self.printf, [self._make_string("AssertionError\n")])
            self.builder.call(self.exit_f, [ir.Constant(INT32, 1)])
            self.builder.branch(pass_block)
            self.builder.position_at_end(pass_block)

        elif isinstance(node, RaiseNode):
            if node.exc:
                exc_node = node.exc
                # unwrap CallNode to get the exception name and optional message
                msg_val = None
                exc_name = None
                if isinstance(exc_node, CallNode) and isinstance(exc_node.func, VariableNode):
                    exc_name = exc_node.func.name
                    if exc_node.args:
                        try:
                            msg_val, msg_typ = self._compile_expr(exc_node.args[0])
                            if msg_typ == "int":
                                tmp = self.builder.call(self.malloc, [ir.Constant(INT64, 32)])
                                self.builder.store(ir.Constant(INT8, 0), tmp)
                                self.builder.call(self.sprintf, [tmp, self._make_string("%lld"), msg_val])
                                msg_val = tmp
                        except Exception:
                            msg_val = None
                elif isinstance(exc_node, VariableNode):
                    exc_name = exc_node.name

                # look up exit code from BUILTIN_EXCEPTIONS
                exc_info = BUILTIN_EXCEPTIONS.get(exc_name) if exc_name else None
                exit_code = exc_info[1] if exc_info else 1

                if exc_name == "SystemExit":
                    if msg_val is not None:
                        self.builder.call(self.printf, [self._make_string("%s\n"), msg_val])
                    self.builder.call(self.exit_f, [ir.Constant(INT32, 0)])
                else:
                    if exc_name:
                        self.builder.call(self.printf, [self._make_string(f"{exc_name}: "), ])
                    if msg_val is not None:
                        self.builder.call(self.printf, [self._make_string("%s\n"), msg_val])
                    elif exc_name:
                        self.builder.call(self.printf, [self._make_string("\n")])
                    self.builder.call(self.exit_f, [ir.Constant(INT32, exit_code)])
            else:
                self.builder.call(self.exit_f, [ir.Constant(INT32, 1)])

        elif isinstance(node, TryNode):
            # Compile-time exception resolution:
            # We attempt each stmt in the try body. For ImportNode we check
            # at compile time if the import succeeds. If it raises an exception
            # matching one of the except handlers, we emit the handler body instead.
            # For stmts that can't fail at compile time, we just emit them normally.

            def _handler_catches(handler, exc_name):
                """Check if an ExceptHandlerNode catches the given exception name."""
                if handler.typ is None:
                    return True  # bare except
                # collect names from the handler type (could be TupleNode or VariableNode)
                def _names(n):
                    if isinstance(n, VariableNode):
                        return [n.name]
                    if isinstance(n, TupleNode):
                        result = []
                        for e in n.elts:
                            result.extend(_names(e))
                        return result
                    return []
                caught = _names(handler.typ)
                # build the MRO of exc_name using BUILTIN_EXCEPTIONS
                exc_mro = {
                    "ModuleNotFoundError": ["ModuleNotFoundError", "ImportError", "Exception", "BaseException"],
                    "ImportError":         ["ImportError", "Exception", "BaseException"],
                    "AttributeError":      ["AttributeError", "Exception", "BaseException"],
                    "NameError":           ["NameError", "Exception", "BaseException"],
                    "SystemExit":          ["SystemExit", "BaseException"],
                    "KeyboardInterrupt":   ["KeyboardInterrupt", "BaseException"],
                    "ValueError":          ["ValueError", "Exception", "BaseException"],
                    "TypeError":           ["TypeError", "Exception", "BaseException"],
                    "RuntimeError":        ["RuntimeError", "Exception", "BaseException"],
                    "OSError":             ["OSError", "Exception", "BaseException"],
                    "IOError":             ["OSError", "Exception", "BaseException"],
                    "FileNotFoundError":   ["FileNotFoundError", "OSError", "Exception", "BaseException"],
                    "ZeroDivisionError":   ["ZeroDivisionError", "ArithmeticError", "Exception", "BaseException"],
                    "OverflowError":       ["OverflowError", "ArithmeticError", "Exception", "BaseException"],
                    "IndexError":          ["IndexError", "LookupError", "Exception", "BaseException"],
                    "KeyError":            ["KeyError", "LookupError", "Exception", "BaseException"],
                    "AssertionError":      ["AssertionError", "Exception", "BaseException"],
                    "StopIteration":       ["StopIteration", "Exception", "BaseException"],
                    "RecursionError":      ["RecursionError", "RuntimeError", "Exception", "BaseException"],
                    "NotImplementedError": ["NotImplementedError", "RuntimeError", "Exception", "BaseException"],
                    "PermissionError":     ["PermissionError", "OSError", "Exception", "BaseException"],
                    "TimeoutError":        ["TimeoutError", "OSError", "Exception", "BaseException"],
                    "ConnectionError":     ["ConnectionError", "OSError", "Exception", "BaseException"],
                    "Exception":           ["Exception", "BaseException"],
                    "BaseException":       ["BaseException"],
                }
                mro = exc_mro.get(exc_name, [exc_name, "Exception", "BaseException"])
                return any(c in caught for c in mro)

            def _find_handler(exc_name):
                for h in node.handlers:
                    if _handler_catches(h, exc_name):
                        return h
                return None

            raised_exc = None  # name of exception raised in try body, if any

            for stmt in node.body:
                if isinstance(stmt, ImportNode):
                    mod_name = stmt.name.split(".")[0]
                    try:
                        importlib.import_module(mod_name)
                        # import ok — emit as normal
                        self._compile_stmt(stmt)
                    except ImportError:
                        raised_exc = "ModuleNotFoundError"
                        break
                    except Exception as e:
                        raised_exc = type(e).__name__
                        break
                else:
                    self._compile_stmt(stmt)
                    if self.builder.block.is_terminated:
                        break

            if raised_exc:
                handler = _find_handler(raised_exc)
                if handler:
                    if handler.name:
                        # bind the exception name to a string var
                        exc_str = self._make_string(raised_exc)
                        ptr = self.builder.alloca(PTR, name=handler.name)
                        self.builder.store(exc_str, ptr)
                        self.vars[handler.name] = (ptr, "str")
                    for s in handler.body:
                        self._compile_stmt(s)

            # always compile finally
            for s in node.finalbody:
                self._compile_stmt(s)

        elif isinstance(node, WithNode):
            for s in node.body:
                self._compile_stmt(s)

        elif isinstance(node, GlobalNode):
            pass

        elif isinstance(node, NonlocalNode):
            pass

        elif isinstance(node, DeleteNode):
            for t in node.targets:
                if isinstance(t, VariableNode) and t.name in self.vars:
                    del self.vars[t.name]

        elif isinstance(node, FuncDefNode):
            self._compile_funcdef(node)

        elif isinstance(node, AsyncFuncDefNode):
            self._compile_funcdef(node)

        elif isinstance(node, ClassDefNode):
            for s in node.body:
                if isinstance(s, FuncDefNode):
                    self._compile_funcdef(s, class_name=node.name)

        elif isinstance(node, YieldNode):
            pass

        elif isinstance(node, AwaitNode):
            pass

        else:
            pass

    def _compile_funcdef(self, node, class_name=None):
        saved_vars = dict(self.vars)
        saved_builder = self.builder
        saved_func = self.current_func
        arg_types = []
        for arg_name, annotation, default in node.args:
            arg_types.append(INT64)
        ret_type = INT64
        fn_name = f"{class_name}.{node.name}" if class_name else node.name
        fn_type = ir.FunctionType(ret_type, arg_types)
        fn = ir.Function(self.module, fn_type, name=fn_name)
        self.funcs[fn_name] = (fn, arg_types, "int")
        if not class_name:
            self.funcs[node.name] = (fn, arg_types, "int")
        block = fn.append_basic_block("entry")
        self.builder = ir.IRBuilder(block)
        self.current_func = fn
        self.vars = {}
        for i, (arg_name, annotation, default) in enumerate(node.args):
            ptr = self.builder.alloca(INT64, name=arg_name)
            self.builder.store(fn.args[i], ptr)
            self.vars[arg_name] = (ptr, "int")
        for s in node.body:
            self._compile_stmt(s)
        if not self.builder.block.is_terminated:
            self.builder.ret(ir.Constant(INT64, 0))
        self.vars = saved_vars
        self.builder = saved_builder
        self.current_func = saved_func

    def compile(self, output_name):
        main_type = ir.FunctionType(INT32, [])
        main_fn = ir.Function(self.module, main_type, name="main")
        block = main_fn.append_basic_block("entry")
        self.builder = ir.IRBuilder(block)
        self.current_func = main_fn

        for node in self.tree.body:
            self._compile_stmt(node)

        if not self.builder.block.is_terminated:
            self.builder.ret(ir.Constant(INT32, 0))

        llvm_ir = str(self.module)
        mod = llvm.parse_assembly(llvm_ir)
        mod.verify()
        target = llvm.Target.from_default_triple()
        print(f"Compiling with target: {llvm.get_default_triple()}")
        tm = target.create_target_machine(opt=self.args["opt_level"], reloc="static", codemodel="default")
        mod.triple = llvm.get_default_triple()
        mod.data_layout = str(tm.target_data)
        obj = tm.emit_object(mod)

        obj_file = output_name + ".o" if not output_name.endswith(".exe") else output_name.replace(".exe", ".o")
        with open(obj_file, "wb") as f:
            f.write(obj)

        if platform.system() == "Windows":
            cmd = ["zig", "cc", "-w", obj_file, "-o", output_name]
        elif platform.system() == "Darwin":
            cmd = ["clang", "-w", obj_file, "-o", output_name]
        else:
            cmd = ["gcc", "-w", "-no-pie", obj_file, "-o", output_name]

        if self.args["static"]:
            cmd.append("-static")
        for d in self.args["pyl"]:
            cmd += ["-L", d]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"\x1b[33mCompiled -> {output_name}\x1b[0m")
        except KeyboardInterrupt:
            print("\033[33mStopped operation!\x1b[0m")
        except subprocess.CalledProcessError as e:
            print("\x1b[31m--------Compiler Error--------\x1b[0m")
            print(e.stderr)
            print(f"\033[31mMessage: {e}\x1b[0m")

        if self.args["nobj"]:
            from pathlib import Path
            Path(obj_file).unlink(missing_ok=True)

        if self.args["npdb"]:
            from pathlib import Path
            if platform.system() == "Windows":
                try:
                    Path(output_name).with_suffix(".pdb").unlink()
                except (FileNotFoundError, PermissionError):
                    print("\033[31mError deleting .pdb!\033[0m")
            else:
                try:
                    Path(output_name).with_suffix(".pdb").unlink()
                except (FileNotFoundError, PermissionError):
                    pass

def compile_ast(tree, output_name, args):
    compiler = Compiler(tree, args)
    compiler.compile(output_name)