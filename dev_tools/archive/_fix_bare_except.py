"""Fix all 'bare except:' to 'except Exception:' 
Retains existing except Exception: lines"""
import re

path = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Count before
bare_before = len(re.findall(r'^(\s*)except:\s*$', content, re.MULTILINE))

# Replace bare except: with except Exception:
# Match: a line starting with whitespace + "except:", 
# followed by a line with whitespace + "pass"
replaced = re.sub(
    r'^(\s*)except:\s*$\n(\s+)pass\s*$',
    lambda m: m.group(1) + 'except Exception:\n' + m.group(2) + 'pass  # non-critical',
    content,
    flags=re.MULTILINE
)

bare_after = len(re.findall(r'^(\s*)except:\s*$', replaced, re.MULTILINE))

with open(path, 'w', encoding='utf-8') as f:
    f.write(replaced)

print(f'bare except: before={bare_before}  after={bare_after}')
print(f'except Exception: pass count now = {replaced.count("except Exception:")}')
