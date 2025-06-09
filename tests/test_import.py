import importlib
import sys
from pathlib import Path

# Add repository root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

def test_bot_imports():
    assert importlib.import_module('src.bot')
