from Tokenize import *
import importlib

MODULE_REGISTRY = {}
# alias -> real module name  e.g. {"s": "subprocess"}
IMPORT_ALIASES = {}

class PyCCSyntaxError(SyntaxError):
    """
    SyntaxError subclass that also carries the offending token's source
    line number, so callers (PyCC.py) can print the classic
    "Line N: <source text>" / "~~~~~" pointer instead of a bare token
    index -- token indices don't map to anything a person can act on
    (they don't correspond 1:1 with characters or even tokens-per-line
    in any way that's easy to eyeball), so every parse error used to
    require re-running the tokenizer by hand just to find where it was.
    """
    def __init__(self, message, line=None):
        super().__init__(message)
        self.pycc_line = line

def register_module(name):
    try:
        mod = importlib.import_module(name)
        enum_cls = GenTokenEnum(mod)
        MODULE_REGISTRY[name] = enum_cls
        register_module_tokens(enum_cls)
    except ImportError:
        pass

# ---------- AST Nodes ----------

class ProgramNode:
    def __init__(self, body): self.body = body

class ImportNode:
    def __init__(self, name, alias=None): self.name = name; self.alias = alias

class FromImportNode:
    def __init__(self, module, names): self.module = module; self.names = names

class AssignNode:
    def __init__(self, targets, value): self.targets = targets; self.value = value

class AugAssignNode:
    def __init__(self, name, op, value): self.name = name; self.op = op; self.value = value

class AnnAssignNode:
    def __init__(self, name, annotation, value): self.name = name; self.annotation = annotation; self.value = value

class DeleteNode:
    def __init__(self, targets): self.targets = targets

class PassNode: pass
class BreakNode: pass
class ContinueNode: pass

class ReturnNode:
    def __init__(self, value): self.value = value

class YieldNode:
    def __init__(self, value): self.value = value

class RaiseNode:
    def __init__(self, exc, cause): self.exc = exc; self.cause = cause

class AssertNode:
    def __init__(self, test, msg): self.test = test; self.msg = msg

class GlobalNode:
    def __init__(self, names): self.names = names

class NonlocalNode:
    def __init__(self, names): self.names = names

class IfNode:
    def __init__(self, test, body, elifs, orelse):
        self.test = test; self.body = body; self.elifs = elifs; self.orelse = orelse

class WhileNode:
    def __init__(self, test, body, orelse):
        self.test = test; self.body = body; self.orelse = orelse

class ForNode:
    def __init__(self, target, iter, body, orelse):
        self.target = target; self.iter = iter; self.body = body; self.orelse = orelse

class TryNode:
    def __init__(self, body, handlers, orelse, finalbody):
        self.body = body; self.handlers = handlers; self.orelse = orelse; self.finalbody = finalbody

class ExceptHandlerNode:
    def __init__(self, typ, name, body):
        self.typ = typ; self.name = name; self.body = body

class WithNode:
    def __init__(self, items, body): self.items = items; self.body = body

class FuncDefNode:
    def __init__(self, name, args, body, decorators, returns):
        self.name = name; self.args = args; self.body = body
        self.decorators = decorators; self.returns = returns

class AsyncFuncDefNode:
    def __init__(self, name, args, body, decorators, returns):
        self.name = name; self.args = args; self.body = body
        self.decorators = decorators; self.returns = returns

class ClassDefNode:
    def __init__(self, name, bases, body, decorators):
        self.name = name; self.bases = bases; self.body = body; self.decorators = decorators

class PrintNode:
    def __init__(self, args, kwargs=None): self.args = args; self.kwargs = kwargs or {}

class CallNode:
    def __init__(self, func, args, kwargs): self.func = func; self.args = args; self.kwargs = kwargs

class AttributeNode:
    def __init__(self, obj, attr): self.obj = obj; self.attr = attr

class SubscriptNode:
    def __init__(self, obj, index): self.obj = obj; self.index = index

class SliceNode:
    def __init__(self, lower, upper, step): self.lower = lower; self.upper = upper; self.step = step

class IntNode:
    def __init__(self, value): self.value = value

class FloatNode:
    def __init__(self, value): self.value = value

class StringNode:
    def __init__(self, value): self.value = value

class FStringNode:
    """F-string node. parts is a list of (is_expr, value) tuples."""
    def __init__(self, parts): self.parts = parts

class BoolNode:
    def __init__(self, value): self.value = value

class NoneNode: pass

class VariableNode:
    def __init__(self, name): self.name = name

class BinOpNode:
    def __init__(self, left, op, right): self.left = left; self.op = op; self.right = right

class UnaryOpNode:
    def __init__(self, op, operand): self.op = op; self.operand = operand

class CompareNode:
    def __init__(self, left, ops, comparators):
        self.left = left; self.ops = ops; self.comparators = comparators

class BoolOpNode:
    def __init__(self, op, values): self.op = op; self.values = values

class IfExpNode:
    def __init__(self, test, body, orelse): self.test = test; self.body = body; self.orelse = orelse

