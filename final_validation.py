#!/usr/bin/env python3
"""
Final validation of scalability fix.
"""

import asyncio

from src.loats.utils.cache import cache_manager, close_cache, initialize_cache


async def final_validation():
    """Final validation of scalability implementation."""
    print("Final validation of scalability fix...")

    # Initialize cache
    await initialize_cache()
    print("Cache initialized successfully")

    # Test basic operations
    print("Testing cache operations...")

    # Test 1: Set and get
    set_result = await cache_manager.set("validation_key", "validation_value")
    print(f"Set result: {set_result}")

    get_result = await cache_manager.get("validation_key")
    print(f"Get result: {get_result}")

    # Test 2: Statistics
    stats = await cache_manager.get_cache_stats()
    print(f"Cache stats: {stats}")

    # Test 3: Delete
    delete_result = await cache_manager.delete("validation_key")
    print(f"Delete result: {delete_result}")

    get_after_delete = await cache_manager.get("validation_key")
    print(f"Get after delete: {get_after_delete}")

    # Close cache
    await close_cache()
    print("Cache closed successfully")

    # Validate results
    success = all([
        set_result == True,
        get_result == "validation_value",
        stats['enabled'] == True,
        stats['connected'] == True,
        delete_result == True,
        get_after_delete is None
    ])

    if success:
        print("VALIDATION PASSED: All scalability fixes working correctly")
        return True
    else:
        print("VALIDATION FAILED: Some operations not working")
        return False

if __name__ == "__main__":
    result = asyncio.run(final_validation())
    exit(0 if result else 1)
