"""Tokenize.py -> Converts source into tokens with proper INDENT/DEDENT/NEWLINE support.
Format of a token: TKN_XXXX_XXXX
Example: TKN_VAR_X, -> TKN_INT(5) -> TKN_VAR_X: int 5"""
from dataclasses import dataclass
from typing import Any
from enum import Enum, auto

class TKN_GROUP_DATATYPES(Enum):
    INT = auto()
    STR = auto()
    FSTR = auto()
    BOOL_TRUE = auto()
    BOOL_FALSE = auto()
    NONE = auto()
    LIST = auto()
    DICT = auto()
    FLOAT = auto()
    TUPLE = auto()
    COMPLEX = auto()
    BYTES = auto()
    SET = auto()

class TKN_GROUP_EXCEPTIONS(Enum):
    EXCEPTION = auto()
    BASE_EXCEPTION = auto()
    SYSTEM_EXIT = auto()
    KEYBOARD_INTERRUPT = auto()
    GENERATOR_EXIT = auto()
    ARITHMETIC_ERROR = auto()
    ZERO_DIVISION_ERROR = auto()
    OVERFLOW_ERROR = auto()
    FLOATING_POINT_ERROR = auto()
    LOOKUP_ERROR = auto()
    INDEX_ERROR = auto()
    KEY_ERROR = auto()
    ATTRIBUTE_ERROR = auto()
    IMPORT_ERROR = auto()
    MODULE_NOT_FOUND_ERROR = auto()
    NAME_ERROR = auto()
    UNBOUND_LOCAL_ERROR = auto()
    OS_ERROR = auto()
    IO_ERROR = auto()
    FILE_NOT_FOUND_ERROR = auto()
    PERMISSION_ERROR = auto()
    TIMEOUT_ERROR = auto()
    RUNTIME_ERROR = auto()
    NOT_IMPLEMENTED_ERROR = auto()
    RECURSION_ERROR = auto()
    STOP_ITERATION = auto()
    STOP_ASYNC_ITERATION = auto()
    SYNTAX_ERROR = auto()
    INDENTATION_ERROR = auto()
    TAB_ERROR = auto()
    SYSTEM_ERROR = auto()
    TYPE_ERROR = auto()
    VALUE_ERROR = auto()
    UNICODE_ERROR = auto()
    UNICODE_DECODE_ERROR = auto()
    UNICODE_ENCODE_ERROR = auto()
    UNICODE_TRANSLATE_ERROR = auto()
    MEMORY_ERROR = auto()
    BUFFER_ERROR = auto()
    EOF_ERROR = auto()
    CONNECTION_ERROR = auto()
    BROKEN_PIPE_ERROR = auto()
    CONNECTION_ABORTED_ERROR = auto()
    CONNECTION_REFUSED_ERROR = auto()
    CONNECTION_RESET_ERROR = auto()
    FILE_EXISTS_ERROR = auto()
    INTERRUPTED_ERROR = auto()
    IS_A_DIRECTORY_ERROR = auto()
    NOT_A_DIRECTORY_ERROR = auto()
    CHILD_PROCESS_ERROR = auto()
    PROCESS_LOOKUP_ERROR = auto()
    WARNING = auto()
    USER_WARNING = auto()
    DEPRECATION_WARNING = auto()
    RUNTIME_WARNING = auto()
    SYNTAX_WARNING = auto()
    RESOURCE_WARNING = auto()
    FUTURE_WARNING = auto()
    IMPORT_WARNING = auto()
    UNICODE_WARNING = auto()
    BYTES_WARNING = auto()
    ASSERTION_ERROR = auto()
    ENVIRONMENT_ERROR = auto()
    EXCEPTION_GROUP = auto()

