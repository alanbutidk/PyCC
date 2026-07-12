# Test27 - global keyword, list.append
counter = 0

def increment():
    global counter
    counter += 1

increment()
increment()
increment()
print(counter)

total = 0

def add_to_total(n):
    global total
    total += n

add_to_total(10)
add_to_total(20)
add_to_total(30)
print(total)

items = [1, 2, 3]
print(len(items))
items.append(4)
items.append(5)
print(len(items))
