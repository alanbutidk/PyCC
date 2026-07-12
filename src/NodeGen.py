"""NodeGen.py -> Dynamically generates parser nodes and compiler handlers
for any callable object, module attribute, or function not hardcoded in the parser.
Usage: GenParserNode(os.path.join) -> creates node, registers in parser + compiler"""
import inspect

PARSER_EXTENSIONS = {}
COMPILER_EXTENSIONS = {}

def _get_obj_info(obj):
    name = getattr(obj, "__name__", None) or getattr(obj, "__func__", {__name__: str(obj)}).__name__
    module = getattr(obj, "__module__", None)
    qualname = getattr(obj, "__qualname__", name)
    try:
        sig = inspect.signature(obj)
        params = list(sig.parameters.keys())
    except (ValueError, TypeError):
        params = []
    return name, module, qualname, params

def _make_node_class(node_name, params):
    def __init__(self, args, kwargs):
        self.args = args
        self.kwargs = kwargs
    def __repr__(self):
        return f"{node_name}(args={self.args}, kwargs={self.kwargs})"
    cls = type(node_name, (), {
        "__init__": __init__,
        "__repr__": __repr__,
        "params": params,
    })
    return cls

def GenParserNode(obj):
    name, module, qualname, params = _get_obj_info(obj)
    node_name = "Node_" + qualname.replace(".", "_")
    if node_name in PARSER_EXTENSIONS:
        return PARSER_EXTENSIONS[node_name]
    node_cls = _make_node_class(node_name, params)
    lookup_key = qualname
    PARSER_EXTENSIONS[lookup_key] = {
        "node_cls": node_cls,
        "obj": obj,
        "name": name,
        "module": module,
        "qualname": qualname,
        "params": params,
    }
    def compiler_handler(compiler, node):
        import llvmlite.ir as ir
        compiled_args = []
        for arg in node.args:
            val, typ = compiler._compile_expr(arg)
            if typ == "str":
                compiled_args.append(val)
            elif typ == "int":
                buf = compiler.builder.call(compiler.malloc, [ir.Constant(compiler.INT64, 32)])
                fmt = compiler._make_string("%lld")
                compiler.builder.call(compiler.sprintf, [buf, fmt, val])
                compiled_args.append(buf)
            elif typ == "float":
                buf = compiler.builder.call(compiler.malloc, [ir.Constant(compiler.INT64, 64)])
                fmt = compiler._make_string("%f")
                compiler.builder.call(compiler.sprintf, [buf, fmt, val])
                compiled_args.append(buf)
            else:
                compiled_args.append(val)
        try:
            py_args = []
            for arg in node.args:
                py_args.append(None)
            result = obj(*[None]*len(node.args))
        except Exception:
            result = None
        if isinstance(result, str):
            return compiler._make_string(result), "str"
        return ir.Constant(compiler.INT64, 0), "none"
    COMPILER_EXTENSIONS[lookup_key] = compiler_handler
    return node_cls

def resolve_node(qualname):
    return PARSER_EXTENSIONS.get(qualname)

def resolve_compiler(qualname):
    return COMPILER_EXTENSIONS.get(qualname)

def list_registered():
    return list(PARSER_EXTENSIONS.keys())
