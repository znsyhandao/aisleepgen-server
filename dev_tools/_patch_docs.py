"""给所有缺少文档的dev_tools脚本补上文档头"""
import os, re

base = r'D:\AISleepGen_Optimized\dev_tools'

# 每个文件要补充的文档头
DOCS = {
    'check/find_duplicates.py': '"""\nfind_duplicates.py — 重复数据检测\n\n扫描 user_profile.json 或指定 JSON 文件，找出重复的 openid 条目。\n用法: python dev_tools/check/find_duplicates.py\n"""',
    'check/find_history.py': '"""\nfind_history.py — 用户历史记录检索\n\n从底层 deepseek_proxy.py 的 content 中提取用户历史上下文构建逻辑，\n用于调试和审查消息拼接是否正确。\n用法: python dev_tools/check/find_history.py\n"""',
    'check/find_messages.py': '"""\nfind_messages.py — 聊天消息检索\n\n从 deepseek_proxy.py 中定位 messages 列表的组装位置，\n确认 system_content + history_context + wm_context 的正确拼接。\n用法: python dev_tools/check/find_messages.py\n"""',
    'check/find_routes.py': '"""\nfind_routes.py — API 路由表扫描\n\n从 deepseek_proxy.py 中用正则提取所有 if-elif 路由路径定义，\n输出完整路由清单。\n用法: python dev_tools/check/find_routes.py\n"""',
    'check/find_stories.py': '"""\nfind_stories.py — 晚安故事检索\n\n遍历 miniprogram 目录的 JS 文件，搜索故事/助眠/晚安相关文本，\n用于确认故事 prompt 是否被正确配置。\n用法: python dev_tools/check/find_stories.py\n"""',
    'check/assess_damage.py': '"""\nassess_damage.py — 损害评估扫描\n\n当代码修改出 bug 后运行，检查 dp_router.py 的完整性：\n确定关键函数(handle_wx_login/handle_user_profile等)是否存在、\n文件是否有损坏字节。\n用法: python dev_tools/check/assess_damage.py\n"""',
    'check/test_compile.py': '"""\ntest_compile.py — 快速编译检查\n\n用 py_compile 检查指定 .py 文件的语法正确性。\n用法: python dev_tools/check/test_compile.py\n"""',
    'ops/clean_misplaced_files.py': '"""\nclean_misplaced_files.py — 清理项目根杂散文件\n\n扫描 dp_router.py 中因多次编辑产生的错位代码块，\n定位并移除被误插入的函数片段。\n用法: python dev_tools/ops/clean_misplaced_files.py\n"""',
    'ops/download_deepseek.py': '"""\ndownload_deepseek.py — 下载 DeepSeek-V3 模型\n\n从 hf-mirror.com 分片下载 safetensors 模型文件，\n支持断点续传 + MD5 校验。注意文件很大 (~600GB总)。\n用法: python dev_tools/ops/download_deepseek.py\n"""',
    'test/find_default.py': '"""\ntest_default.py — 默认用户流程测试\n\n用 openid=default 的用户模拟微信小程序 chat 请求，\n验证核心对话功能正常。\n用法: python dev_tools/test/test_default.py (需 deepseek_proxy 运行在 8090)\n"""',
    'test/test_dev_user.py': '"""\ntest_dev_user.py — 开发用户数据验证\n\n模拟带 X-OpenID header 的微信小程序请求，\n测试 update-profile + user-profile + chat 完整链路。\n用法: python dev_tools/test/test_dev_user.py\n"""',
    'test/verify_curl.py': '"""\nverify_curl.py — curl 验证(已废弃)\n\n原始脚本只剩残缺输出，不再维护。\n"""',
    'test/after_restart.py': '"""\nafter_restart.py — 重启后快速验证\n\n服务重启后立刻调 user-profile + chat 确认核心功能恢复。\n用法: python dev_tools/test/after_restart.py (需服务运行)\n"""',
    'test/file_check.py': '"""\nfile_check.py — 用户配置文件检查\n\n读 user_profile.json 指定用户的 latest/history 等字段，\n验证数据结构完整性。\n用法: python dev_tools/test/file_check.py\n"""',
    'test/quick_test.py': '"""\nquick_test.py — 快速测试\n\n向 localhost:8090 发 chat 请求测试 AI 对话正常。\n用法: python dev_tools/test/quick_test.py (需服务运行)\n"""',
    'test/verify_pay.py': '"""\nverify_pay.py — 支付 API 远程验证\n\n调远程服务器(82.156.208.245:8090)的 pricing + recommend-tier + create-order，\n确认外网支付链路正常。\n用法: python dev_tools/test/verify_pay.py\n"""',
    'test/verify_recommend.py': '"""\nverify_recommend.py — 推荐 API 远程验证\n\n调远程服务器测试 recommend-tier 对不同用户(test123/test_heavy)的推荐结果。\n用法: python dev_tools/test/verify_recommend.py\n"""',
}

import os
patched = 0
for rel_path, doc_header in DOCS.items():
    fpath = os.path.join(base, rel_path)
    if not os.path.exists(fpath):
        print(f'  ! 文件不存在: {rel_path}')
        continue
    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    # Only patch if it starts with code (no docstring)
    if not (content.strip().startswith('"""') or content.strip().startswith("'''")):
        # Replace first line or prepend
        if content.startswith('#!'):
            # shebang line - insert after it
            first_nl = content.index('\n')
            content = content[:first_nl+1] + doc_header + '\n' + content[first_nl+1:]
        else:
            content = doc_header + '\n' + content
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'  + {rel_path} 补文档')
        patched += 1
    else:
        print(f'  = {rel_path} 已有文档')

print(f'\n补全: {patched} 个')
