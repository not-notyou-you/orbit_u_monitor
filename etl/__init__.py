import os

try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except ImportError:  # python-dotenv opsional saat runtime minimal
    pass

for _var in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_var, None)
del _var

os.environ.setdefault("GDAL_CACHEMAX", "4096")  # MB
os.environ.setdefault("GDAL_NUM_THREADS", "ALL_CPUS")

WARP_THREADS = max(1, (os.cpu_count() or 1))
