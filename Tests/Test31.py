# Test31 - File I/O
f = open("pycc_test_out.txt", "w")
f.write("Hello from PyCC!\n")
f.write("Line 2\n")
f.close()

f = open("pycc_test_out.txt", "r")
content = f.read()
f.close()
print(content)

f = open("pycc_test_out.txt", "r")
line = f.readline()
f.close()
print(line)
