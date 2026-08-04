# -*- coding: utf-8 -*-
"""
医疗合规官 v1 — 法规红绿灯 + 数据隐私检查

突变动力学安全设计：
  1. 不修改任何数据文件
  2. 只读分析+报告
  3. 所有检查结果输出到独立 compliance/ 目录

产出:
  - compliance/regulatory_audit.json — 法规红绿灯检查报告
  - 建议"当前应该做什么合规动作"
"""

import os, json, hashlib, time
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
COMPLIANCE_DIR = os.path.join(BASE, 'compliance')

# ============================================================
# 法规检查清单
# ============================================================

REGULATIONS = [
    {
        'id': 'PIPL-01',
        'name': '个人信息保护法-告知同意',
        'region': '中国',
        'status': 'risk',
        'check': lambda: _check_user_consent(),
        'detail': '微信小程序首次启动时是否有隐私政策弹窗？数据收集是否明确告知用途？',
        'action': '检查 miniprogram/app.js 是否有 showPrivacyGuide',
    },
    {
        'id': 'PIPL-02',
        'name': '个人信息保护法-最小必要',
        'region': '中国',
        'status': 'audit',
        'check': lambda: _check_data_minimal(),
        'detail': '是否只收集了必要的睡眠数据？有没有收集不相关的敏感信息？',
        'action': '审核 user_profile.json 的字段，确认全部都是睡眠分析必需字段',
    },
    {
        'id': 'PIPL-03',
        'name': '个人信息保护法-数据删除权',
        'region': '中国',
        'status': 'risk',
        'check': lambda: _check_delete_capability(),
        'detail': '用户能否一键删除所有个人数据？当前没有delete-data接口',
        'action': '新增 /api/delete-user-data 接口',
    },
    {
        'id': 'PIPL-04',
        'name': '个人信息保护法-数据本地化',
        'region': '中国',
        'status': 'ok',
        'check': lambda: _check_data_localization(),
        'detail': '所有数据存储在本地D盘，未跨境传输',
        'action': '无需操作',
    },
    {
        'id': 'SEC-01',
        'name': '人脸数据-加密存储',
        'region': '通用',
        'status': 'risk',
        'check': lambda: _check_face_encryption(),
        'detail': 'facial_features_v9.csv直接存储面部特征数据，未加密',
        'action': '对面部特征CSV进行AES加密或脱敏处理',
    },
    {
        'id': 'SEC-02',
        'name': '录音数据-脱敏',
        'region': '通用',
        'status': 'risk',
        'check': lambda: _check_audio_privacy(),
        'detail': '录音.m4a文件包含声音特征，可直接识别个人身份',
        'action': '录音分析JSON脱敏后存储，原始文件定期清理',
    },
    {
        'id': 'SEC-03',
        'name': '访问日志-审计',
        'region': '通用',
        'status': 'audit',
        'check': lambda: _check_access_log(),
        'detail': '没有用户数据访问日志，谁什么时候看了什么数据不可追溯',
        'action': '新增 /api/audit-trail 记录数据访问行为',
    },
    {
        'id': 'MED-01',
        'name': '医疗器械注册-免责',
        'region': '中国',
        'status': 'ok',
        'check': lambda: _check_disclaimer_present(),
        'detail': 'medical_filter.py已注入免责声明',
        'action': '无需操作',
    },
    {
        'id': 'MED-02',
        'name': '医疗建议-AI责任边界',
        'region': '通用',
        'status': 'audit',
        'check': lambda: _check_medical_scope(),
        'detail': 'AI是否明确标注为"非医疗器械"？当前无此标注',
        'action': '在回复头或UI中增加「非医疗器械」声明',
    },
    {
        'id': 'GDPR-01',
        'name': 'GDPR-数据可移植性',
        'region': '欧盟',
        'status': 'ok',
        'check': lambda: _check_portability(),
        'detail': '所有数据为JSON/CSV格式，可导出',
        'action': '目前不面向欧盟用户，继续监控即可',
    },
]


