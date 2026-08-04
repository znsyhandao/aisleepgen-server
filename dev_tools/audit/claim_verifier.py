#!/usr/bin/env python3
"""
Security Claim Verifier
Verify security claims in documentation match actual code implementation
"""

import os
import re
import ast
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional

class SecurityClaimVerifier:
    """验证安全声明是否实施"""

    def __init__(self, skill_path: str):
        self.skill_path = Path(skill_path)
        self.results = []

    def verify_all(self) -> Dict[str, any]:
        """验证所有安全声明"""
        print("=" * 80)
        print("安全声明验证检查")
        print("=" * 80)

        checks = [
            ("路径限制声明验证", self.verify_path_restriction_claims),
            ("网络访问声明验证", self.verify_network_access_claims),
            ("Shell命令声明验证", self.verify_shell_command_claims),
            ("内存/时间限制声明验证", self.verify_resource_limit_claims),
            ("自动验证声明验证", self.verify_auto_validation_claims),
            ("导入限制声明验证", self.verify_import_restriction_claims),
        ]

        all_passed = True

        for check_name, check_func in checks:
            print(f"\n[检查] {check_name}")
            try:
                passed, evidence = check_func()
                if passed:
                    print(f"  [OK] 通过")
                else:
                    print(f"  [FAIL] 失败")
                    all_passed = False

                self.results.append({
                    "check": check_name,
                    "passed": passed,
                    "evidence": evidence
                })
            except Exception as e:
                print(f"  [ERROR] 错误: {e}")
                all_passed = False
                self.results.append({
                    "check": check_name,
                    "error": str(e)
                })

        print("\n" + "=" * 80)
        if all_passed:
            print("[SUCCESS] 所有安全声明验证通过")
        else:
            print("[FAILURE] 有安全声明验证失败")
            print("\n修复建议:")
            for result in self.results:
                if not result.get("passed", True):
                    evidence = result.get("evidence", {})
                    if "recommendation" in evidence:
                        print(f"  - {evidence['recommendation']}")
        print("=" * 80)

        return {
            "all_passed": all_passed,
            "results": self.results,
            "skill_path": str(self.skill_path)
        }

    def verify_path_restriction_claims(self) -> Tuple[bool, Dict]:
        """验证路径限制声明"""
        # 1. 检查文档中的路径限制声明
        doc_claims = self._extract_path_restriction_claims_from_docs()

        # 2. 检查代码中的路径限制实施
        code_implementation = self._check_path_restriction_implementation()

        # 3. 验证声明与实施的一致性
        if doc_claims and not code_implementation["implemented"]:
            return False, {
                "doc_claims": doc_claims,
                "code_implementation": code_implementation,
                "issue": "文档声称路径限制，但代码未实施",
                "recommendation": "实施PathValidator或移除虚假声明"
            }

        if not doc_claims and code_implementation["implemented"]:
            return True, {
                "doc_claims": doc_claims,
                "code_implementation": code_implementation,
                "note": "代码实施了路径限制但文档未声明"
            }

        return True, {
            "doc_claims": doc_claims,
            "code_implementation": code_implementation,
            "consistent": True
        }

    def verify_network_access_claims(self) -> Tuple[bool, Dict]:
        """验证网络访问声明"""
        # 检查文档中的网络访问声明
        doc_claims = self._extract_network_access_claims_from_docs()

        # 检查代码中的网络导入
        network_imports = self._find_network_imports_in_code()

        # 逻辑：如果声明无网络访问，代码中不应有网络导入
        if doc_claims.get("network_access") == "false" and network_imports:
            return False, {
                "doc_claims": doc_claims,
                "network_imports_found": network_imports,
                "issue": "文档声明无网络访问，但代码中有网络导入",
                "recommendation": "移除网络导入或更新文档声明"
            }

        return True, {
            "doc_claims": doc_claims,
            "network_imports_found": network_imports,
            "consistent": True
        }

    def verify_shell_command_claims(self) -> Tuple[bool, Dict]:
        """验证Shell命令声明"""
        # 检查文档中的Shell命令声明
        doc_claims = self._extract_shell_command_claims_from_docs()

        # 检查代码中的Shell命令
        shell_commands = self._find_shell_commands_in_code()

        # 逻辑：如果声明无Shell命令，代码中不应有Shell命令
        if doc_claims.get("shell_commands") == "false" and shell_commands:
            return False, {
                "doc_claims": doc_claims,
                "shell_commands_found": shell_commands,
                "issue": "文档声明无Shell命令，但代码中有Shell命令",
                "recommendation": "移除Shell命令或更新文档声明"
            }

        return True, {
            "doc_claims": doc_claims,
            "shell_commands_found": shell_commands,
            "consistent": True
        }

    def verify_resource_limit_claims(self) -> Tuple[bool, Dict]:
        """验证资源限制声明"""
        # 检查文档中的资源限制声明
        doc_claims = self._extract_resource_limit_claims_from_docs()

        # 检查代码中的资源限制实施
        code_implementation = self._check_resource_limit_implementation()

        # 验证声明与实施的一致性
        issues = []
        for claim_type, claim_value in doc_claims.items():
            if claim_value == "true" and not code_implementation.get(claim_type, False):
                issues.append(f"文档声称{claim_type}，但代码未实施")

        if issues:
            return False, {
                "doc_claims": doc_claims,
                "code_implementation": code_implementation,
                "issues": issues,
                "recommendation": "实施资源限制或从文档中移除声明"
            }

        return True, {
            "doc_claims": doc_claims,
            "code_implementation": code_implementation,
            "consistent": True
        }

    def verify_auto_validation_claims(self) -> Tuple[bool, Dict]:
        """验证自动验证声明"""
        # 检查文档中的自动验证声明
        doc_claims = self._extract_auto_validation_claims_from_docs()

        # 检查代码中的自动验证实施
        code_implementation = self._check_auto_validation_implementation()

        # 验证声明与实施的一致性
        issues = []
        for claim_type, claim_value in doc_claims.items():
            if claim_value == "true" and not code_implementation.get(claim_type, False):
                issues.append(f"文档声称{claim_type}，但代码未实施")

        if issues:
            return False, {
                "doc_claims": doc_claims,
                "code_implementation": code_implementation,
                "issues": issues,
                "recommendation": "实施自动验证或从文档中移除声明"
            }

        return True, {
            "doc_claims": doc_claims,
            "code_implementation": code_implementation,
            "consistent": True
        }

    def verify_import_restriction_claims(self) -> Tuple[bool, Dict]:
        """验证导入限制声明"""
        # 检查文档中的导入限制声明
        doc_claims = self._extract_import_restriction_claims_from_docs()

        # 检查代码中的外部导入
        external_imports = self._find_external_imports_in_code()

        # 逻辑：如果声明只有标准库导入，不应有外部导入
        if doc_claims.get("only_stdlib") == "true" and external_imports:
            return False, {
                "doc_claims": doc_claims,
                "external_imports_found": external_imports,
                "issue": "文档声明只有标准库导入，但代码中有外部导入",
                "recommendation": "移除外部导入或更新文档声明"
            }

        return True, {
            "doc_claims": doc_claims,
            "external_imports_found": external_imports,
            "consistent": True
        }

    # ========== 辅助方法 ==========

    def _extract_import_restriction_claims_from_docs(self) -> Dict[str, str]:
        """Extract import restriction claims from documentation"""
        claims = {}
        for file_path in self.skill_path.rglob("*.md"):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                if "only standard library" in content or "stdlib only" in content:
                    claims["only_stdlib"] = "true"
                if "no external" in content or "no third-party" in content:
                    claims["no_external"] = "true"
            except:
                continue
        return claims

    def _find_external_imports_in_code(self) -> List[str]:
        """Find external imports in code"""
        external_imports = []
        standard_lib = {"os", "sys", "json", "re", "math", "pathlib", "typing",
                        "collections", "itertools", "functools", "datetime",
                        "subprocess", "tempfile", "shutil", "hashlib", "uuid",
                        "unittest", "io", "textwrap", "copy", "enum"}
        for file_path in self.skill_path.rglob("*.py"):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        if line.startswith("import ") or line.startswith("from "):
                            parts = line.split()
                            if len(parts) >= 2:
                                module = parts[1].split(".")[0]
                                if module not in standard_lib and module not in {"__future__"}:
                                    external_imports.append(module)
            except:
                continue
        return list(set(external_imports))

    def _extract_path_restriction_claims_from_docs(self) -> Dict[str, str]:
        """从文档提取路径限制声明"""
        claims = {}

        for file_path in self.skill_path.rglob("*.md"):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()

                # 查找路径限制相关声明
                patterns = {
                    "path_restriction": r'restricted to (?:skill|plugin) directory',
                    "directory_restriction": r'limited to (?:allowed|specified) (?:directories|paths)',
                    "file_access_restriction": r'file access (?:restricted|limited)',
                    "path_validation": r'path (?:validation|verification)',
                }

                for claim_key, pattern in patterns.items():
                    if re.search(pattern, content, re.IGNORECASE):
                        claims[claim_key] = "true"
            except:
                continue

        return claims

    def _check_path_restriction_implementation(self) -> Dict[str, any]:
        """检查路径限制实施"""
        implementation = {
            "implemented": False,
            "path_validator_found": False,
            "file_operations_restricted": False,
            "details": {}
        }

        # 检查PathValidator类
        for file_path in self.skill_path.rglob("*.py"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 查找PathValidator或类似类
                if "PathValidator" in content or "path_validator" in content.lower():
                    implementation["path_validator_found"] = True

                    # 检查是否实施了路径验证
                    if "is_path_allowed" in content or "validate_path" in content:
                        implementation["implemented"] = True

                # 检查文件操作是否使用路径验证
                if "file_check" in content or "check_file_exists" in content:
                    # 检查是否调用了路径验证
                    if "is_path_allowed" in content or "validate_path" in content:
                        implementation["file_operations_restricted"] = True

            except:
                continue

        return implementation

    def _extract_network_access_claims_from_docs(self) -> Dict[str, str]:
        """从文档提取网络访问声明"""
        claims = {}

        for file_path in self.skill_path.rglob("*.md"):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()

                # 查找网络访问声明
                if "no network" in content or "network access: false" in content:
                    claims["network_access"] = "false"
                elif "network access: true" in content:
                    claims["network_access"] = "true"

            except:
                continue

        return claims

    def _find_network_imports_in_code(self) -> List[str]:
        """查找代码中的网络导入"""
        network_modules = [
            'socket', 'requests', 'urllib', 'http', 'ftplib', 'smtplib',
            'poplib', 'imaplib', 'telnetlib', 'asyncio', 'aiohttp',
            'websocket', 'httpx', 'urllib3', 'paramiko', 'ssh'
        ]

        found_imports = []

        for file_path in self.skill_path.rglob("*.py"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                for module in network_modules:
                    if f"import {module}" in content or f"from {module}" in content:
                        found_imports.append(f"{file_path.name}: {module}")
            except:
                continue

        return found_imports

    def _extract_shell_command_claims_from_docs(self) -> Dict[str, str]:
        """从文档提取Shell命令声明"""
        claims = {}

        for file_path in self.skill_path.rglob("*.md"):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()

                # 查找Shell命令声明
                if "no shell commands" in content or "shell commands: false" in content:
                    claims["shell_commands"] = "false"
                elif "shell commands: true" in content:
                    claims["shell_commands"] = "true"

            except:
                continue

        return claims

    def _find_shell_commands_in_code(self) -> List[str]:
        """查找代码中的Shell命令"""
        shell_patterns = [
            r'os\.system\(',
            r'os\.popen\(',
            r'subprocess\.',
            r'Popen\(',
            r'call\(',
            r'run\(',
            r'check_output\(',
        ]

        found_commands = []

        for file_path in self.skill_path.rglob("*.py"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                for pattern in shell_patterns:
                    if re.search(pattern, content):
                        found_commands.append(f"{file_path.name}: {pattern}")
            except:
                continue

        return found_commands

    def _extract_resource_limit_claims_from_docs(self) -> Dict[str, str]:
        """从文档提取资源限制声明"""
        claims = {}

        for file_path in self.skill_path.rglob("*.md"):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()

                # 查找资源限制声明
                if "memory limit" in content or "memory usage: limited" in content:
                    claims["memory_limit"] = "true"

                if "time limit" in content or "execution time: limited" in content:
                    claims["time_limit"] = "true"

            except:
                continue

        return claims

    def _check_resource_limit_implementation(self) -> Dict[str, bool]:
        """检查资源限制实施"""
        implementation = {
            "memory_limit": False,
            "time_limit": False,
        }

        for file_path in self.skill_path.rglob("*.py"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 检查内存限制
                if "memory" in content.lower() and ("limit" in content.lower() or "constraint" in content.lower()):
                    implementation["memory_limit"] = True

                # 检查时间限制
                if "time" in content.lower() and ("limit" in content.lower() or "timeout" in content.lower()):
                    implementation["time_limit"] = True

            except:
                continue

        return implementation

    def _extract_auto_validation_claims_from_docs(self) -> Dict[str, str]:
        """从文档提取自动验证声明"""
        claims = {}

        for file_path in self.skill_path.rglob("*.md"):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()

                # 查找自动验证声明
                if "automated validation" in content or "automatic validation" in content:
                    claims["auto_validation"] = "true"

                if "syntax validation" in content:
                    claims["syntax_validation"] = "true"

            except:
                continue

        return claims

    def _check_auto_validation_implementation(self) -> Dict[str, bool]:
        """Check auto validation implementation"""
        implementation = {
            "auto_validation": False,
            "syntax_validation": False,
        }

        for file_path in self.skill_path.rglob("*.py"):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                if "validate" in content.lower() or "check" in content.lower():
                    implementation["auto_validation"] = True
                if "compile" in content.lower() or "syntax" in content.lower():
                    implementation["syntax_validation"] = True
            except:
                continue
        return implementation