# maps Python source name -> (token, exit_code, is_warning)
BUILTIN_EXCEPTIONS: dict = {
    "Exception":                (TKN_GROUP_EXCEPTIONS.EXCEPTION,               1, False),
    "BaseException":            (TKN_GROUP_EXCEPTIONS.BASE_EXCEPTION,           1, False),
    "SystemExit":               (TKN_GROUP_EXCEPTIONS.SYSTEM_EXIT,              0, False),
    "KeyboardInterrupt":        (TKN_GROUP_EXCEPTIONS.KEYBOARD_INTERRUPT,       130, False),
    "GeneratorExit":            (TKN_GROUP_EXCEPTIONS.GENERATOR_EXIT,           0, False),
    "ArithmeticError":          (TKN_GROUP_EXCEPTIONS.ARITHMETIC_ERROR,         1, False),
    "ZeroDivisionError":        (TKN_GROUP_EXCEPTIONS.ZERO_DIVISION_ERROR,      1, False),
    "OverflowError":            (TKN_GROUP_EXCEPTIONS.OVERFLOW_ERROR,           1, False),
    "FloatingPointError":       (TKN_GROUP_EXCEPTIONS.FLOATING_POINT_ERROR,     1, False),
    "LookupError":              (TKN_GROUP_EXCEPTIONS.LOOKUP_ERROR,             1, False),
    "IndexError":               (TKN_GROUP_EXCEPTIONS.INDEX_ERROR,              1, False),
    "KeyError":                 (TKN_GROUP_EXCEPTIONS.KEY_ERROR,                1, False),
    "AttributeError":           (TKN_GROUP_EXCEPTIONS.ATTRIBUTE_ERROR,          1, False),
    "ImportError":              (TKN_GROUP_EXCEPTIONS.IMPORT_ERROR,             1, False),
    "ModuleNotFoundError":      (TKN_GROUP_EXCEPTIONS.MODULE_NOT_FOUND_ERROR,   1, False),
    "NameError":                (TKN_GROUP_EXCEPTIONS.NAME_ERROR,               1, False),
    "UnboundLocalError":        (TKN_GROUP_EXCEPTIONS.UNBOUND_LOCAL_ERROR,      1, False),
    "OSError":                  (TKN_GROUP_EXCEPTIONS.OS_ERROR,                 1, False),
    "IOError":                  (TKN_GROUP_EXCEPTIONS.IO_ERROR,                 1, False),
    "FileNotFoundError":        (TKN_GROUP_EXCEPTIONS.FILE_NOT_FOUND_ERROR,     1, False),
    "PermissionError":          (TKN_GROUP_EXCEPTIONS.PERMISSION_ERROR,         1, False),
    "TimeoutError":             (TKN_GROUP_EXCEPTIONS.TIMEOUT_ERROR,            1, False),
    "RuntimeError":             (TKN_GROUP_EXCEPTIONS.RUNTIME_ERROR,            1, False),
    "NotImplementedError":      (TKN_GROUP_EXCEPTIONS.NOT_IMPLEMENTED_ERROR,    1, False),
    "RecursionError":           (TKN_GROUP_EXCEPTIONS.RECURSION_ERROR,          1, False),
    "StopIteration":            (TKN_GROUP_EXCEPTIONS.STOP_ITERATION,           0, False),
    "StopAsyncIteration":       (TKN_GROUP_EXCEPTIONS.STOP_ASYNC_ITERATION,     0, False),
    "SyntaxError":              (TKN_GROUP_EXCEPTIONS.SYNTAX_ERROR,             1, False),
    "IndentationError":         (TKN_GROUP_EXCEPTIONS.INDENTATION_ERROR,        1, False),
    "TabError":                 (TKN_GROUP_EXCEPTIONS.TAB_ERROR,                1, False),
    "SystemError":              (TKN_GROUP_EXCEPTIONS.SYSTEM_ERROR,             1, False),
    "TypeError":                (TKN_GROUP_EXCEPTIONS.TYPE_ERROR,               1, False),
    "ValueError":               (TKN_GROUP_EXCEPTIONS.VALUE_ERROR,              1, False),
    "UnicodeError":             (TKN_GROUP_EXCEPTIONS.UNICODE_ERROR,            1, False),
    "UnicodeDecodeError":       (TKN_GROUP_EXCEPTIONS.UNICODE_DECODE_ERROR,     1, False),
    "UnicodeEncodeError":       (TKN_GROUP_EXCEPTIONS.UNICODE_ENCODE_ERROR,     1, False),
    "UnicodeTranslateError":    (TKN_GROUP_EXCEPTIONS.UNICODE_TRANSLATE_ERROR,  1, False),
    "MemoryError":              (TKN_GROUP_EXCEPTIONS.MEMORY_ERROR,             1, False),
    "BufferError":              (TKN_GROUP_EXCEPTIONS.BUFFER_ERROR,             1, False),
    "EOFError":                 (TKN_GROUP_EXCEPTIONS.EOF_ERROR,                1, False),
    "ConnectionError":          (TKN_GROUP_EXCEPTIONS.CONNECTION_ERROR,         1, False),
    "BrokenPipeError":          (TKN_GROUP_EXCEPTIONS.BROKEN_PIPE_ERROR,        1, False),
    "ConnectionAbortedError":   (TKN_GROUP_EXCEPTIONS.CONNECTION_ABORTED_ERROR, 1, False),
    "ConnectionRefusedError":   (TKN_GROUP_EXCEPTIONS.CONNECTION_REFUSED_ERROR, 1, False),
    "ConnectionResetError":     (TKN_GROUP_EXCEPTIONS.CONNECTION_RESET_ERROR,   1, False),
    "FileExistsError":          (TKN_GROUP_EXCEPTIONS.FILE_EXISTS_ERROR,        1, False),
    "InterruptedError":         (TKN_GROUP_EXCEPTIONS.INTERRUPTED_ERROR,        1, False),
    "IsADirectoryError":        (TKN_GROUP_EXCEPTIONS.IS_A_DIRECTORY_ERROR,     1, False),
    "NotADirectoryError":       (TKN_GROUP_EXCEPTIONS.NOT_A_DIRECTORY_ERROR,    1, False),
    "ChildProcessError":        (TKN_GROUP_EXCEPTIONS.CHILD_PROCESS_ERROR,      1, False),
    "ProcessLookupError":       (TKN_GROUP_EXCEPTIONS.PROCESS_LOOKUP_ERROR,     1, False),
    "Warning":                  (TKN_GROUP_EXCEPTIONS.WARNING,                  0, True),
    "UserWarning":              (TKN_GROUP_EXCEPTIONS.USER_WARNING,             0, True),
    "DeprecationWarning":       (TKN_GROUP_EXCEPTIONS.DEPRECATION_WARNING,      0, True),
    "RuntimeWarning":           (TKN_GROUP_EXCEPTIONS.RUNTIME_WARNING,          0, True),
    "SyntaxWarning":            (TKN_GROUP_EXCEPTIONS.SYNTAX_WARNING,           0, True),
    "ResourceWarning":          (TKN_GROUP_EXCEPTIONS.RESOURCE_WARNING,         0, True),
    "FutureWarning":            (TKN_GROUP_EXCEPTIONS.FUTURE_WARNING,           0, True),
    "ImportWarning":            (TKN_GROUP_EXCEPTIONS.IMPORT_WARNING,           0, True),
    "UnicodeWarning":           (TKN_GROUP_EXCEPTIONS.UNICODE_WARNING,          0, True),
    "BytesWarning":             (TKN_GROUP_EXCEPTIONS.BYTES_WARNING,            0, True),
    "AssertionError":           (TKN_GROUP_EXCEPTIONS.ASSERTION_ERROR,          1, False),
    "EnvironmentError":         (TKN_GROUP_EXCEPTIONS.ENVIRONMENT_ERROR,        1, False),
    "ExceptionGroup":           (TKN_GROUP_EXCEPTIONS.EXCEPTION_GROUP,          1, False),
}

