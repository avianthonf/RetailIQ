import sys

import pytest

with open("test_results.txt", "w", encoding="utf-8") as f:
    sys.stdout = f
    sys.stderr = f
    pytest.main(["tests/test_market_intelligence.py", "-v", "--tb=short"])