class LambdaNode:
    def __init__(self, args, body): self.args = args; self.body = body

class ListNode:
    def __init__(self, elts): self.elts = elts

class TupleNode:
    def __init__(self, elts): self.elts = elts

class DictNode:
    def __init__(self, keys, values): self.keys = keys; self.values = values

class SetNode:
    def __init__(self, elts): self.elts = elts

class StarredNode:
    def __init__(self, value): self.value = value

class AwaitNode:
    def __init__(self, value): self.value = value

class RangeNode:
    """range(start, stop, step) - resolved at parse time for for-loop use."""
    def __init__(self, args): self.args = args

BINOP_OPS = {
    TKN_GROUP_OPERATORS.PLUS, TKN_GROUP_OPERATORS.MINUS,
    TKN_GROUP_OPERATORS.STAR, TKN_GROUP_OPERATORS.SLASH,
    TKN_GROUP_OPERATORS.PERCENT, TKN_GROUP_OPERATORS.DSTAR,
    TKN_GROUP_OPERATORS.DSLASH, TKN_GROUP_OPERATORS.AMP,
    TKN_GROUP_OPERATORS.PIPE, TKN_GROUP_OPERATORS.CARET,
    TKN_GROUP_OPERATORS.LSHIFT, TKN_GROUP_OPERATORS.RSHIFT,
    TKN_GROUP_OPERATORS.AT,
}

AUGASSIGN_OPS = {
    TKN_GROUP_OPERATORS.PLUS_EQ, TKN_GROUP_OPERATORS.MINUS_EQ,
    TKN_GROUP_OPERATORS.STAR_EQ, TKN_GROUP_OPERATORS.SLASH_EQ,
    TKN_GROUP_OPERATORS.PERCENT_EQ, TKN_GROUP_OPERATORS.DSTAR_EQ,
    TKN_GROUP_OPERATORS.DSLASH_EQ, TKN_GROUP_OPERATORS.AMP_EQ,
    TKN_GROUP_OPERATORS.PIPE_EQ, TKN_GROUP_OPERATORS.CARET_EQ,
    TKN_GROUP_OPERATORS.LSHIFT_EQ, TKN_GROUP_OPERATORS.RSHIFT_EQ,
    TKN_GROUP_OPERATORS.AT_EQ,
}

COMPARE_OPS = {
    TKN_GROUP_OPERATORS.EQEQ, TKN_GROUP_OPERATORS.NEQ,
    TKN_GROUP_OPERATORS.LT, TKN_GROUP_OPERATORS.GT,
    TKN_GROUP_OPERATORS.LEQ, TKN_GROUP_OPERATORS.GEQ,
    TKN_GROUP_KEYWORDS.IN, TKN_GROUP_KEYWORDS.NOT_IN,
    TKN_GROUP_KEYWORDS.IS, TKN_GROUP_KEYWORDS.IS_NOT,
}

SKIP_TOKENS = {
    TKN_GROUP_SPECIAL.COMMENT,
    TKN_GROUP_SPECIAL.MULTI_COMMENT,
}

STMT_END = {TKN_GROUP_SPECIAL.NEWLINE, TKN_GROUP_SPECIAL.SEMICOLON}


