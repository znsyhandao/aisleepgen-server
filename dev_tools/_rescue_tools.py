"""从archive中捞回有工具价值的脚本，迁移到dev_tools相应目录"""
import os, shutil

BASE = r'D:\AISleepGen_Optimized'
TOOLS = os.path.join(BASE, 'dev_tools')
ARCHIVE = os.path.join(TOOLS, 'archive')

# 要捞回的工具: (文件名, 目标子目录, 新名称, 功能说明)
RESCUE = [
    ('_assess_damage.py', 'check', 'assess_damage.py', '损害评估—跑一遍看到哪些用户/文件/数据受损'),
    ('_find_dup.py', 'check', 'find_duplicates.py', '重复数据检测'),
    ('_find_history.py', 'check', 'find_history.py', '从profile中检索用户历史记录'),
    ('_find_msgs.py', 'check', 'find_messages.py', '从聊天记录中检索特定消息'),
    ('_find_story.py', 'check', 'find_stories.py', '检索晚安故事记录'),
    ('_find_routes.py', 'check', 'find_routes.py', '扫描全部路由定义'),
    ('_remove_misplaced.py', 'ops', 'clean_misplaced_files.py', '清理误放到项目根的杂散文件'),
    ('_test_default.py', 'test', 'test_default.py', '默认用户完整流程测试'),
    ('_test_dev_user.py', 'test', 'test_dev_user.py', '开发用户数据验证'),
    ('_test_compile.py', 'check', 'test_compile.py', '编译检查（full_health_check已覆盖，保留作为独立工具）'),
]

rescued = 0
for fname, subdir, new_name, desc in RESCUE:
    src = os.path.join(ARCHIVE, fname)
    dst = os.path.join(TOOLS, subdir, new_name)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)
        print(f'  + {subdir}/{new_name}  — {desc}')
        rescued += 1
    elif os.path.exists(dst):
        print(f'  = {subdir}/{new_name}  (已存在)')
    else:
        print(f'  ! {fname} not found in archive')

print(f'\n捞回: {rescued} 个')

# 生成archive目录的索引文件，说明为什么剩下的留在archive
remaining = sorted(f for f in os.listdir(ARCHIVE) if f.endswith('.py'))
index = """# archive/ — 一次性/历史脚本

这些脚本是为特定任务一次性编写的，不值得沉淀到 dev_tools 中。
如需要，直接 `python %s` 运行。历史保留不删。

## 分类
"""
cats = {
    '一次性修复': [],
    '一次性数据处理': [],
    '一次性调试/验证': [],
    '一次性推送/部署': [],
    '一次性运维': [],
    '需人工判断': [],
    '已迁移到dev_tools': [],
}

import re
for f in remaining:
    content = open(os.path.join(ARCHIVE, f), 'r', encoding='utf-8', errors='ignore').read()
    desc_match = re.search(r'"""(.+?)"""', content, re.DOTALL)
    desc = desc_match.group(1).strip()[:120] if desc_match else '(无文档)'
    
    if re.match(r'^_debug_|_test_4_|_test_ask_|_test_boot_|_test_chain_|_test_correct_|_test_exact_|_test_full_default_|_test_gbk_|_test_get_detail_|_test_read_|_test_truncate_|_test_write_|_find_(?!r|history|msgs|story|dup)|_debug_', f):
        cats['一次性调试/验证'].append((f, desc))
    elif re.match(r'^_dl_|_download_|_mendeley_|_parse_mendeley|_validate_mendeley|_insert_protocols|_add_|_score_|_train_final|_inject_atmosphere|_remove_misplaced|_scan_all', f):
        cats['一次性数据处理'].append((f, desc))
    elif re.match(r'^_fix_|_check_compile|_check_default|_check_dev_user|_check_real_users|_check_users|_check_all', f):
        cats['一次性修复'].append((f, desc))
    elif re.match(r'^_gh_|_github_|_do_push|_push_debug|_push_profile|_push_tier', f):
        cats['一次性推送/部署'].append((f, desc))
    elif re.match(r'^_deploy_server|_final_verify|_run_with_crash', f):
        cats['一次性运维'].append((f, desc))
    else:
        cats['需人工判断'].append((f, desc))

for cat, files in cats.items():
    if files:
        index += f'\n### {cat} ({len(files)}个)\n\n'
        for f, desc in files:
            index += f'- `{f}` — {desc[:80]}\n'

with open(os.path.join(ARCHIVE, 'INDEX.md'), 'w', encoding='utf-8') as f:
    f.write(index)

print(f'索引已生成: archive/INDEX.md ({len(remaining)} 个文件)')