# reverse map: token -> source name
EXCEPTION_TOKEN_NAME: dict = {v[0]: k for k, v in BUILTIN_EXCEPTIONS.items()}

# set of "import-related" exception tokens — used by try/except compile-time resolution
IMPORT_EXCEPTIONS = {
    TKN_GROUP_EXCEPTIONS.IMPORT_ERROR,
    TKN_GROUP_EXCEPTIONS.MODULE_NOT_FOUND_ERROR,
    TKN_GROUP_EXCEPTIONS.ATTRIBUTE_ERROR,
    TKN_GROUP_EXCEPTIONS.NAME_ERROR,
}

# set of exit exceptions — raise these = clean exit
EXIT_EXCEPTIONS = {
    TKN_GROUP_EXCEPTIONS.SYSTEM_EXIT,
    TKN_GROUP_EXCEPTIONS.KEYBOARD_INTERRUPT,
    TKN_GROUP_EXCEPTIONS.GENERATOR_EXIT,
    TKN_GROUP_EXCEPTIONS.STOP_ITERATION,
    TKN_GROUP_EXCEPTIONS.STOP_ASYNC_ITERATION,
}

class TKN_GROUP_KEYWORDS(Enum):
    AND = auto()
    OR = auto()
    NOT = auto()
    IS = auto()
    IS_NOT = auto()
    IN = auto()
    NOT_IN = auto()
    ASSERT = auto()
    ASYNC = auto()
    AWAIT = auto()
    BREAK = auto()
    CONTINUE = auto()
    DEL = auto()
    ELIF = auto()
    ELSE = auto()
    IF = auto()
    EXCEPT = auto()
    AS = auto()
    FINALLY = auto()
    FOR = auto()
    FROM = auto()
    GLOBAL = auto()
    IMPORT = auto()
    LAMBDA = auto()
    NONLOCAL = auto()
    PASS = auto()
    RAISE = auto()
    RETURN = auto()
    TRY = auto()
    WHILE = auto()
    WITH = auto()
    YIELD = auto()
    DEF = auto()
    CLASS = auto()

