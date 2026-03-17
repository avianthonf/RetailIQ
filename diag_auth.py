import os
import sys

# Add project root to sys.path
root = r"d:\Files\Desktop\RetailIQ-Final-Workspace\RetailIQ"
if root not in sys.path:
    sys.path.insert(0, root)

try:
    from app.auth import utils

    print(f"app.auth.utils found at: {utils.__file__}")
    print(f"Attributes in utils: {dir(utils)}")
    if hasattr(utils, "get_redis_client"):
        print("SUCCESS: get_redis_client FOUND")
    else:
        print("FAILURE: get_redis_client NOT FOUND")
except Exception as e:
    print(f"ERROR: {e}")
