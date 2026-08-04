import subprocess, sys
r = subprocess.run(['git', 'push', 'origin', 'main', '--force'], capture_output=True, text=True, timeout=120, cwd='D:\\AISleepGen_Optimized')
print('STDOUT:', r.stdout[-500:])
print('STDERR:', r.stderr[-500:])
print('RETURN:', r.returncode)