class TKN_GROUP_OPERATORS(Enum):
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    DSTAR = auto()
    SLASH = auto()
    DSLASH = auto()
    PERCENT = auto()
    AT = auto()
    EQ = auto()
    PLUS_EQ = auto()
    MINUS_EQ = auto()
    STAR_EQ = auto()
    DSTAR_EQ = auto()
    SLASH_EQ = auto()
    DSLASH_EQ = auto()
    PERCENT_EQ = auto()
    AT_EQ = auto()
    AMP_EQ = auto()
    PIPE_EQ = auto()
    CARET_EQ = auto()
    RSHIFT_EQ = auto()
    LSHIFT_EQ = auto()
    EQEQ = auto()
    NEQ = auto()
    LT = auto()
    GT = auto()
    LEQ = auto()
    GEQ = auto()
    AMP = auto()
    PIPE = auto()
    CARET = auto()
    TILDE = auto()
    RSHIFT = auto()
    LSHIFT = auto()
    ARROW = auto()
    WALRUS = auto()

class TKN_GROUP_SPECIAL(Enum):
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()
    SPACE = auto()
    COMMENT = auto()
    MULTI_COMMENT = auto()
    COMMA = auto()
    TAB = auto()
    QUOTE = auto()
    SINGLE_QUOTE = auto()
    SEMICOLON = auto()
    COLON = auto()
    DOT = auto()
    BRACKET_NORMOPEN = auto()
    BRACKET_NORMCLOSE = auto()
    BRACKET_DICTOPEN = auto()
    BRACKET_DICTCLOSE = auto()
    BRACKET_LISTOPEN = auto()
    BRACKET_LISTCLOSE = auto()

class TKN_GROUP_DUNDERS(Enum):
    DUNDER_NEW = auto()
    DUNDER_INIT = auto()
    DUNDER_DEL = auto()
    DUNDER_REPR = auto()
    DUNDER_STR = auto()
    DUNDER_BYTES = auto()
    DUNDER_FORMAT = auto()
    DUNDER_LT = auto()
    DUNDER_LE = auto()
    DUNDER_EQ = auto()
    DUNDER_NE = auto()
    DUNDER_GT = auto()
    DUNDER_GE = auto()
    DUNDER_HASH = auto()
    DUNDER_LEN = auto()
    DUNDER_GETITEM = auto()
    DUNDER_SETITEM = auto()
    DUNDER_DELITEM = auto()
    DUNDER_ITER = auto()
    DUNDER_NEXT = auto()
    DUNDER_CONTAINS = auto()
    DUNDER_GETATTR = auto()
    DUNDER_SETATTR = auto()
    DUNDER_ADD = auto()
    DUNDER_SUB = auto()
    DUNDER_MUL = auto()
    DUNDER_TRUEDIV = auto()
    DUNDER_FLOORDIV = auto()
    DUNDER_MOD = auto()
    DUNDER_POW = auto()
    DUNDER_AND = auto()
    DUNDER_OR = auto()
    DUNDER_XOR = auto()
    DUNDER_LSHIFT = auto()
    DUNDER_RSHIFT = auto()
    DUNDER_ENTER = auto()
    DUNDER_EXIT = auto()
    DUNDER_CALL = auto()

class TKN_VARIABLE_GROUP(Enum):
    VARIABLE = auto()

class TKN_GROUP_BUILTINS(Enum):
    PRINT = auto()
    INPUT = auto()
    EXEC = auto()
    INT = auto()
    STR = auto()
    LIST = auto()
    DICT = auto()
    TUPLE = auto()
    SET = auto()
    RANGE = auto()
    ABS = auto()
    DIVMOD = auto()
    MAX = auto()
    MIN = auto()
    POW = auto()
    ROUND = auto()
    SUM = auto()
    BIN = auto()
    HEX = auto()
    OCT = auto()
    BOOL = auto()
    BYTEARRAY = auto()
    BYTES = auto()
    COMPLEX = auto()
    FLOAT = auto()
    OBJECT = auto()
    TYPE = auto()
    ALL = auto()
    ANY = auto()
    ENUMERATE = auto()
    FILTER = auto()
    ITER = auto()
    LEN = auto()
    MAP = auto()
    NEXT = auto()
    REVERSED = auto()
    SLICE = auto()
    SORTED = auto()
    ZIP = auto()
    OPEN = auto()
    CALLABLE = auto()
    DELATTR = auto()
    DIR = auto()
    HASATTR = auto()
    ID = auto()
    ISINSTANCE = auto()
    ISSUBCLASS = auto()
    SETATTR = auto()
    VARS = auto()
    ASCII = auto()
    CHR = auto()
    ORD = auto()
    FORMAT = auto()
    REPR = auto()
    GLOBALS = auto()
    LOCALS = auto()
    HASH = auto()
    PROPERTY = auto()
    CLASSMETHOD = auto()
    STATICMETHOD = auto()
    SUPER = auto()

