from src.loats.utils.rate_limiter import rate_limited, RateLimitExceededError

# Test the sync rate limited decorator
@rate_limited(max_ops=2, window_size=1.0)
def test_func(x):
    return x * 2

print('First call:', test_func(1))
print('Second call:', test_func(2))

try:
    print('Third call:', test_func(3))
except RateLimitExceededError as e:
    print('Third call failed as expected:', str(e))