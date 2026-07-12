import subprocess as s

try:
    import blablabla as bla
except (ImportError, ModuleNotFoundError):
    print("Test Passed!")
a = s.run(["echo", "Hi!"], capture_output=True, shell=True, text=True)
if a.returncode != 0:
    print("Failed!")
else:
    print("Passed!")
raise SystemExit("Exiting!")