@dataclass
class Token:
    type: Enum
    value: Any = None
    # Populated by tokenize() after tokenize_line() returns, rather than
    # threaded through every individual Token(...) call site in
    # tokenize_line() (there are dozens) -- tokenize() knows which
    # physical source line it's currently scanning, so it's the simplest
    # place to stamp this on uniformly. None until that happens (e.g. for
    # tokens built directly by tests/tools that skip tokenize()).
    line: Any = None

def GenTokenEnum(module):
    import importlib
    members = {}
    for name in dir(module):
        if name.startswith("__"):
            CleanName = name.strip("_").upper()
            members[f"DUNDER_{CleanName}"] = auto()
        elif not name.startswith("_"):
            members[name.upper()] = auto()
    enum_cls = Enum(f"TKN_GROUP_{module.__name__.upper()}", members)
    # attach a reverse name map so parser/compiler can recover the original name
    enum_cls._member_name_map = {m: name for name, m in zip(
        [k for k in members], enum_cls
    )}
    return enum_cls

# Global registry: token_type -> original identifier string
# Used by parser to recover name from any GenTokenEnum token
MODULE_TOKEN_NAME: dict = {}

def register_module_tokens(enum_cls):
    """Register all members of a GenTokenEnum into the global name map."""
    for member in enum_cls:
        original = member.name  # e.g. "RETURNCODE"
        # recover original casing from the enum name map if available
        MODULE_TOKEN_NAME[member] = original.lower()

OPERATOR_MAP = {
    "**=": TKN_GROUP_OPERATORS.DSTAR_EQ,
    "//=": TKN_GROUP_OPERATORS.DSLASH_EQ,
    ">>=": TKN_GROUP_OPERATORS.RSHIFT_EQ,
    "<<=": TKN_GROUP_OPERATORS.LSHIFT_EQ,
    "**":  TKN_GROUP_OPERATORS.DSTAR,
    "//":  TKN_GROUP_OPERATORS.DSLASH,
    "+=":  TKN_GROUP_OPERATORS.PLUS_EQ,
    "-=":  TKN_GROUP_OPERATORS.MINUS_EQ,
    "*=":  TKN_GROUP_OPERATORS.STAR_EQ,
    "/=":  TKN_GROUP_OPERATORS.SLASH_EQ,
    "%=":  TKN_GROUP_OPERATORS.PERCENT_EQ,
    "@=":  TKN_GROUP_OPERATORS.AT_EQ,
    "&=":  TKN_GROUP_OPERATORS.AMP_EQ,
    "|=":  TKN_GROUP_OPERATORS.PIPE_EQ,
    "^=":  TKN_GROUP_OPERATORS.CARET_EQ,
    "==":  TKN_GROUP_OPERATORS.EQEQ,
    "!=":  TKN_GROUP_OPERATORS.NEQ,
    "<=":  TKN_GROUP_OPERATORS.LEQ,
    ">=":  TKN_GROUP_OPERATORS.GEQ,
    ">>":  TKN_GROUP_OPERATORS.RSHIFT,
    "<<":  TKN_GROUP_OPERATORS.LSHIFT,
    "->":  TKN_GROUP_OPERATORS.ARROW,
    ":=":  TKN_GROUP_OPERATORS.WALRUS,
    "+":   TKN_GROUP_OPERATORS.PLUS,
    "-":   TKN_GROUP_OPERATORS.MINUS,
    "*":   TKN_GROUP_OPERATORS.STAR,
    "/":   TKN_GROUP_OPERATORS.SLASH,
    "%":   TKN_GROUP_OPERATORS.PERCENT,
    "@":   TKN_GROUP_OPERATORS.AT,
    "=":   TKN_GROUP_OPERATORS.EQ,
    "<":   TKN_GROUP_OPERATORS.LT,
    ">":   TKN_GROUP_OPERATORS.GT,
    "&":   TKN_GROUP_OPERATORS.AMP,
    "|":   TKN_GROUP_OPERATORS.PIPE,
    "^":   TKN_GROUP_OPERATORS.CARET,
    "~":   TKN_GROUP_OPERATORS.TILDE,
}

SPECIAL_MAP = {
    "(": TKN_GROUP_SPECIAL.BRACKET_NORMOPEN,
    ")": TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE,
    "{": TKN_GROUP_SPECIAL.BRACKET_DICTOPEN,
    "}": TKN_GROUP_SPECIAL.BRACKET_DICTCLOSE,
    "[": TKN_GROUP_SPECIAL.BRACKET_LISTOPEN,
    "]": TKN_GROUP_SPECIAL.BRACKET_LISTCLOSE,
    ";": TKN_GROUP_SPECIAL.SEMICOLON,
    ":": TKN_GROUP_SPECIAL.COLON,
    ",": TKN_GROUP_SPECIAL.COMMA,
    ".": TKN_GROUP_SPECIAL.DOT
}

