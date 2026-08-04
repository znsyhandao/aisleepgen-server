from setuptools import setup, find_packages

setup(
    name="aisleep",
    version="0.1",
    package_dir={"": "src"},
    packages=find_packages(where="src", include=["aisleep*"]),  # Explicit include
    install_requires=[
        "torch>=2.0",
        "numpy>=1.20",
        "mne==1.9.0"  # Pinned version for stability
    ],
    python_requires=">=3.8",
    # ... 前面的代码保持不变 ...
    include_package_data=True,  # Ensure non-Python files are included
    zip_safe=False,  # Disable zip installs
    package_data={
        "aisleep": ["*.json", "*.yaml", "*.txt"]  # 扩展支持的文件类型
    },
    entry_points={
        "console_scripts": [
            "aisleep=aisleep.cli:main",  # 简化命令名称
            "aisleep-analysis=aisleep.analysis:run"  # 新增分析命令
        ],
    },

    # ... 后面的代码保持不变 ...

)