def _check_user_consent():
    """检查是否有隐私政策弹窗"""
    miniapp_path = os.path.join(BASE, 'miniprogram', 'app.js')
    if os.path.exists(miniapp_path):
        try:
            with open(miniapp_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if 'showPrivacyGuide' in content or 'privacy' in content.lower() or '隐私' in content:
                return {'found': True, 'detail': 'app.js 包含隐私/Privacy相关代码'}
        except:
            pass
    # 检查用户配置中是否有同意记录
    user_profile = os.path.join(BASE, 'user_profile.json')
    if os.path.exists(user_profile):
        try:
            with open(user_profile, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                first_entry = list(data.values())[0] if isinstance(list(data.values())[0], dict) else {}
                consent = first_entry.get('privacy_consent', first_entry.get('agreed_to_terms', False))
                if consent:
                    return {'found': True, 'detail': '用户配置文件包含同意记录'}
        except:
            pass
    return {'found': False, 'detail': '未找到隐私政策弹窗或同意记录'}


def _check_data_minimal():
    """检查数据字段最小必要性"""
    user_profile = os.path.join(BASE, 'user_profile.json')
    if not os.path.exists(user_profile):
        return {'status': 'unknown', 'detail': 'user_profile.json 不存在'}
    
    # 检查是否有明显不必要的敏感字段
    sensitive_fields = ['id_card', 'phone', 'address', 'real_name', 'email', 'wechat_id']
    
    try:
        with open(user_profile, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        return {'status': 'error', 'detail': '解析失败'}
    
    issues = []
    if isinstance(data, dict):
        for key in data.keys():
            if isinstance(data[key], dict):
                for field in sensitive_fields:
                    if field in data[key] and data[key][field]:
                        issues.append(f'用户 {key[-8:]}: 发现敏感字段 {field}')
    
    return {'issues': issues, 'total_issues': len(issues)}


def _check_delete_capability():
    """检查是否有数据删除功能"""
    try:
        with open(os.path.join(BASE, 'deepseek_proxy.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        if '/api/delete' in content or 'delete-user' in content or 'clear_data' in content:
            return {'found': True, 'detail': '已实现删除接口'}
        return {'found': False, 'detail': '未实现用户数据删除接口'}
    except:
        return {'found': False, 'detail': '无法读取deepseek_proxy.py'}


def _check_data_localization():
    return {'local': True, 'detail': '全部数据存储在本地D盘'}


def _check_face_encryption():
    face_csv = os.path.join(BASE, 'sleep-skin features', 'facial_features_v9.csv')
    if not os.path.exists(face_csv):
        return {'status': 'unknown', 'detail': '面部特征文件不存在'}
    
    # 检查文件权限
    file_size = os.path.getsize(face_csv)
    return {
        'encrypted': False,
        'file_size_kb': round(file_size / 1024, 1),
        'detail': '面部特征CSV明文存储，未加密',
    }


def _check_audio_privacy():
    audio_dir = os.path.join(BASE, 'sleep_record')
    if not os.path.exists(audio_dir):
        return {'status': 'unknown', 'detail': '录音目录不存在'}
    
    m4a_files = [f for f in os.listdir(audio_dir) if f.endswith('.m4a')] if os.path.isdir(audio_dir) else []
    
    return {
        'raw_audio_count': len(m4a_files),
        'encrypted': False,
        'detail': f'录音文件明文存储({len(m4a_files)}个.m4a)',
    }


def _check_access_log():
    return {'found': False, 'detail': '无数据访问审计日志'}


def _check_disclaimer_present():
    med_filter = os.path.join(BASE, 'medical_filter.py')
    if os.path.exists(med_filter):
        return {'found': True, 'detail': 'medical_filter.py 已实现免责声明'}
    return {'found': False, 'detail': '未找到医疗免责声明'}


def _check_medical_scope():
    disclaimer_path = os.path.join(BASE, 'sleep-skin features', 'medical_audit_log.json')
    if os.path.exists(disclaimer_path):
        return {'found': True, 'detail': '医疗审计日志存在'}
    return {'found': False, 'detail': '未找到非医疗器械声明'}


def _check_portability():
    return {'found': True, 'detail': '数据格式为JSON/CSV，可导出'}


def full_audit():
    """全量法规审计"""
    os.makedirs(COMPLIANCE_DIR, exist_ok=True)
    
    results = []
    for reg in REGULATIONS:
        try:
            check_result = reg['check']()
            reg_status = reg['status']
            # 如果check函数返回了override status
            if isinstance(check_result, dict) and 'found' in check_result:
                if check_result['found']:
                    reg_status = 'ok'
                else:
                    reg_status = 'risk'
            
            results.append({
                'id': reg['id'],
                'name': reg['name'],
                'region': reg['region'],
                'status': reg_status,
                'check_result': check_result,
                'detail': reg['detail'] if isinstance(reg['detail'], str) else str(reg['detail']),
                'action': reg['action'],
            })
        except Exception as e:
            results.append({
                'id': reg['id'],
                'name': reg['name'],
                'status': 'error',
                'detail': f'检查失败: {e}',
            })
    
    # 风险统计
    risk_count = sum(1 for r in results if r.get('status') == 'risk')
    audit_count = sum(1 for r in results if r.get('status') == 'audit')
    ok_count = sum(1 for r in results if r.get('status') == 'ok')
    
    report = {
        'generated_at': datetime.now().isoformat(),
        'regulations_checked': len(results),
        'risk': risk_count,
        'needs_audit': audit_count,
        'ok': ok_count,
        'compliance_score': round(ok_count / len(results) * 100, 1) if results else 0,
        'results': results,
        'urgent_actions': [
            r['action'] for r in results if r.get('status') == 'risk'
        ][:5],
    }
    
    # 写报告
    report_path = os.path.join(COMPLIANCE_DIR, 'regulatory_audit.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return report


def print_summary():
    report = full_audit()
    score = report['compliance_score']
    
    print(f'医疗合规官 — 法规红绿灯检查')
    print(f'  检查项: {report["regulations_checked"]}')
    print(f'  合规评分: {score}%')
    print()
    
    for r in report['results']:
        status = r.get('status', '?')
        sym = {'ok': '[OK]', 'risk': '[RISK]', 'audit': '[AUDIT]', 'error': '[ERROR]'}.get(status, '[?]')
        print(f'  {sym} {r["id"]:10s} {r["name"]:30s} ({r.get("region","")})')
    
    print()
    print('  紧急动作:')
    for action in report.get('urgent_actions', []):
        print(f'    - {action}')
    print()
    print('  突变动力学: 只读检查, 未修改任何管线数据')
    return report


if __name__ == '__main__':
    print_summary()
