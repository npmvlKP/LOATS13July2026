import re

with open('src/loats/openalgo.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix async method return types - add Awaitable wrapper for non-generator async functions
replacements = [
    (r'async def get_position_book\(self\) -> dict\[str, Any\]:', 'async def get_position_book(self) -> Awaitable[dict[str, Any]]:\n'),
    (r'async def get_funds\(self\) -> dict\[str, Any\]:', 'async def get_funds(self) -> Awaitable[dict[str, Any]]:\n'),
    (r'async def cancel_order\(self, order_id: str\) -> dict\[str, Any\]:', 'async def cancel_order(self, order_id: str) -> Awaitable[dict[str, Any]]:\n'),
    (r'async def get_order_status\(self, order_id: str\) -> dict\[str, Any\]:', 'async def get_order_status(self, order_id: str) -> Awaitable[dict[str, Any]]:\n'),
    (r'async def get_all_orders\(self\) -> dict\[str, Any\]:', 'async def get_all_orders(self) -> Awaitable[dict[str, Any]]:\n'),
    (r'async def get_trade_book\(self\) -> dict\[str, Any\]:', 'async def get_trade_book(self) -> Awaitable[dict[str, Any]]:\n'),
]

for pattern, repl in replacements:
    content = re.sub(pattern, repl, content)

with open('src/loats/openalgo.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed openalgo.py return types')