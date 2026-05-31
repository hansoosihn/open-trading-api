import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_trading_system import obtain_and_save_keys

try:
    path = obtain_and_save_keys()
    print("SAVED:", path)
except Exception as e:
    print("ERROR:", repr(e))
    import traceback
    traceback.print_exc()
    sys.exit(2)
