from src.modules import Modules


def test_modules_load():
    mod = Modules()
    assert mod.load() is None