class Parser:
    def __init__(self, tokens):
        self.tokens = [t for t in tokens if t.type not in SKIP_TOKENS]
        self.i = 0

    def peek(self, offset=0):
        idx = self.i + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return None

    def eat(self, expected=None):
        t = self.tokens[self.i]
        if expected and t.type != expected:
            raise PyCCSyntaxError(
                f"Expected {expected} but got {t.type} ({t.value!r})",
                line=t.line)
        self.i += 1
        return t

    def at_end(self):
        return self.i >= len(self.tokens)

    def skip(self, *types):
        while not self.at_end() and self.peek().type in types:
            self.i += 1

    def skip_newlines(self):
        self.skip(TKN_GROUP_SPECIAL.NEWLINE, TKN_GROUP_SPECIAL.SEMICOLON)

    def at_stmt_end(self):
        return self.at_end() or self.peek().type in STMT_END

    # ---- top level ----

    def parse(self):
        body = []
        self.skip_newlines()
        while not self.at_end():
            stmt = self.parse_stmt()
            if stmt is not None:
                body.append(stmt)
            self.skip_newlines()
        return ProgramNode(body)

    def parse_block(self):
        """Parse an indented block. Must be called after eating the COLON."""
        body = []
        self.skip_newlines()
        if self.at_end():
            return body

        # inline single-stmt block: `if x: pass`
        if self.peek().type != TKN_GROUP_SPECIAL.INDENT:
            stmt = self.parse_stmt()
            if stmt is not None:
                body.append(stmt)
            return body

        self.eat(TKN_GROUP_SPECIAL.INDENT)
        self.skip_newlines()
        while not self.at_end() and self.peek().type != TKN_GROUP_SPECIAL.DEDENT:
            stmt = self.parse_stmt()
            if stmt is not None:
                body.append(stmt)
            self.skip_newlines()
        if not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.DEDENT:
            self.eat(TKN_GROUP_SPECIAL.DEDENT)
        return body

    # ---- statements ----

    def parse_stmt(self):
        self.skip_newlines()
        if self.at_end():
            return None
        t = self.peek()

        if t.type == TKN_GROUP_KEYWORDS.IMPORT:
            return self.parse_import()
        elif t.type == TKN_GROUP_KEYWORDS.FROM:
            return self.parse_from_import()
        elif t.type == TKN_GROUP_KEYWORDS.IF:
            return self.parse_if()
        elif t.type == TKN_GROUP_KEYWORDS.WHILE:
            return self.parse_while()
        elif t.type == TKN_GROUP_KEYWORDS.FOR:
            return self.parse_for()
        elif t.type == TKN_GROUP_KEYWORDS.TRY:
            return self.parse_try()
        elif t.type == TKN_GROUP_KEYWORDS.WITH:
            return self.parse_with()
        elif t.type == TKN_GROUP_KEYWORDS.ASYNC:
            return self.parse_async()
        elif t.type == TKN_GROUP_OPERATORS.AT:
            # @decorator1
            # @decorator2
            # def f(...): ...
            # We don't have function values / indirect calls, so we can't
            # actually apply an arbitrary decorator's wrapping logic. What
            # we *can* do correctly is parse the syntax so it doesn't blow
            # up the parser, and compile the underlying def/class as if
            # undecorated -- which is exactly correct for identity-style
            # decorators (`def deco(f): return f`), the common case in
            # simple/test code, and a reasonable degradation otherwise.
            decorators = []
            while not self.at_end() and self.peek().type == TKN_GROUP_OPERATORS.AT:
                self.eat()
                decorators.append(self.parse_expr())
                self.eat(TKN_GROUP_SPECIAL.NEWLINE)
            inner = self.parse_stmt()
            if isinstance(inner, (FuncDefNode, AsyncFuncDefNode)):
                inner.decorators = decorators
            return inner
        elif t.type == TKN_GROUP_KEYWORDS.DEF:
            return self.parse_funcdef()
        elif t.type == TKN_GROUP_KEYWORDS.CLASS:
            return self.parse_classdef()
        elif t.type == TKN_GROUP_KEYWORDS.RETURN:
            return self.parse_return()
        elif t.type == TKN_GROUP_KEYWORDS.YIELD:
            return self.parse_yield()
        elif t.type == TKN_GROUP_KEYWORDS.RAISE:
            return self.parse_raise()
        elif t.type == TKN_GROUP_KEYWORDS.ASSERT:
            return self.parse_assert()
        elif t.type == TKN_GROUP_KEYWORDS.DEL:
            return self.parse_del()
        elif t.type == TKN_GROUP_KEYWORDS.GLOBAL:
            return self.parse_global()
        elif t.type == TKN_GROUP_KEYWORDS.NONLOCAL:
            return self.parse_nonlocal()
        elif t.type == TKN_GROUP_KEYWORDS.PASS:
            self.eat(); self.skip(TKN_GROUP_SPECIAL.NEWLINE); return PassNode()
        elif t.type == TKN_GROUP_KEYWORDS.BREAK:
            self.eat(); self.skip(TKN_GROUP_SPECIAL.NEWLINE); return BreakNode()
        elif t.type == TKN_GROUP_KEYWORDS.CONTINUE:
            self.eat(); self.skip(TKN_GROUP_SPECIAL.NEWLINE); return ContinueNode()
        else:
            return self.parse_expr_stmt()

    def parse_import(self):
        self.eat(TKN_GROUP_KEYWORDS.IMPORT)
        name = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
        while not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.DOT:
            self.eat()
            name += "." + self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
        alias = None
        if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.AS:
            self.eat(); alias = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
        root = name.split(".")[0]
        register_module(root)
        if alias:
            IMPORT_ALIASES[alias] = root
        else:
            IMPORT_ALIASES[root] = root
        self.skip(TKN_GROUP_SPECIAL.NEWLINE)
        return ImportNode(name, alias)

    def parse_from_import(self):
        self.eat(TKN_GROUP_KEYWORDS.FROM)
        module = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
        while not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.DOT:
            self.eat()
            module += "." + self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
        self.eat(TKN_GROUP_KEYWORDS.IMPORT)
        names = []
        if not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.BRACKET_NORMOPEN:
            self.eat()
            while not self.at_end() and self.peek().type != TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE:
                self.skip(TKN_GROUP_SPECIAL.COMMA)
                n = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
                alias = None
                if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.AS:
                    self.eat(); alias = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
                names.append((n, alias))
            self.eat(TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE)
        else:
            # Multiple comma-separated names without parens, e.g.
            # `from console import console, print_banner`, was previously
            # unhandled here -- this branch only ever read a single name
            # and then stopped, leaving the following "," unconsumed,
            # which surfaced later as an unrelated-looking
            # "Unexpected token: COMMA" parse error.
            while True:
                n = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
                alias = None
                if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.AS:
                    self.eat(); alias = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
                names.append((n, alias))
                if not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COMMA:
                    self.eat()
                    continue
                break
        register_module(module.split(".")[0])
        self.skip(TKN_GROUP_SPECIAL.NEWLINE)
        return FromImportNode(module, names)

    def parse_if(self):
        self.eat(TKN_GROUP_KEYWORDS.IF)
        test = self.parse_expr()
        self.eat(TKN_GROUP_SPECIAL.COLON)
        body = self.parse_block()
        elifs = []
        orelse = []
        self.skip_newlines()
        while not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.ELIF:
            self.eat()
            elif_test = self.parse_expr()
            self.eat(TKN_GROUP_SPECIAL.COLON)
            elif_body = self.parse_block()
            elifs.append((elif_test, elif_body))
            self.skip_newlines()
        if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.ELSE:
            self.eat()
            self.eat(TKN_GROUP_SPECIAL.COLON)
            orelse = self.parse_block()
        return IfNode(test, body, elifs, orelse)

    def parse_while(self):
        self.eat(TKN_GROUP_KEYWORDS.WHILE)
        test = self.parse_expr()
        self.eat(TKN_GROUP_SPECIAL.COLON)
        body = self.parse_block()
        orelse = []
        self.skip_newlines()
        if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.ELSE:
            self.eat(); self.eat(TKN_GROUP_SPECIAL.COLON)
            orelse = self.parse_block()
        return WhileNode(test, body, orelse)

    def parse_for(self):
        self.eat(TKN_GROUP_KEYWORDS.FOR)
        # support tuple unpacking: for x, y in ...
        if self.peek(1) and self.peek(1).type == TKN_GROUP_SPECIAL.COMMA:
            targets = [self.eat(TKN_VARIABLE_GROUP.VARIABLE).value]
            while not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COMMA:
                self.eat()
                targets.append(self.eat(TKN_VARIABLE_GROUP.VARIABLE).value)
            target = targets
        else:
            target = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
        self.eat(TKN_GROUP_KEYWORDS.IN)
        iter_ = self.parse_expr()
        self.eat(TKN_GROUP_SPECIAL.COLON)
        body = self.parse_block()
        orelse = []
        self.skip_newlines()
        if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.ELSE:
            self.eat(); self.eat(TKN_GROUP_SPECIAL.COLON)
            orelse = self.parse_block()
        return ForNode(target, iter_, body, orelse)

    def parse_try(self):
        self.eat(TKN_GROUP_KEYWORDS.TRY)
        self.eat(TKN_GROUP_SPECIAL.COLON)
        body = self.parse_block()
        handlers = []
        self.skip_newlines()
        while not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.EXCEPT:
            self.eat()
            exc_type = None; exc_name = None
            if not self.at_end() and self.peek().type != TKN_GROUP_SPECIAL.COLON:
                exc_type = self.parse_expr()
                if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.AS:
                    self.eat()
                    exc_name = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
            self.eat(TKN_GROUP_SPECIAL.COLON)
            handler_body = self.parse_block()
            handlers.append(ExceptHandlerNode(exc_type, exc_name, handler_body))
            self.skip_newlines()
        orelse = []
        if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.ELSE:
            self.eat(); self.eat(TKN_GROUP_SPECIAL.COLON)
            orelse = self.parse_block()
            self.skip_newlines()
        finalbody = []
        if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.FINALLY:
            self.eat(); self.eat(TKN_GROUP_SPECIAL.COLON)
            finalbody = self.parse_block()
        return TryNode(body, handlers, orelse, finalbody)

    def parse_with(self):
        self.eat(TKN_GROUP_KEYWORDS.WITH)
        items = []
        while True:
            ctx = self.parse_expr()
            alias = None
            if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.AS:
                self.eat(); alias = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
            items.append((ctx, alias))
            if self.at_end() or self.peek().type != TKN_GROUP_SPECIAL.COMMA:
                break
            self.eat()
        self.eat(TKN_GROUP_SPECIAL.COLON)
        body = self.parse_block()
        return WithNode(items, body)

    def _def_name(self):
        # Normally a function/class name is a VARIABLE token. But some
        # builtin names (staticmethod, classmethod, len, str, ...) get
        # tokenized as their own fixed BUILTINS token type rather than a
        # generic identifier (see Tokenize.BUILTIN_MAP), since ordinarily
        # they refer to the builtin itself. That breaks the legitimate case
        # of a user *redefining* one of those names as a plain function
        # (`def staticmethod(func): return func`, a common pattern for
        # writing your own decorator stand-ins). Accept a BUILTINS token
        # here too and recover its name from the enum, so a redefinition
        # parses instead of raising "Expected VARIABLE".
        t = self.peek()
        if t.type == TKN_VARIABLE_GROUP.VARIABLE:
            return self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
        if isinstance(t.type, TKN_GROUP_BUILTINS):
            self.eat()
            return t.type.name.lower()
        return self.eat(TKN_VARIABLE_GROUP.VARIABLE).value

    def parse_funcdef(self, async_=False):
        self.eat(TKN_GROUP_KEYWORDS.DEF)
        name = self._def_name()
        self.eat(TKN_GROUP_SPECIAL.BRACKET_NORMOPEN)
        args = self.parse_funcargs()
        self.eat(TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE)
        returns = None
        if not self.at_end() and self.peek().type == TKN_GROUP_OPERATORS.ARROW:
            self.eat(); returns = self.parse_expr()
        self.eat(TKN_GROUP_SPECIAL.COLON)
        body = self.parse_block()
        if async_:
            return AsyncFuncDefNode(name, args, body, [], returns)
        return FuncDefNode(name, args, body, [], returns)

    def parse_classdef(self):
        self.eat(TKN_GROUP_KEYWORDS.CLASS)
        name = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
        bases = []
        if not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.BRACKET_NORMOPEN:
            self.eat()
            while not self.at_end() and self.peek().type != TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE:
                self.skip(TKN_GROUP_SPECIAL.COMMA)
                if self.peek().type == TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE:
                    break
                bases.append(self.parse_expr())
            self.eat(TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE)
        self.eat(TKN_GROUP_SPECIAL.COLON)
        body = self.parse_block()
        return ClassDefNode(name, bases, body, [])

    def parse_funcargs(self):
        args = []
        while not self.at_end() and self.peek().type != TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE:
            self.skip(TKN_GROUP_SPECIAL.COMMA)
            if self.at_end() or self.peek().type == TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE:
                break
            # *args and **kwargs
            if self.peek().type == TKN_GROUP_OPERATORS.DSTAR:
                self.eat()
                arg_name = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
                args.append(("**" + arg_name, None, None))
                continue
            if self.peek().type == TKN_GROUP_OPERATORS.STAR:
                self.eat()
                if not self.at_end() and self.peek().type == TKN_VARIABLE_GROUP.VARIABLE:
                    arg_name = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
                    args.append(("*" + arg_name, None, None))
                continue
            arg_name = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
            annotation = None; default = None
            if not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COLON:
                self.eat(); annotation = self.parse_expr()
            if not self.at_end() and self.peek().type == TKN_GROUP_OPERATORS.EQ:
                self.eat(); default = self.parse_expr()
            args.append((arg_name, annotation, default))
        return args

    def parse_async(self):
        self.eat(TKN_GROUP_KEYWORDS.ASYNC)
        return self.parse_funcdef(async_=True)

    def parse_return(self):
        self.eat(TKN_GROUP_KEYWORDS.RETURN)
        value = None
        if not self.at_stmt_end():
            value = self.parse_expr()
        self.skip(TKN_GROUP_SPECIAL.NEWLINE)
        return ReturnNode(value)

    def parse_yield(self):
        self.eat(TKN_GROUP_KEYWORDS.YIELD)
        value = None
        if not self.at_stmt_end():
            value = self.parse_expr()
        self.skip(TKN_GROUP_SPECIAL.NEWLINE)
        return YieldNode(value)

    def parse_raise(self):
        self.eat(TKN_GROUP_KEYWORDS.RAISE)
        exc = None; cause = None
        if not self.at_stmt_end():
            exc = self.parse_expr()
            if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.FROM:
                self.eat(); cause = self.parse_expr()
        self.skip(TKN_GROUP_SPECIAL.NEWLINE)
        return RaiseNode(exc, cause)

    def parse_assert(self):
        self.eat(TKN_GROUP_KEYWORDS.ASSERT)
        test = self.parse_expr()
        msg = None
        if not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COMMA:
            self.eat(); msg = self.parse_expr()
        self.skip(TKN_GROUP_SPECIAL.NEWLINE)
        return AssertNode(test, msg)

    def parse_del(self):
        self.eat(TKN_GROUP_KEYWORDS.DEL)
        targets = [self.parse_expr()]
        while not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COMMA:
            self.eat(); targets.append(self.parse_expr())
        self.skip(TKN_GROUP_SPECIAL.NEWLINE)
        return DeleteNode(targets)

    def parse_global(self):
        self.eat(TKN_GROUP_KEYWORDS.GLOBAL)
        names = [self.eat(TKN_VARIABLE_GROUP.VARIABLE).value]
        while not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COMMA:
            self.eat(); names.append(self.eat(TKN_VARIABLE_GROUP.VARIABLE).value)
        self.skip(TKN_GROUP_SPECIAL.NEWLINE)
        return GlobalNode(names)

    def parse_nonlocal(self):
        self.eat(TKN_GROUP_KEYWORDS.NONLOCAL)
        names = [self.eat(TKN_VARIABLE_GROUP.VARIABLE).value]
        while not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COMMA:
            self.eat(); names.append(self.eat(TKN_VARIABLE_GROUP.VARIABLE).value)
        self.skip(TKN_GROUP_SPECIAL.NEWLINE)
        return NonlocalNode(names)

    def parse_expr_stmt(self):
        expr = self.parse_expr()

        if not self.at_end() and self.peek().type == TKN_GROUP_OPERATORS.EQ:
            self.eat()
            value = self.parse_expr()
            # chained assignment: a = b = c = 99
            # After the first "=", `value` (here `b`) might itself just be
            # the next target in the chain rather than the final RHS --
            # keep consuming "= expr" as long as another EQ follows, and
            # treat everything before the last one as an assignment target.
            targets = [expr]
            while not self.at_end() and self.peek().type == TKN_GROUP_OPERATORS.EQ:
                self.eat()
                targets.append(value)
                value = self.parse_expr()
            self.skip(TKN_GROUP_SPECIAL.NEWLINE)
            norm_targets = [t.name if isinstance(t, VariableNode) else t for t in targets]
            return AssignNode(norm_targets, value)

        if not self.at_end() and self.peek().type in AUGASSIGN_OPS:
            op = self.eat().type
            value = self.parse_expr()
            self.skip(TKN_GROUP_SPECIAL.NEWLINE)
            if isinstance(expr, VariableNode):
                return AugAssignNode(expr.name, op, value)

        if not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COLON:
            self.eat()
            annotation = self.parse_expr()
            value = None
            if not self.at_end() and self.peek().type == TKN_GROUP_OPERATORS.EQ:
                self.eat(); value = self.parse_expr()
            self.skip(TKN_GROUP_SPECIAL.NEWLINE)
            if isinstance(expr, VariableNode):
                return AnnAssignNode(expr.name, annotation, value)

        self.skip(TKN_GROUP_SPECIAL.NEWLINE)
        return expr

    # ---- expressions ----
    # Key fix: parse_ifexp is ONLY called when we're already inside an expression
    # and we see `if` AFTER a value (ternary). Statement-level `if` never reaches here.

    def parse_expr(self):
        return self.parse_ternary()

    def parse_ternary(self):
        node = self.parse_or()
        # ternary: `value if condition else other`
        # only consume `if` here if the previous token produced a value (which it always does here)
        # and the next token is IF
        if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.IF:
            self.eat()
            test = self.parse_or()
            self.eat(TKN_GROUP_KEYWORDS.ELSE)
            orelse = self.parse_ternary()
            return IfExpNode(test, node, orelse)
        return node

    def parse_or(self):
        left = self.parse_and()
        while not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.OR:
            self.eat()
            right = self.parse_and()
            left = BoolOpNode(TKN_GROUP_KEYWORDS.OR, [left, right])
        return left

    def parse_and(self):
        left = self.parse_not()
        while not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.AND:
            self.eat()
            right = self.parse_not()
            left = BoolOpNode(TKN_GROUP_KEYWORDS.AND, [left, right])
        return left

    def parse_not(self):
        if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.NOT:
            # peek ahead: `not in` is a compare op
            if self.peek(1) and self.peek(1).type == TKN_GROUP_KEYWORDS.IN:
                pass  # fall through to compare
            else:
                self.eat()
                return UnaryOpNode(TKN_GROUP_KEYWORDS.NOT, self.parse_not())
        return self.parse_compare()

    def parse_compare(self):
        left = self.parse_bitor()
        ops = []
        comparators = []
        while not self.at_end():
            t = self.peek()
            if t.type in COMPARE_OPS:
                ops.append(self.eat().type)
                comparators.append(self.parse_bitor())
            elif t.type == TKN_GROUP_KEYWORDS.NOT and self.peek(1) and self.peek(1).type == TKN_GROUP_KEYWORDS.IN:
                self.eat(); self.eat()
                ops.append(TKN_GROUP_KEYWORDS.NOT_IN)
                comparators.append(self.parse_bitor())
            elif t.type == TKN_GROUP_KEYWORDS.IS and self.peek(1) and self.peek(1).type == TKN_GROUP_KEYWORDS.NOT:
                self.eat(); self.eat()
                ops.append(TKN_GROUP_KEYWORDS.IS_NOT)
                comparators.append(self.parse_bitor())
            else:
                break
        if ops:
            return CompareNode(left, ops, comparators)
        return left

    def parse_bitor(self):
        left = self.parse_bitxor()
        while not self.at_end() and self.peek().type == TKN_GROUP_OPERATORS.PIPE:
            self.eat()
            left = BinOpNode(left, TKN_GROUP_OPERATORS.PIPE, self.parse_bitxor())
        return left

    def parse_bitxor(self):
        left = self.parse_bitand()
        while not self.at_end() and self.peek().type == TKN_GROUP_OPERATORS.CARET:
            self.eat()
            left = BinOpNode(left, TKN_GROUP_OPERATORS.CARET, self.parse_bitand())
        return left

    def parse_bitand(self):
        left = self.parse_shift()
        while not self.at_end() and self.peek().type == TKN_GROUP_OPERATORS.AMP:
            self.eat()
            left = BinOpNode(left, TKN_GROUP_OPERATORS.AMP, self.parse_shift())
        return left

    def parse_shift(self):
        left = self.parse_add()
        while not self.at_end() and self.peek().type in (TKN_GROUP_OPERATORS.LSHIFT, TKN_GROUP_OPERATORS.RSHIFT):
            op = self.eat().type
            left = BinOpNode(left, op, self.parse_add())
        return left

    def parse_add(self):
        left = self.parse_mul()
        while not self.at_end() and self.peek().type in (TKN_GROUP_OPERATORS.PLUS, TKN_GROUP_OPERATORS.MINUS):
            op = self.eat().type
            left = BinOpNode(left, op, self.parse_mul())
        return left

    def parse_mul(self):
        left = self.parse_unary()
        while not self.at_end() and self.peek().type in (
            TKN_GROUP_OPERATORS.STAR, TKN_GROUP_OPERATORS.SLASH,
            TKN_GROUP_OPERATORS.DSLASH, TKN_GROUP_OPERATORS.PERCENT,
            TKN_GROUP_OPERATORS.AT
        ):
            op = self.eat().type
            left = BinOpNode(left, op, self.parse_unary())
        return left

    def parse_unary(self):
        if not self.at_end():
            t = self.peek()
            if t.type == TKN_GROUP_OPERATORS.MINUS:
                self.eat()
                return UnaryOpNode(TKN_GROUP_OPERATORS.MINUS, self.parse_unary())
            elif t.type == TKN_GROUP_OPERATORS.PLUS:
                self.eat()
                return UnaryOpNode(TKN_GROUP_OPERATORS.PLUS, self.parse_unary())
            elif t.type == TKN_GROUP_OPERATORS.TILDE:
                self.eat()
                return UnaryOpNode(TKN_GROUP_OPERATORS.TILDE, self.parse_unary())
        return self.parse_power()

    def parse_power(self):
        base = self.parse_await()
        if not self.at_end() and self.peek().type == TKN_GROUP_OPERATORS.DSTAR:
            self.eat()
            exp = self.parse_unary()
            return BinOpNode(base, TKN_GROUP_OPERATORS.DSTAR, exp)
        return base

    def parse_await(self):
        if not self.at_end() and self.peek().type == TKN_GROUP_KEYWORDS.AWAIT:
            self.eat()
            # Was parse_primary(), which only consumes the bare identifier
            # ("fetch_data") and left the following "(a)" call parens
            # unconsumed here -- they'd then get mis-parsed as a separate
            # trailing expression, which is why `await fetch_data(a)` failed
            # with "Undefined variable: fetch_data" (the call arguments
            # were never attached to the call, so `fetch_data` surfaced
            # again downstream as a bare, non-callable variable reference).
            return AwaitNode(self.parse_call_attr())
        return self.parse_call_attr()

    def parse_call_attr(self):
        node = self.parse_primary()
        while not self.at_end():
            t = self.peek()
            if t.type == TKN_GROUP_SPECIAL.DOT:
                self.eat()
                attr = self.eat(TKN_VARIABLE_GROUP.VARIABLE).value
                node = AttributeNode(node, attr)
            elif t.type == TKN_GROUP_SPECIAL.BRACKET_NORMOPEN:
                self.eat()
                args, kwargs = self.parse_callargs()
                self.eat(TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE)
                if isinstance(node, VariableNode) and node.name == "print":
                    node = PrintNode(args, kwargs)
                elif isinstance(node, VariableNode) and node.name == "range":
                    node = RangeNode(args)
                else:
                    node = CallNode(node, args, kwargs)
            elif t.type == TKN_GROUP_SPECIAL.BRACKET_LISTOPEN:
                self.eat()
                index = self.parse_slice()
                self.eat(TKN_GROUP_SPECIAL.BRACKET_LISTCLOSE)
                node = SubscriptNode(node, index)
            else:
                break
        return node

    def parse_slice(self):
        lower = None; upper = None; step = None
        if not self.at_end() and self.peek().type != TKN_GROUP_SPECIAL.COLON:
            lower = self.parse_expr()
        if not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COLON:
            self.eat()
            if not self.at_end() and self.peek().type not in (TKN_GROUP_SPECIAL.COLON, TKN_GROUP_SPECIAL.BRACKET_LISTCLOSE):
                upper = self.parse_expr()
            if not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COLON:
                self.eat()
                if not self.at_end() and self.peek().type != TKN_GROUP_SPECIAL.BRACKET_LISTCLOSE:
                    step = self.parse_expr()
            return SliceNode(lower, upper, step)
        return lower

    def parse_callargs(self):
        args = []; kwargs = {}
        while not self.at_end() and self.peek().type != TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE:
            self.skip(TKN_GROUP_SPECIAL.COMMA)
            if self.at_end() or self.peek().type == TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE:
                break
            if self.peek().type == TKN_GROUP_OPERATORS.DSTAR:
                self.eat(); kwargs["**"] = self.parse_expr()
            elif self.peek().type == TKN_GROUP_OPERATORS.STAR:
                self.eat(); args.append(StarredNode(self.parse_expr()))
            elif (self.peek().type == TKN_VARIABLE_GROUP.VARIABLE and
                  self.peek(1) and self.peek(1).type == TKN_GROUP_OPERATORS.EQ):
                key = self.eat().value; self.eat()
                kwargs[key] = self.parse_expr()
            else:
                args.append(self.parse_expr())
        return args, kwargs

    def parse_primary(self):
        if self.at_end():
            last_line = self.tokens[-1].line if self.tokens else None
            raise PyCCSyntaxError("Unexpected end of tokens", line=last_line)
        t = self.peek()

        if t.type == TKN_GROUP_DATATYPES.INT:
            self.eat(); return IntNode(t.value)
        elif t.type == TKN_GROUP_DATATYPES.FLOAT:
            self.eat(); return FloatNode(t.value)
        elif t.type == TKN_GROUP_DATATYPES.STR:
            self.eat(); return StringNode(t.value)
        elif t.type == TKN_GROUP_DATATYPES.FSTR:
            self.eat(); return FStringNode(t.value)
        elif t.type == TKN_GROUP_DATATYPES.BOOL_TRUE:
            self.eat(); return BoolNode(True)
        elif t.type == TKN_GROUP_DATATYPES.BOOL_FALSE:
            self.eat(); return BoolNode(False)
        elif t.type == TKN_GROUP_DATATYPES.NONE:
            self.eat(); return NoneNode()
        elif t.type == TKN_GROUP_KEYWORDS.LAMBDA:
            self.eat()
            args = []
            while not self.at_end() and self.peek().type != TKN_GROUP_SPECIAL.COLON:
                self.skip(TKN_GROUP_SPECIAL.COMMA)
                if self.peek().type == TKN_GROUP_SPECIAL.COLON:
                    break
                args.append(self.eat(TKN_VARIABLE_GROUP.VARIABLE).value)
            self.eat(TKN_GROUP_SPECIAL.COLON)
            body = self.parse_expr()
            return LambdaNode(args, body)
        elif t.type == TKN_GROUP_SPECIAL.BRACKET_NORMOPEN:
            self.eat()
            if not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE:
                self.eat(); return TupleNode([])
            expr = self.parse_expr()
            if not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COMMA:
                elts = [expr]
                while not self.at_end() and self.peek().type == TKN_GROUP_SPECIAL.COMMA:
                    self.eat()
                    if self.peek().type == TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE:
                        break
                    elts.append(self.parse_expr())
                self.eat(TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE)
                return TupleNode(elts)
            self.eat(TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE)
            return expr
        elif t.type == TKN_GROUP_SPECIAL.BRACKET_LISTOPEN:
            self.eat()
            elts = []
            while not self.at_end() and self.peek().type != TKN_GROUP_SPECIAL.BRACKET_LISTCLOSE:
                self.skip(TKN_GROUP_SPECIAL.COMMA)
                if self.peek().type == TKN_GROUP_SPECIAL.BRACKET_LISTCLOSE:
                    break
                elts.append(self.parse_expr())
            self.eat(TKN_GROUP_SPECIAL.BRACKET_LISTCLOSE)
            return ListNode(elts)
        elif t.type == TKN_GROUP_SPECIAL.BRACKET_DICTOPEN:
            self.eat()
            keys = []; values = []
            while not self.at_end() and self.peek().type != TKN_GROUP_SPECIAL.BRACKET_DICTCLOSE:
                self.skip(TKN_GROUP_SPECIAL.COMMA)
                if self.peek().type == TKN_GROUP_SPECIAL.BRACKET_DICTCLOSE:
                    break
                k = self.parse_expr()
                self.eat(TKN_GROUP_SPECIAL.COLON)
                v = self.parse_expr()
                keys.append(k); values.append(v)
            self.eat(TKN_GROUP_SPECIAL.BRACKET_DICTCLOSE)
            return DictNode(keys, values)
        elif t.type == TKN_VARIABLE_GROUP.VARIABLE:
            self.eat(); return VariableNode(t.value)
        elif t.type in set(TKN_GROUP_BUILTINS):
            self.eat(); return VariableNode(t.type.name.lower())
        elif t.type in EXCEPTION_TOKEN_NAME:
            self.eat(); return VariableNode(EXCEPTION_TOKEN_NAME[t.type])
        else:
            name = MODULE_TOKEN_NAME.get(t.type)
            if name is not None:
                self.eat(); return VariableNode(name)
            raise PyCCSyntaxError(
                f"Unexpected token: {t.type} ({t.value!r})",
                line=t.line)


def parse(tokens):
    return Parser(tokens).parse()