KEYWORD_MAP = {
    "and":      TKN_GROUP_KEYWORDS.AND,
    "or":       TKN_GROUP_KEYWORDS.OR,
    "not":      TKN_GROUP_KEYWORDS.NOT,
    "is":       TKN_GROUP_KEYWORDS.IS,
    "in":       TKN_GROUP_KEYWORDS.IN,
    "assert":   TKN_GROUP_KEYWORDS.ASSERT,
    "async":    TKN_GROUP_KEYWORDS.ASYNC,
    "await":    TKN_GROUP_KEYWORDS.AWAIT,
    "break":    TKN_GROUP_KEYWORDS.BREAK,
    "continue": TKN_GROUP_KEYWORDS.CONTINUE,
    "del":      TKN_GROUP_KEYWORDS.DEL,
    "elif":     TKN_GROUP_KEYWORDS.ELIF,
    "else":     TKN_GROUP_KEYWORDS.ELSE,
    "if":       TKN_GROUP_KEYWORDS.IF,
    "except":   TKN_GROUP_KEYWORDS.EXCEPT,
    "as":       TKN_GROUP_KEYWORDS.AS,
    "finally":  TKN_GROUP_KEYWORDS.FINALLY,
    "for":      TKN_GROUP_KEYWORDS.FOR,
    "from":     TKN_GROUP_KEYWORDS.FROM,
    "global":   TKN_GROUP_KEYWORDS.GLOBAL,
    "import":   TKN_GROUP_KEYWORDS.IMPORT,
    "lambda":   TKN_GROUP_KEYWORDS.LAMBDA,
    "nonlocal": TKN_GROUP_KEYWORDS.NONLOCAL,
    "pass":     TKN_GROUP_KEYWORDS.PASS,
    "raise":    TKN_GROUP_KEYWORDS.RAISE,
    "return":   TKN_GROUP_KEYWORDS.RETURN,
    "try":      TKN_GROUP_KEYWORDS.TRY,
    "while":    TKN_GROUP_KEYWORDS.WHILE,
    "with":     TKN_GROUP_KEYWORDS.WITH,
    "yield":    TKN_GROUP_KEYWORDS.YIELD,
    "def":      TKN_GROUP_KEYWORDS.DEF,
    "class":    TKN_GROUP_KEYWORDS.CLASS,
}

BUILTIN_MAP = {m.name.lower(): m for m in TKN_GROUP_BUILTINS}

def _parse_fstring(s: str) -> list:
    """Parse an f-string into a list of (is_expr, text_or_tokens) parts."""
    parts = []
    buf = ""
    i = 0
    while i < len(s):
        if s[i] == '{' and i + 1 < len(s) and s[i+1] != '{':
            if buf:
                parts.append((False, buf))
                buf = ""
            i += 1
            expr_buf = ""
            depth = 1
            while i < len(s) and depth > 0:
                if s[i] == '{':
                    depth += 1
                elif s[i] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                expr_buf += s[i]
                i += 1
            i += 1  # skip closing }
            parts.append((True, expr_buf.strip()))
        elif s[i] == '{' and i + 1 < len(s) and s[i+1] == '{':
            buf += '{'
            i += 2
        elif s[i] == '}' and i + 1 < len(s) and s[i+1] == '}':
            buf += '}'
            i += 2
        else:
            buf += s[i]
            i += 1
    if buf:
        parts.append((False, buf))
    return parts

