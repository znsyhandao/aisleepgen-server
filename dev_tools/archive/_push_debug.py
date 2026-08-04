import subprocess, sys

# Try pushing with full error capture
try:
    r = subprocess.run(
        ['git', 'push', 'origin', 'main', '--force'],
        capture_output=True, text=True, timeout=120,
        cwd='D:\\AISleepGen_Optimized'
    )
    print('=== STDOUT ===')
    print(r.stdout[-1000:])
    print('=== STDERR ===')
    print(r.stderr[-1000:])
    print(f'=== RETURN CODE: {r.returncode} ===')
except subprocess.TimeoutExpired:
    print('TIMEOUT - GitHub connection slow')
except Exception as e:
    print(f'ERROR: {e}')
