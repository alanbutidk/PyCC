# Test26 - builtins: isinstance, hasattr, zip, enumerate, map, filter
x = 5
s = "hello"
f = 3.14

print(isinstance(x, int))
print(isinstance(s, str))
print(hasattr(x, "__add__"))
print(callable(print))
print(id(x) > 0)
print(repr(42))
print(repr("hi"))
print(hash(42))
print(all([1, 1, 1]))
print(any([0, 0, 1]))