def tokenize_line(line: str) -> list:
    """Tokenize a single line (no leading whitespace, no newline handling)."""
    tokens = []
    i = 0
    while i < len(line):
        ch = line[i]

        # skip spaces and tabs mid-line
        if ch in (' ', '\t'):
            i += 1
            continue

        if ch == '#':
            tokens.append(Token(TKN_GROUP_SPECIAL.COMMENT, line[i+1:]))
            break

        # f-strings
        if ch in ('f', 'F') and i + 1 < len(line) and line[i+1] in ('"', "'"):
            i += 1
            quote = line[i]
            i += 1
            buf = ""
            while i < len(line) and line[i] != quote:
                if line[i] == '\\' and i + 1 < len(line):
                    buf += line[i] + line[i+1]
                    i += 2
                else:
                    buf += line[i]
                    i += 1
            i += 1
            parts = _parse_fstring(buf)
            tokens.append(Token(TKN_GROUP_DATATYPES.FSTR, parts))
            continue

        # raw strings: r"...", R"..." -- backslashes are literal, no
        # escape processing at all (that's the entire point of a raw
        # string). Previously unhandled: `r"..."` tokenized as a bare
        # identifier `r` immediately followed by a separate string token,
        # which then surfaced downstream as "Undefined variable: r" the
        # first time that name got referenced as an expression.
        if ch in ('r', 'R') and i + 1 < len(line) and line[i+1] in ('"', "'"):
            i += 1
            quote = line[i]
            i += 1
            buf = ""
            while i < len(line) and line[i] != quote:
                buf += line[i]
                i += 1
            i += 1
            tokens.append(Token(TKN_GROUP_DATATYPES.STR, buf))
            continue

        # regular strings
        if ch in ('"', "'"):
            quote = ch
            i += 1
            buf = ""
            while i < len(line) and line[i] != quote:
                if line[i] == '\\' and i + 1 < len(line):
                    buf += line[i] + line[i+1]
                    i += 2
                else:
                    buf += line[i]
                    i += 1
            tokens.append(Token(TKN_GROUP_DATATYPES.STR, buf))
            i += 1
            continue

        if ch in SPECIAL_MAP:
            tokens.append(Token(SPECIAL_MAP[ch]))
            i += 1
            # after a dot, force the next identifier to always be VARIABLE
            if SPECIAL_MAP[ch] == TKN_GROUP_SPECIAL.DOT:
                # consume the identifier right here
                if i < len(line) and (line[i].isalpha() or line[i] == '_'):
                    buf = ""
                    while i < len(line) and (line[i].isalnum() or line[i] == '_'):
                        buf += line[i]
                        i += 1
                    tokens.append(Token(TKN_VARIABLE_GROUP.VARIABLE, buf))
            continue

        # operators (longest match first)
        op_match = None
        for op in OPERATOR_MAP:
            if line[i:i+len(op)] == op:
                op_match = op
                break
        if op_match:
            tokens.append(Token(OPERATOR_MAP[op_match]))
            i += len(op_match)
            continue

        if ch.isalpha() or ch == '_':
            buf = ""
            while i < len(line) and (line[i].isalnum() or line[i] == '_'):
                buf += line[i]
                i += 1
            if buf in KEYWORD_MAP:
                tokens.append(Token(KEYWORD_MAP[buf]))
            elif buf in BUILTIN_EXCEPTIONS:
                tokens.append(Token(BUILTIN_EXCEPTIONS[buf][0], buf))
            elif buf in BUILTIN_MAP:
                tokens.append(Token(BUILTIN_MAP[buf]))
            elif buf == "True":
                tokens.append(Token(TKN_GROUP_DATATYPES.BOOL_TRUE))
            elif buf == "False":
                tokens.append(Token(TKN_GROUP_DATATYPES.BOOL_FALSE))
            elif buf == "None":
                tokens.append(Token(TKN_GROUP_DATATYPES.NONE))
            else:
                tokens.append(Token(TKN_VARIABLE_GROUP.VARIABLE, buf))
            continue

        if ch.isdigit():
            # hex / binary / octal prefixes (0x.., 0b.., 0o..). Previously
            # totally unhandled: `0xFF` tokenized as INT(0) followed by a
            # bare identifier "xFF", since the digit scanner only ever
            # continued on isdigit()/underscore and had no prefix check at
            # all -- every hex/bin/oct literal in the language silently
            # produced 0 (or a parse error) instead of its real value.
            if ch == '0' and i + 1 < len(line) and line[i+1] in ('x', 'X', 'b', 'B', 'o', 'O'):
                prefix = line[i+1].lower()
                i += 2
                start = i
                valid = {'x': "0123456789abcdefABCDEF_", 'b': "01_", 'o': "01234567_"}[prefix]
                while i < len(line) and line[i] in valid:
                    i += 1
                digits = line[start:i].replace('_', '')
                base = {'x': 16, 'b': 2, 'o': 8}[prefix]
                tokens.append(Token(TKN_GROUP_DATATYPES.INT, int(digits, base) if digits else 0))
                continue

            buf = ""
            while i < len(line) and (line[i].isdigit() or line[i] == '_'):
                buf += line[i]
                i += 1
            is_float = False
            if i < len(line) and line[i] == '.':
                is_float = True
                buf += '.'
                i += 1
                while i < len(line) and (line[i].isdigit() or line[i] == '_'):
                    buf += line[i]
                    i += 1
            # scientific notation exponent: 1.5e2, 1e-3, 2E+10 -- previously
            # unhandled, so e.g. `1.5e2` tokenized as FLOAT(1.5) followed
            # by a bare identifier "e2".
            if i < len(line) and line[i] in ('e', 'E') and i + 1 < len(line) and \
               (line[i+1].isdigit() or (line[i+1] in ('+', '-') and i + 2 < len(line) and line[i+2].isdigit())):
                is_float = True
                buf += 'e'
                i += 1
                if line[i] in ('+', '-'):
                    buf += line[i]; i += 1
                while i < len(line) and line[i].isdigit():
                    buf += line[i]
                    i += 1
            if is_float:
                tokens.append(Token(TKN_GROUP_DATATYPES.FLOAT, float(buf.replace('_', ''))))
            else:
                tokens.append(Token(TKN_GROUP_DATATYPES.INT, int(buf.replace('_', ''))))
            continue

        i += 1

    return tokens

