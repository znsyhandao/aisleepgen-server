# diagnose.py
import sys
import platform
import os
import subprocess

print("=" * 50)
print("系统诊断信息")
print("=" * 50)

print(f"Python版本: {sys.version}")
print(f"Python路径: {sys.executable}")
print(f"当前工作目录: {os.getcwd()}")
print(f"操作系统: {platform.system()} {platform.release()}")
print(f"架构: {platform.architecture()}")

print("\n" + "=" * 50)
print("环境变量")
print("=" * 50)
print(f"PATH: {os.environ.get('PATH', 'Not set')[:200]}...")  # 只显示前200字符

print("\n" + "=" * 50)
print("PyTorch相关文件检查")
print("=" * 50)

torch_site_packages = r"D:\conda_cache\envs\neuroforge_311\Lib\site-packages\torch"
if os.path.exists(torch_site_packages):
    print(f"[OK] PyTorch安装目录存在: {torch_site_packages}")
    
    # 检查关键的DLL文件
    lib_dir = os.path.join(torch_site_packages, "lib")
    if os.path.exists(lib_dir):
        dll_files = [f for f in os.listdir(lib_dir) if f.endswith('.dll')]
        print(f"找到 {len(dll_files)} 个DLL文件:")
        for dll in dll_files[:10]:  # 只显示前10个
            print(f"  - {dll}")
        
        # 检查c10.dll
        c10_path = os.path.join(lib_dir, "c10.dll")
        if os.path.exists(c10_path):
            size = os.path.getsize(c10_path) / 1024 / 1024
            print(f"\n[OK] c10.dll 存在，大小: {size:.2f} MB")
        else:
            print(f"\n[FAIL] c10.dll 不存在！")
    else:
        print(f"[FAIL] lib目录不存在: {lib_dir}")
else:
    print(f"[FAIL] PyTorch安装目录不存在: {torch_site_packages}")

print("\n" + "=" * 50)
print("尝试导入PyTorch")
print("=" * 50)

try:
    # 尝试先导入numpy（有时可以绕过一些问题）
    import numpy as np
    print(f"[OK] NumPy导入成功: {np.__version__}")
    
    # 尝试导入PyTorch
    import torch
    print(f"[OK] PyTorch导入成功!")
    print(f"  版本: {torch.__version__}")
    print(f"  CUDA可用: {torch.cuda.is_available()}")
    
    # 创建一个简单的张量测试
    x = torch.randn(3, 3)
    print(f"  张量测试: {x.shape}")
    
except ImportError as e:
    print(f"[FAIL] 导入失败: {e}")
    
    # 检查是否是因为DLL问题
    if "DLL" in str(e) or "1114" in str(e):
        print("\n这是DLL加载错误，可能是以下原因:")
        print("1. 环境冲突 - 建议创建新环境")
        print("2. 杀毒软件拦截 - 临时禁用杀毒软件")
        print("3. 系统文件损坏 - 运行系统文件检查")
        
except Exception as e:
    print(f"[FAIL] 其他错误: {e}")
    print(f"错误类型: {type(e).__name__}")

print("\n" + "=" * 50)
print("建议解决方案")
print("=" * 50)

print("""
1. 最简单的解决方案：创建全新的干净环境
   conda deactivate
   conda remove -n neuroforge_311 --all -y
   conda create -n neuroforge python=3.10 -y
   conda activate neuroforge
   pip install torch --index-url https://download.pytorch.org/whl/cpu

2. 如果不想重新创建环境，尝试修复：
   pip uninstall torch torchvision torchaudio -y
   pip install torch --index-url https://download.pytorch.org/whl/cpu --force-reinstall

3. 使用conda安装（有时更稳定）：
   conda install pytorch torchvision torchaudio cpuonly -c pytorch

4. 检查杀毒软件：临时禁用后重试

5. 运行系统文件检查：
   sfc /scannow
""")