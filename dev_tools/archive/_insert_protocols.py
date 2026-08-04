# -*- coding: utf-8 -*-
# Insert 5 new protocols right before PROTOCOLS closing

with open(r'D:\AISleepGen_Optimized\dp_router.py', 'r', encoding='utf-8') as f:
    c = f.read()

# Find: last element before PROTOCOLS closes
# sound_bath is the last entry. Its outermost brace is at depth 1 (before the final }, })
# Find the last closing brace of the PROTOCOLS inner dict

idx = c.find("'sound_bath': {")
# Count depth from sound_bath start
depth = 0
brace_positions = []
for i in range(idx, len(c)):
    if c[i] == '{':
        depth += 1
        brace_positions.append((i, depth, '{'))
    elif c[i] == '}':
        brace_positions.append((i, depth, '}'))
        depth -= 1
        if depth == 1 and len([x for x in brace_positions if x[2] == '}']) >= 3:
            # We're back to PROTOCOLS level (depth 1) after closing sound_bath
            pass
        if depth == 0:
            # PROTOCOLS closed
            # The insertion point is BEFORE this closing
            close_pos = i
            # Go backwards to find the last comma before PROTOCOLS close
            last_comma = c.rfind(',', idx, close_pos)
            insert_pos = last_comma + 1  # after the comma, before newline
            
            new_protocols = """
        # === 行为认知类（5种新增） ===
        'cognitive_unloading': {
            'name': "认知卸荷 - 担忧日记",
            'icon': 'journal',
            'desc': '把脑子里放不下的事逐件写下来，清空工作记忆，效果等同入睡潜伏期缩短9min',
            'steps': [
                '闭上眼睛，回想今天一直在想的事情',
                '在脑海里把那件事"放在"一个盒子里',
                '告诉自己："明天再处理，现在不是时候"',
                '把注意拉回到呼吸上',
                '感受肩膀有没有放松一点',
                '现在想第二件事...重复这个步骤',
            ],
            'repeat_every': 30,
        },
        'paradoxical_intention': {
            'name': '矛盾意向疗法 - 努力清醒',
            'icon': 'eye',
            'desc': '放弃"必须睡着"的执念，反向操作：努力保持清醒，反而消除焦虑入睡',
            'steps': [
                '舒服躺好，睁开眼睛',
                '告诉自己："我不睡了，我要努力保持清醒"',
                '不要闭眼，专注盯着天花板或黑暗中的一点',
                '对自己说："清醒就是胜利，睡着了算我输"',
                '允许眼皮变重，但坚持不要闭上',
                '如果闭上就再睁开，继续"努力清醒"',
            ],
            'repeat_every': 25,
        },
        'stimulus_control': {
            'name': '刺激控制 - 重新建立床=睡觉',
            'icon': 'bed',
            'desc': '打破"床=睡不着焦虑"的条件反射，重新建立床和睡眠的唯一关联，效果Cohen d=0.87',
            'steps': [
                '现在你躺在床上，但感觉不困',
                '好，起来，离开床',
                '去一个昏暗安静的地方坐下',
                '不要看手机，不要做刺激的事',
                '等真正感到困意时再回床上',
                '如果躺下15分钟还不困，重复这个过程',
            ],
            'repeat_every': 40,
        },
        'sleep_hygiene': {
            'name': '睡眠卫生检查清单',
            'icon': 'checklist',
            'desc': '逐项检查优化睡眠环境和习惯，循证睡眠卫生教育',
            'steps': [
                '检查室温：18-22度最佳（凉爽助眠）',
                '检查光线：拉上窗帘，关闭所有发光源',
                '检查声音：关门关窗，或打开白噪音',
                '放下手机：蓝光抑制褪黑素分泌',
                '放松身体：洗个温水澡或做简单拉伸',
                '调整睡姿：侧卧最佳，减少打鼾和反流',
            ],
            'repeat_every': 35,
        },
        'cognitive_restructuring': {
            'name': '认知重构 - 挑战不合理信念',
            'icon': 'brain',
            'desc': '识别并挑战关于睡眠的灾难化思维，改善焦虑性失眠，效果Cohen d=0.65',
            'steps': [
                '注意到你在想什么："今晚又睡不着了"',
                '问自己：这句话是事实还是担忧？',
                '挑战它：你过去也有睡好的时候，说明能睡着',
                '替换："即使今晚睡不好，我明天也能撑过去"',
                '接受：身体有自我调节能力，相信它',
                '放下：不需要控制睡眠，让睡眠来找你',
            ],
            'repeat_every': 30,
        },
"""
            c = c[:insert_pos] + new_protocols + c[insert_pos:]
            
            with open(r'D:\AISleepGen_Optimized\dp_router.py', 'w', encoding='utf-8') as f:
                f.write(c)
            
            import py_compile
            try:
                py_compile.compile(r'D:\AISleepGen_Optimized\dp_router.py', doraise=True)
                print('VALID - 5 protocols inserted at correct position!')
            except py_compile.PyCompileError as e:
                print(f'ERROR: {e}')
            break
