import os
import glob


__version__ = "v0.1"

all_senders_path = os.path.join(os.path.dirname(__file__), "all_senders")
all_senders_files = glob.glob(os.path.join(all_senders_path, "*.py"))
__all_senders__ = [
    os.path.splitext(os.path.basename(f))[0]
    for f in all_senders_files
    if not f.endswith("__init__.py")
]
