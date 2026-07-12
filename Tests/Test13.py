# Test13 - Number literals: hex, binary, octal, scientific, underscores
a = 0xFF
b = 0b1010
c = 0o17
d = 1_000_000
e = 1.5e2

print(a)
print(b)
print(c)
print(d)
print(e)

x = 0xFF & 0x0F
print(x)
y = 0b1010 | 0b0101
print(y)
z = 0xFF ^ 0x0F
print(z)
print(1 << 4)
print(256 >> 3)
print(~5)
