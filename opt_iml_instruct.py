#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
opt_iml_instruct.py — OPT-IML统一指令集 (v7.5+)
原理: Meta OPT-IML — 统一各任务的指令模板，确保输出风格一致
落地: 为AISleepGen的10位专家提供统一指令集，对齐分析风格

用法:
  from opt_iml_instruct import get_expert_instruction, build_unified_prompt
  instruction = get_expert_instruction('ClinicalPsychologist')
  prompt = build_unified_prompt(sleep_data, instruction)
"""

# ===== 10位专家的统一指令模板 =====
EXPERT_INSTRUCTIONS = {
    'ClinicalPsychologist': {
        'role': '睡眠临床心理师',
        'core_task': '评估睡眠相关心理状态',
        'output_format': ['score:0-1', 'confidence:0-1', 'findings[]', 'risk_flags[]'],
        'scale': '0=poor, 1=excellent',
        'evidence_priority': ['PHQ-9', 'GAD-7', 'ISI', 'PSQI'],
        'style': '专业审慎，避免绝对化表述',
        'fallback': {'score': 0.5, 'confidence': 0.3},
    },
    'CBT': {
        'role': '失眠认知行为治疗师',
        'core_task': '评估CBT-I适用性和失眠严重度',
        'output_format': ['score:0-1', 'confidence:0-1', 'findings[]', 'risk_flags[]'],
        'scale': '0=severe, 1=normal',
        'evidence_priority': ['ICSD-3', 'AASM指南', 'CBT-I手册'],
        'style': '结构化，按失-眠诊断标准逐条核对',
        'fallback': {'score': 0.5, 'confidence': 0.3},
    },
    'SleepPhysician': {
        'role': '睡眠医生',
        'core_task': '筛查潜在睡眠障碍',
        'output_format': ['score:0-1', 'confidence:0-1', 'findings[]', 'risk_flags[]'],
        'scale': '0=sleep_disorder, 1=healthy',
        'evidence_priority': ['ICS-3', 'AASM指南'],
        'style': '对红-色信号要明确标注',
        'fallback': {'score': 0.5, 'confidence': 0.3},
    },
    'Chronobiologist': {
        'role': '时间生物学家',
        'core_task': '评估昼夜节律与作息规律',
        'output_format': ['score:0-1', 'confidence:0-1', 'findings[]', 'risk_flags[]'],
        'scale': '0=disrupted, 1=aligned',
        'evidence_priority': ['MEQ-SA', '昼夜节律障碍诊断标准'],
        'style': '关注时间模式，非单点数据',
        'fallback': {'score': 0.5, 'confidence': 0.3},
    },
    'LifeScientist': {
        'role': '综合科学家',
        'core_task': '评估睡眠效率与整体健康关联',
        'output_format': ['score:0-1', 'confidence:0-1', 'findings[]', 'risk_flags[]'],
        'scale': '0=inefficient, 1=efficient',
        'evidence_priority': ['SE计算', '心率变异性参考'],
        'style': '数据驱动，定量分析',
        'fallback': {'score': 0.5, 'confidence': 0.3},
    },
    'RiskManager': {
        'role': '风险管控师',
        'core_task': '评估综合睡眠风险等级',
        'output_format': ['score:0-1', 'confidence:0-1', 'findings[]', 'risk_flags[]'],
        'scale': '0=high_risk, 1=low_risk',
        'evidence_priority': ['风险矩阵', '累积暴露模型'],
        'style': '保守评估，宁高勿低',
        'fallback': {'score': 0.5, 'confidence': 0.3, 'risk_flags': ['数据不足以评估']},
    },
    'StressRelaxation': {
        'role': '减压评估师',
        'core_task': '评估压力水平和推荐放松策略',
        'output_format': ['score:0-1', 'confidence:0-1', 'findings[]', 'risk_flags[]'],
        'scale': '0=high_stress, 1=relaxed',
        'evidence_priority': ['PSS-10', '心率变异性'],
        'style': '共情但不越界，不可替代医学治疗',
        'fallback': {'score': 0.5, 'confidence': 0.3},
    },
    'ExerciseRehab': {
        'role': '运动分析师',
        'core_task': '评估运动习惯对睡眠的影响',
        'output_format': ['score:0-1', 'confidence:0-1', 'findings[]', 'risk_flags[]'],
        'scale': '0=sedentary, 1=active',
        'evidence_priority': ['运动指南', '运动-睡眠剂量效应'],
        'style': '鼓励但不过度推荐',
        'fallback': {'score': 0.5, 'confidence': 0.3, 'findings': ['无运动数据']},
    },
    'CardiacMonitor': {
        'role': '心血管监测师',
        'core_task': '心率变异性与心血管风险提示',
        'output_format': ['score:0-1', 'confidence:0-1', 'findings[]', 'risk_flags[]'],
        'scale': '0=cardiovascular_risk, 1=normal',
        'evidence_priority': ['HRV参考值', '夜间心率模式'],
        'style': '数据不足时明确标注低于推荐',
        'fallback': {'score': 0.5, 'confidence': 0.3, 'findings': ['心-血管数据缺失']},
    },
    'NutriMetabolism': {
        'role': '营养代谢师',
        'core_task': '评估饮食与代谢对睡眠的影响',
        'output_format': ['score:0-1', 'confidence:0-1', 'findings[]', 'risk_flags[]'],
        'scale': '0=metabolic_risk, 1=optimal',
        'evidence_priority': ['膳食指南', '褪黑素代谢路径'],
        'style': '推-荐可行饮食调整，不做极端建议',
        'fallback': {'score': 0.5, 'confidence': 0.3, 'findings': ['饮食-数据缺失']},
    },
}


def get_expert_instruction(expert_name, lang='cn'):
    """获取某位专家的统一指令"""
    inst = EXPERT_INSTRUCTIONS.get(expert_name)
    if not inst:
        return {'role': '未知专家', 'core_task': '暂无定义', 'fallback': {'score': 0.5, 'confidence': 0.1}}
    return inst


def build_unified_prompt(sleep_data, instruction):
    """根据指令模板和睡眠数据构建统一prompt

    Args:
        sleep_data: dict — 用户睡眠数据
        instruction: dict — 专家指令 (get_expert_instruction返回值)

    Returns:
        str — 统一格式的prompt
    """
    core = instruction.get('core_task', '评估')
    style = instruction.get('style', '专业')
    score_desc = instruction.get('scale', '0-1')
    parts = [
        '【统一指令】%s' % core,
        '【评分标准】%s' % score_desc,
        '【分析风格】%s' % style,
        '【输入数据】',
    ]
    # 添加关键数据指针
    for key in ['sleep_latency', 'awake_times', 'total_duration', 'stress_level']:
        if key in sleep_data:
            parts.append('  %s: %s' % (key, sleep_data[key]))
    return '\n'.join(parts)


def get_all_instructions():
    """获取所有专家的指令摘要"""
    return {name: {'role': v['role'], 'task': v['core_task'], 'style': v['style']}
            for name, v in EXPERT_INSTRUCTIONS.items()}


# ===== 自测 =====
if __name__ == '__main__':
    print('=== OPT-IML Instruct Test ===\n')

    inst = get_expert_instruction('ClinicalPsychologist')
    print('CP role:', inst['role'])
    assert inst['core_task'] == '评估睡眠相关心理状态'

    inst = get_expert_instruction('NonExistent')
    print('Unknown role:', inst['role'])
    assert inst['role'] == '未知专家'

    prompt = build_unified_prompt({'sleep_latency': 60, 'stress_level': 8}, inst)
    print('Prompt length:', len(prompt))

    all_inst = get_all_instructions()
    print('Total experts:', len(all_inst))
    assert len(all_inst) == 10

    print('\nAll tests passed!')
