with open("main.py", 'r') as f:
    string = f.read()

print(len(string))

lines = string.split("\n")

piece = ""
for line in lines:
    x = len(piece + line)
    if len(piece + line) >= 4000:
        print(piece)
        piece = ""
    else:
        piece += line + "\n"

    x