def _collapse_triple_quoted(source: str) -> str:
    """
    Rewrite every triple-quoted string ("\"\"\"..." or '''...''') into an
    equivalent single-line, backslash-escaped regular string literal, so
    the existing (line-oriented) tokenizer can handle it with its normal
    string-scanning logic unchanged.

    Previously there was no real triple-quote handling at all (despite a
    comment in tokenize() claiming there was): a triple-quoted string
    tokenized as three separate single-quote string tokens plus stray
    bare identifiers for every word inside it, since tokenize_line()
    naively scans up to the *next* single quote character. This collapses
    the multi-line literal into `"escaped text"` first, before line
    splitting ever happens.

    Also preserves the original line count: collapsing a multi-line
    string down to one line would otherwise shift every line number after
    it (off by however many newlines got swallowed), which broke the
    line numbers used in "Line N: ..." error messages for any error
    occurring after a triple-quoted string anywhere earlier in the file.
    Trailing blank lines are appended right after the collapsed literal
    to make up the difference, so `splitlines()` downstream still lines
    up 1:1 with the real source.
    """
    out = []
    i = 0
    n = len(source)
    while i < n:
        if source[i:i+3] in ('"""', "'''"):
            delim = source[i:i+3]
            i += 3
            buf = []
            consumed_newlines = 0
            while i < n and source[i:i+3] != delim:
                ch = source[i]
                if ch == '\\':
                    buf.append('\\\\')
                    i += 1
                elif ch == '"':
                    buf.append('\\"')
                    i += 1
                elif ch == '\n':
                    buf.append('\\n')
                    consumed_newlines += 1
                    i += 1
                elif ch == '\r':
                    i += 1  # drop bare CR, \n above already encodes the newline
                else:
                    buf.append(ch)
                    i += 1
            i += 3  # skip closing delimiter
            out.append('"' + "".join(buf) + '"')
            out.append('\n' * consumed_newlines)
        else:
            out.append(source[i])
            i += 1
    return "".join(out)


def tokenize(source: str) -> list:
    """Tokenize full source with INDENT/DEDENT/NEWLINE tokens."""
    source = _collapse_triple_quoted(source)
    tokens = []
    indent_stack = [0]
    paren_depth = 0  # track open parens/brackets to suppress NEWLINE inside them

    lines = source.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        # handle triple-quoted strings (multiline)
        stripped = line.lstrip()

        # skip blank lines and comment-only lines
        if not stripped or stripped.startswith('#'):
            i += 1
            continue

        # measure indent
        indent = len(line) - len(stripped)

        # emit INDENT/DEDENT only when not inside brackets
        if paren_depth == 0:
            if indent > indent_stack[-1]:
                indent_stack.append(indent)
                tokens.append(Token(TKN_GROUP_SPECIAL.INDENT, line=i + 1))
            else:
                while indent < indent_stack[-1]:
                    indent_stack.pop()
                    tokens.append(Token(TKN_GROUP_SPECIAL.DEDENT, line=i + 1))

        line_tokens = tokenize_line(stripped)
        for t in line_tokens:
            t.line = i + 1  # 1-based, for "Line N: ..." error messages

        # track paren depth to handle multi-line expressions
        for t in line_tokens:
            if t.type in (TKN_GROUP_SPECIAL.BRACKET_NORMOPEN,
                          TKN_GROUP_SPECIAL.BRACKET_LISTOPEN,
                          TKN_GROUP_SPECIAL.BRACKET_DICTOPEN):
                paren_depth += 1
            elif t.type in (TKN_GROUP_SPECIAL.BRACKET_NORMCLOSE,
                            TKN_GROUP_SPECIAL.BRACKET_LISTCLOSE,
                            TKN_GROUP_SPECIAL.BRACKET_DICTCLOSE):
                paren_depth = max(0, paren_depth - 1)

        tokens.extend(line_tokens)

        if paren_depth == 0:
            tokens.append(Token(TKN_GROUP_SPECIAL.NEWLINE, line=i + 1))

        i += 1

    # close any remaining indents
    last_line = len(lines)
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token(TKN_GROUP_SPECIAL.DEDENT, line=last_line))

    tokens.append(Token(TKN_GROUP_SPECIAL.NEWLINE, line=last_line))
    return tokens