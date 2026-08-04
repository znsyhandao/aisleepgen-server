# Quick boot test for deepseek_proxy
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Clean cache
import shutil
for d in ['__pycache__', 'sleep_edf_validate/__pycache__']:
    p = os.path.join(os.getcwd(), d)
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)

# Try import - this is what will fail at module level
try:
    import deepseek_proxy
    print('[OK] deepseek_proxy imported successfully')
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

print('[OK] deepseek_proxy loaded, ProxyHandler has methods:')
from deepseek_proxy import ProxyHandler
for name in ['_handle_sleep_from_face', '_handle_audio_analysis', '_handle_audio_status', '_handle_audio_upload']:
    print(f'  {name}: {hasattr(ProxyHandler, name)}')
