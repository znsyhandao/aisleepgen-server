#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_learn.py — AISleepGen 自学习引擎
"""
import os, json, time, threading
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_save_calibration_lock = threading.Lock()
_self_learn_counter = 0

def _load_calibration():
    path=os.path.join(PROJECT_ROOT,'data','calibration.json')
    try:
        if os.path.exists(path):
            with open(path,'r',encoding='utf-8') as f: return json.load(f)
    except Exception as _e:
        print('[SelfLearn] load_calibration: %s' % _e)
    return {'version':'1.0','learned_on':'','pain_penalty_base':0.08,'latency_threshold':120,'user_group_weights':{}}

def _save_calibration(cal):
    path=os.path.join(PROJECT_ROOT,'data','calibration.json')
    with _save_calibration_lock:
        with open(path,'w',encoding='utf-8') as f: json.dump(cal,f,ensure_ascii=False,indent=2)

def _trigger_self_learn(force=False):
    global _self_learn_counter
    now=time.time()
    last=getattr(_trigger_self_learn,'_last_learn',None)
    _self_learn_counter+=1
    if not(force or last is None or _self_learn_counter>=10 or(last and now-last>3600)): return
    _self_learn_counter=0
    _trigger_self_learn._last_learn=now
    try:
        fb_path=os.path.join(PROJECT_ROOT,'data','feedback.json')
        if not os.path.exists(fb_path): return
        with open(fb_path,'r',encoding='utf-8') as f: fbs=json.load(f)
        sc=[fb for fb in fbs if fb.get('rating',0)>0]
        if len(sc)<3: return
        cal=_load_calibration()
        low=[fb for fb in sc if fb['rating']<=2]
        ur=len(sc)>=100
        cal['_learn_mode']='regression' if ur else 'heuristic'
        if ur:
            try:
                from sklearn.linear_model import LinearRegression
                X,Y=[],[]
                for fb in sc:
                    wm=fb.get('wm_score_at_time',50)or 50; la=fb.get('sleep_latency',30)or 30
                    aw=fb.get('awake_times',1)or 1; du=fb.get('total_duration',420)or 420
                    st=fb.get('stress_level',5)or 5
                    pf=1.0 if any(kw in(fb.get('message','')or'').lower() for kw in['疼','痛','酸','不舒服','不适','难受'])else 0.0
                    X.append([wm,la,aw,du,st,pf]); Y.append(fb['rating'])
                if len(set(tuple(r) for r in X))>=10:
                    reg=LinearRegression().fit(X,Y); pc=reg.coef_[5] if len(reg.coef_)>5 else 0.0
                    cal['_regression_coefs']={k:round(c,4) for k,c in zip(['wm_score','latency','awake','duration','stress','pain_flag'],reg.coef_)}
                    cal['_regression_intercept']=round(reg.intercept_,3)
                    cal['_regression_score']=round(reg.score(X,Y),3)
                    cal['pain_penalty_base']=min(0.15,max(0.05,abs(pc)*0.3)) if pc<-0.3 else(0.10 if pc<-0.1 else 0.08)
            except Exception as _e:
                print('[SelfLearn] regression failed: %s' % _e)
        if not ur and len(low)>=3:
            cal['pain_penalty_base']=min(cal.get('pain_penalty_base',0.08)+0.02,0.15)
        hi=sum(1 for fb in sc if fb['rating']>=4)
        cal['happy_ratio']=round(hi/len(sc),3)
        cal['avg_user_rating']=round(sum(fb['rating'] for fb in sc)/len(sc),2)
        cal['avg_wm_at_feedback']=round(sum((fb.get('wm_score_at_time',0)or 0) for fb in sc)/len(sc),1)
        cal['learned_on']=datetime.now().strftime('%Y-%m-%d %H:%M')
        cal['samples']=len(sc)
        _save_calibration(cal)
        try:
            from architecture_inner_eye import measure_system_pulse,report_to_calibration
            report_to_calibration(measure_system_pulse())
        except Exception as _e:
            print('[SelfLearn] sys pulse report: %s' % _e)
    except Exception as e: print(f'[SelfLearn] {e}')

def _get_feedback_insights(openid):
    """分析用户的反馈历史，输出可注入到 prompt 的学习洞察"""
    from profile_storage import _load_user_profile
    profile = _load_user_profile(openid)
    feedbacks = profile.get('_feedbacks', []) or []

    if not feedbacks:
        return '', {'total_feedbacks':0,'dislike_ratio':0.0,'dislike_count':0,'like_count':0,'patterns':[],'has_insight':False}

    total = len(feedbacks)
    dislikes = [f for f in feedbacks if f.get('type') == 'dislike']
    likes = [f for f in feedbacks if f.get('type') == 'like']
    dislike_ratio = len(dislikes) / max(total, 1)

    # 提取 dislike 的文本模式
    dislike_texts = [f.get('text', '') for f in dislikes if f.get('text')]
    # 简单关键词分类
    pattern_hints = []
    for t in dislike_texts:
        if any(w in t for w in ['太严', '分低', '苛刻', '准确', '不对']):
            pattern_hints.append('scoring_too_strict')
        if any(w in t for w in ['啰嗦', '太长', '简单', '直接']):
            pattern_hints.append('too_verbose')
        if any(w in t for w in ['不懂', '没理解', '敷衍', '机械']):
            pattern_hints.append('lacks_empathy')
        if any(w in t for w in ['不具体', '空泛', '没用', '大道理']):
            pattern_hints.append('too_vague')

    # 生成自然语言洞察
    insights = []
    if total >= 3 and dislike_ratio > 0.5:
        insights.append(f'用户已反馈{len(dislikes)}次不满意，倾向性明显，需调整对话风格')

    if 'scoring_too_strict' in pattern_hints:
        insights.append('用户多次反馈评分偏低，回复时应更关注用户实际感受而非机械打分')
    if 'too_verbose' in pattern_hints:
        insights.append('用户偏好简洁回复，每次建议不超过2条，避免长篇大论')
    if 'lacks_empathy' in pattern_hints:
        insights.append('用户对共情程度敏感，回复时应先充分共情再分析数据')
    if 'too_vague' in pattern_hints:
        insights.append('用户要求具体可执行的建议，避免空泛的"保持良好习惯"类表述')

    insight_text = '\n'.join(insights) if insights else ''
    insight_data = {
        'total_feedbacks': total,
        'dislike_ratio': round(dislike_ratio, 2),
        'dislike_count': len(dislikes),
        'like_count': len(likes),
        'patterns': list(set(pattern_hints)),
        'has_insight': bool(insights),
    }
    return insight_text, insight_data


def _learnt_style_adjustments(openid):
    """基于用户历史反馈给出风格调整建议
    返回一段可注入 prompt 的指令文本。
    """
    insight_text, insight_data = _get_feedback_insights(openid)
    if not insight_text:
        return ''
    # 包装成 prompt 注入格式
    return f'\n【自学习反馈洞察】\n{insight_text}\n请基于以上用户反馈调整本次回复风格。'


def _meta_update(openid,sd):
    from profile_storage import _load_user_profile,_save_user_profile,_get_default_profile,_extract_features
    p=_load_user_profile(openid)
    mp=p.setdefault('meta_params',{})
    dfl=_get_default_profile()['meta_params']
    for k,v in dfl.items():
        if k not in mp: mp[k]=v
    c=sd.get('completed',False); pat=sd.get('breath_pattern','4-7-8')
    or_=mp.get('completion_rate',0.0); oc=mp.get('total_interactions',0)
    mp['completion_rate']=round((oc*or_+(1 if c else 0))/(oc+1),3)
    mp['total_interactions']=oc+1
    t_=0.45 if c else 0.55; ot=mp.get('intervention_threshold',0.5)
    mp['intervention_threshold']=round(max(0.3,min(0.8,ot+(t_-ot)*0.2)),3)
    ps=mp.get('_pattern_scores',{}); ps[pat]=ps.get(pat,0)+(1.0 if c else -0.3)
    mp['preferred_pattern']=sorted(ps,key=lambda k:ps[k],reverse=True)[0]
    fv=mp.get('feature_vector',[0.0]*8)
    msg=sd.get('_raw_message','')
    if msg:
        nfv=_extract_features(p,msg,sd.get('stress_type',''))
        for i in range(8): fv[i]=round(0.3*nfv[i]+0.7*fv[i],3)
    mp['feature_vector']=fv
    mp['response_rate']=round(mp['total_interactions']/max(1,p.get('total_sessions',0)),3)
    n=mp['total_interactions']
    mp['confidence']=round(min(0.95,0.3+n*0.08-(n-1)*0.02),3)
    mp['last_meta_update']=sd.get('timestamp',datetime.now().strftime('%Y-%m-%d %H:%M'))
    _save_user_profile(p,openid)
