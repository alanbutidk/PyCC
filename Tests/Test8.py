# Test8 - Control flow: if/elif/else, while, for, break, continue
x = 15

if x > 20:
    print("big")
elif x > 10:
    print("medium")
else:
    print("small")

i = 0
while i < 5:
    print(i)
    i += 1

for c in "PyCC":
    print(c)

i = 0
while i < 10:
    i += 1
    if i == 3:
        continue
    if i == 6:
        break
    print(i)
