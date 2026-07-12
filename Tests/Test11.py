# Test11 - Strings: concat, f-strings, raw, triple
a = "Hello"
b = "World"
c = a + " " + b
print(c)
print(len(c))

x = 42
msg = f"The answer is {x}"
print(msg)

name = "PyCC"
version = 1
info = f"Compiler: {name} v{version}"
print(info)

raw = r"No\escape\here"
print(raw)

triple = """This is
a multiline string"""
print(triple)

print(str(100))
print(str(3.14))
