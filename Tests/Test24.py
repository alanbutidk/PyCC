# Test24 - Async functions (compiled as sync)
async def fetch_data(x):
    return x * 2

async def process(a, b):
    result = await fetch_data(a)
    return result + b

print(fetch_data(5))
print(process(3, 10))

async def pipeline(n):
    x = await fetch_data(n)
    y = await fetch_data(x)
    return y

print(pipeline(4))
