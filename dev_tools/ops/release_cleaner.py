#!/usr/bin/env python3
"""
Pre-release Cleaner - Ensure clean release packages, no cache files
"""

import os
import sys
import shutil
import zipfile
from pathlib import Path

class PreReleaseCleaner:
    """发布前清理器"""
    
    def __init__(self, skill_dir):
        self.skill_dir = Path(skill_dir)
        self.cleanup_log = []
        
        # 需要清理的文件和目录模式
        self.cleanup_patterns = [
            # Python缓存
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            ".pytest_cache",
            ".mypy_cache",
            
            # 临时文件
            "*.tmp",
            "*.temp",
            "*.log",
            "*.bak",
            "*.backup",
            
            # 构建文件
            "build/",
            "dist/",
            "*.egg-info",
            
            # 版本控制
            ".git/",
            ".svn/",
            ".hg/",
            
            # 编辑器文件
            ".vscode/",
            ".idea/",
            "*.swp",
            "*.swo",
            
            # 其他
            "Thumbs.db",
            ".DS_Store",
            "desktop.ini"
        ]
        
        # 必需文件列表
        self.required_files = [
            "skill.py",
            "config.yaml",
            "SKILL.md",
            "README.md",
            "CHANGELOG.md",
            "requirements.txt"
        ]
    
    def clean_directory(self):
        """清理目录"""
        print("=" * 80)
        print("发布前清理器 - 开始清理")
        print("=" * 80)
        print(f"清理目录: {self.skill_dir}")
        
        total_cleaned = 0
        
        # 清理文件和目录
        for pattern in self.cleanup_patterns:
            if pattern.endswith("/"):  # 目录模式
                dir_pattern = pattern.rstrip("/")
                for dir_path in self.skill_dir.rglob(dir_pattern):
                    if dir_path.is_dir():
                        try:
                            shutil.rmtree(dir_path)
                            self.cleanup_log.append(f"删除目录: {dir_path.relative_to(self.skill_dir)}")
                            total_cleaned += 1
                        except Exception as e:
                            self.cleanup_log.append(f"删除目录失败 {dir_path}: {e}")
            else:  # 文件模式
                for file_path in self.skill_dir.rglob(pattern):
                    if file_path.is_file():
                        try:
                            file_path.unlink()
                            self.cleanup_log.append(f"删除文件: {file_path.relative_to(self.skill_dir)}")
                            total_cleaned += 1
                        except Exception as e:
                            self.cleanup_log.append(f"删除文件失败 {file_path}: {e}")
        
        print(f"清理完成: 删除了 {total_cleaned} 个文件/目录")
        return total_cleaned
    
    def check_required_files(self):
        """检查必需文件"""
        print("\n" + "=" * 80)
        print("检查必需文件")
        print("=" * 80)
        
        missing_files = []
        present_files = []
        
        for filename in self.required_files:
            file_path = self.skill_dir / filename
            if file_path.exists():
                size_kb = file_path.stat().st_size / 1024
                print(f"[OK] {filename}: {size_kb:.1f}KB")
                present_files.append(filename)
            else:
                print(f"[MISSING] {filename}")
                missing_files.append(filename)
        
        print(f"\n文件状态: {len(present_files)}/{len(self.required_files)} 存在")
        
        if missing_files:
            print(f"[ERROR] 缺失文件: {', '.join(missing_files)}")
            return False
        
        return True
    
    def create_clean_zip(self, output_name=None):
        """创建干净的ZIP包"""
        print("\n" + "=" * 80)
        print("创建干净ZIP包")
        print("=" * 80)
        
        if output_name:
            zip_name = output_name
        else:
            # 从config.yaml获取技能名称和版本
            config_path = self.skill_dir / "config.yaml"
            skill_name = "skill"
            skill_version = "1.0.0"
            
            if config_path.exists():
                try:
                    import yaml
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                    skill_name = config.get("skill", {}).get("name", "skill")
                    skill_version = config.get("skill", {}).get("version", "1.0.0")
                except Exception:
            zip_name = f"{skill_name}-v{skill_version}.zip"
        
        zip_path = self.skill_dir / zip_name
        
        # 删除旧的ZIP文件
        for old_zip in self.skill_dir.glob("*.zip"):
            try:
                old_zip.unlink()
                print(f"删除旧ZIP: {old_zip.name}")
            except Exception:
        # 创建新的ZIP包
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename in self.required_files:
                file_path = self.skill_dir / filename
                if file_path.exists():
                    zipf.write(file_path, filename)
                    print(f"添加到ZIP: {filename}")
        
        size_kb = zip_path.stat().st_size / 1024
        print(f"\nZIP包创建完成: {zip_path.name}")
        print(f"文件大小: {size_kb:.1f}KB")
        print(f"包含文件: {len(self.required_files)}个")
        
        return zip_path
    
    def generate_report(self):
        """生成清理报告"""
        report_path = self.skill_dir / "cleanup_report.md"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# 发布前清理报告\n\n")
            f.write(f"**清理目录**: {self.skill_dir}\n")
            f.write(f"**清理时间**: {self._current_time()}\n\n")
            
            f.write("## 清理日志\n")
            if self.cleanup_log:
                for log_entry in self.cleanup_log:
                    f.write(f"- {log_entry}\n")
            else:
                f.write("无清理操作\n")
            
            f.write("\n## 必需文件状态\n")
            for filename in self.required_files:
                file_path = self.skill_dir / filename
                if file_path.exists():
                    size_kb = file_path.stat().st_size / 1024
                    f.write(f"- ✅ {filename}: {size_kb:.1f}KB\n")
                else:
                    f.write(f"- ❌ {filename}: 缺失\n")
            
            f.write("\n## 建议\n")
            f.write("1. 运行永久审核框架验证技能\n")
            f.write("2. 测试技能功能\n")
            f.write("3. 提交到ClawHub\n")
        
        print(f"\n清理报告已保存: {report_path}")
        return report_path
    
    def _current_time(self):
        """获取当前时间"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def run_full_cleanup(self):
        """运行完整清理流程"""
        print("=" * 80)
        print("发布前完整清理流程")
        print("=" * 80)
        
        # 1. 清理目录
        cleaned_count = self.clean_directory()
        
        # 2. 检查必需文件
        files_ok = self.check_required_files()
        if not files_ok:
            print("[ERROR] 必需文件缺失，无法继续")
            return False
        
        # 3. 创建干净ZIP包
        zip_path = self.create_clean_zip()
        
        # 4. 生成报告
        report_path = self.generate_report()
        
        print("\n" + "=" * 80)
        print("清理完成！")
        print("=" * 80)
        print(f"清理文件/目录: {cleaned_count}个")
        print(f"ZIP包: {zip_path.name}")
        print(f"报告: {report_path.name}")
        print("\n下一步:")
        print("1. 运行永久审核框架验证")
        print("2. 测试技能功能")
        print("3. 发布到ClawHub")
        
        return True

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("发布前清理器")
        print("=" * 60)
        print("使用方法:")
        print("  python pre_release_cleaner.py <技能目录>")
        print("")
        print("示例:")
        print("  python pre_release_cleaner.py D:\\openclaw\\releases\\skill-name")
        print("")
        print("功能:")
        print("  1. 清理缓存文件和临时文件")
        print("  2. 检查必需文件")
        print("  3. 创建干净ZIP包")
        print("  4. 生成清理报告")
        return
    
    skill_dir = sys.argv[1]
    
    if not Path(skill_dir).exists():
        print(f"[ERROR] 目录不存在: {skill_dir}")
        return
    
    cleaner = PreReleaseCleaner(skill_dir)
    cleaner.run_full_cleanup()

if __name__ == "__main__":
    main()