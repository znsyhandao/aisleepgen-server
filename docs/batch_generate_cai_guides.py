# -*- coding: utf-8 -*-
"""
训练完成后，用蔡声音批量生成全部引导语
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cai_voice_engine import CaiVoiceEngine

# 所有需要生成的引导语
ALL_SCRIPTS = {
    '478_breathing': [
        ('intro', '现在，找一个舒服的姿势坐好或躺下。轻轻闭上眼睛，把注意力带回到呼吸上。'),
        ('inhale', '慢慢吸气，感受空气充满你的肺部。4、3、2、1。'),
        ('hold', '屏住呼吸，感受这一刻的宁静。7、6、5、4、3、2、1。'),
        ('exhale', '缓缓呼气，释放所有紧张。8、7、6、5、4、3、2、1。'),
        ('outro', '感受身体逐渐放松。每一次呼吸，都让自己更深地沉入宁静之中。'),
    ],
    'box_breathing': [
        ('intro', '想象一个正方形。吸气，划出第一条边。屏息，第二条边。呼气，第三条边。停，第四条边。'),
        ('inhale', '吸气，4、3、2、1。'),
        ('hold', '屏住呼吸，4、3、2、1。'),
        ('exhale', '呼气，4、3、2、1。'),
        ('hold2', '停，4、3、2、1。'),
        ('outro', '很好。让呼吸自然地流动。'),
    ],
    'body_scan': [
        ('intro', '躺好，双手自然放在身体两侧。我们从头顶开始，逐步扫描全身。'),
        ('head', '感受头顶，头皮，额头，眉毛，眼睛，脸颊，下巴。'),
        ('neck', '感受颈部，喉咙，肩膀。让肩膀自然地沉下去。'),
        ('torso', '感受胸腔，心脏的跳动，腹部，随着呼吸起伏。'),
        ('legs', '感受大腿，膝盖，小腿，脚踝，双脚，完全放松。'),
        ('outro', '你的身体已经完全放松了。'),
    ],
    'progressive_relaxation': [
        ('intro', '我们从脚开始，逐部位紧绷再放松。'),
        ('feet', '收紧脚趾，用力，5、4、3、2、1，放松。'),
        ('legs', '收紧大腿和臀部，用力，5、4、3、2、1，放松。'),
        ('torso', '收紧腹部和背部，用力，5、4、3、2、1，放松。'),
        ('hands', '握紧双拳，用力，5、4、3、2、1，松开手。'),
        ('shoulders', '耸起双肩靠近耳朵，用力，5、4、3、2、1，沉下去。'),
        ('face', '皱起整张脸，用力，5、4、3、2、1，放松面部。'),
        ('outro', '全身放松。从脚趾到头顶，没有一处紧张。'),
    ],
    'sleep_preparation': [
        ('intro', '夜晚来临。这一天已经结束了。现在到了放下的时候。'),
        ('release_day', '回想今天让你开心的一个瞬间，在心里默默感谢它，然后放手。'),
        ('release_worry', '回想今天让你烦心的一件事，让它顺着河流漂走。'),
        ('body_check', '感受床垫支撑着你的身体。感受被子覆盖着你的温暖。'),
        ('breath_focus', '把注意力放在呼吸上。不要改变它，只是观察它。进，出。'),
        ('outro', '让自己慢慢沉入睡眠。安心入睡。'),
    ],
    'loving_kindness': [
        ('intro', '找一个舒服的姿势坐好。双手轻轻放在膝盖上。'),
        ('self', '愿我快乐。愿我平安。愿我健康。愿我生活幸福。'),
        ('others', '把这份善意延伸出去。愿我的家人快乐平安。愿我的朋友健康幸福。'),
        ('all', '愿所有众生都快乐平安。愿世间没有痛苦。'),
        ('outro', '带着这份善意，慢慢把注意力带回呼吸。'),
    ],
    'mindful_breathing': [
        ('intro', '轻轻闭上眼睛。把注意力放在呼吸上。'),
        ('focus', '感受空气从鼻孔进入。感受腹部微微鼓起。'),
        ('wandering', '杂念来了没关系。轻轻把它放走。回到呼吸。'),
        ('outro', '慢慢地睁开眼睛。带着这份平静。'),
    ],
}

def main():
    engine = CaiVoiceEngine()
    
    print('检查模型...')
    if not engine.check_model():
        print('模型未找到！请先下载训练好的模型到 voice_clone_model/ 目录')
        return
    
    print('启动推理服务...')
    if not engine.start_inference_server():
        print('启动失败！')
        return
    
    print()
    print('开始批量合成蔡声音引导语...')
    results = engine.batch_synthesize(ALL_SCRIPTS)
    
    print()
    print(f'合成完成: {len(results)}段')
    success = [r for r in results if r['path']]
    failed = [r for r in results if not r['path']]
    print(f'  成功: {len(success)}')
    print(f'  失败: {len(failed)}')
    
    if failed:
        print(f'  失败段:')
        for f in failed:
            print(f'    {f["guide"]}_{f["segment"]}')
    
    engine.stop()
    print()
    print('刷新引导库清单:')
    import guide_audio_manager
    guide_audio_manager.status()


if __name__ == '__main__':
    main()
