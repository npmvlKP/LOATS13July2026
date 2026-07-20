with open('src/loats/openalgo.py', 'rb') as f:
    lines = f.readlines()
    for i, line in enumerate(lines[:10]):
        print(f"{i}: {line}")