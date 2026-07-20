import re

with open('src/loats/scheduler.py', 'r') as f:
    content = f.read()

# Fix 1: Change import line
content = content.replace('.openalgo import client openalgo_client', '.openalgo import async_client')

# Fix 2: Change all usages of openalgo_client to async_client
content = content.replace('awaitopenalgo_client', 'awaitasync_client')
content = content.replace('openalgo_client', 'async_client')

with open('src/loats/scheduler.py', 'w') as f:
    f.write(content)

print("Fixed scheduler.py")