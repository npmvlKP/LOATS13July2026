"""Top-level package marker for the LOATS13July2026 source tree.

Adding this file ensures that the ``src`` directory is recognised as a proper
Python package. This eliminates the MyPy "Source file found twice" error that
occurs when the same module can be imported both as ``loats`` (because ``src``
is on ``sys.path``) and as ``src.loats`` (when ``src`` itself is treated as a
package). The file is intentionally empty aside from the explanatory docstring.
"""
