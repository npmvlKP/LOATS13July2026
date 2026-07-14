# Test file to verify pre-commit hooks
import os


def test_function():
    # This should trigger ruff and mypy checks
    x = "test"
    print(x + 5)  # This will cause a type error

    # This should trigger bandit security check
    os.system("ls")

    # This is a secret that should trigger gitleaks
    api_key = "AKIAEXAMPLE1234567890"

    return x


if __name__ == "__main__":
    test_function()
