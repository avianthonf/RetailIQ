import numpy as np

# Patch for libraries that still use np.float_ (removed in NumPy 2.0)
if not hasattr(np, "float_"):
    np.float_ = np.float64

if not hasattr(np, "int_"):
    np.int_ = np.int64
