#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
profile_storage.py — AISleepGen 用户画像存储层

v2 使用 SQLite 后端（WAL 模式），接口完全兼容 v1。
JSON 文件保留为只读 fallback + 导出格式。

所有函数重定向到 db_sqlite.SQLiteDB。
业务逻辑函数（_log_intervention, _update_user_profile 等）保持原样，
但它们内部调用的 _load_user_profile/_save_user_profile 已指向 SQLite。
"""
import os, json, time, threading, shutil
from datetime import datetime, timedelta
from copy import deepcopy

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
USER_PROFILE_PATH = os.path.join(PROJECT_ROOT, 'user_profile.json')
PROFILE_BACKUP_DIR = os.path.join(PROJECT_ROOT, 'data', 'backups')
MAX_BACKUPS = 3
_profile_lock = threading.Lock()

# SQLite 后端替代 JSON 文件
from db_sqlite import get_db as _get_sqlite_db
_db = _get_sqlite_db()


# ===== SQLite 重定向 v2（业务层无感知） =====

def _get_default_profile():
    return _db.get_default_profile()

def _load_user_profile(openid='default'):
    return _db.load_user_profile(openid)

def _save_user_profile(profile, openid='default'):
    _db.save_user_profile(profile, openid)

def _atomic_write_profile(openid, modify_fn):
    return _db.atomic_write_profile(openid, modify_fn)

def _load_all_profiles():
    return _db.load_all_profiles()

def _save_all_profiles(allp):
    for oid, prof in allp.items():
        _db.save_user_profile(prof, oid)

def _store_feedback(openid, message_id, feedback_type, feedback_text=None):
    return _db.store_feedback(openid, message_id, feedback_type, feedback_text)

def _backup_profile():
    pass  # SQLite WAL 自带故障恢复

def _recover_from_backup():
    return None


# ===== 以下为业务逻辑函数（保持原样，内部调用已指向 SQLite） =====

def _log_intervention(openid,stress_type,pat,rounds=0,duration=0,completed=True,user_message=''):
    try:
        p=_load_user_profile(openid)
        if 'relax_log' not in p: p['relax_log']=[]
        if 'behavior_stats' not in p: p['behavior_stats']={'total_relax_sessions':0,'common_emotions':[]}
        bs=p['behavior_stats']
        for k in ['total_completed_sessions','total_interrupted_sessions','total_relax_seconds',
                   'avg_relax_duration','relax_streak_days','stress_type_distribution',
                   'last_relax_date','weekly_counts']:
            if k not in bs: bs[k]=0 if k not in ['stress_type_distribution','weekly_counts','last_relax_date'] else ({} if k=='stress_type_distribution' else ([] if k=='weekly_counts' else None))
        now=datetime.now(); today=now.strftime('%Y-%m-%d')
        p['relax_log'].append({'timestamp':now.strftime('%Y-%m-%d %H:%M'),'date':today,'type':'breathing',
            'stress_type':stress_type,'breath_pattern':pat,'rounds_completed':rounds,
            'duration_seconds':duration,'completed':completed})
        if len(p['relax_log'])>200: p['relax_log']=p['relax_log'][-200:]
        bs['total_relax_sessions']=bs.get('total_relax_sessions',0)+1
        if completed: bs['total_completed_sessions']=bs.get('total_completed_sessions',0)+1
        else: bs['total_interrupted_sessions']=bs.get('total_interrupted_sessions',0)+1
        bs['total_relax_seconds']=bs.get('total_relax_seconds',0)+duration
        total_sessions=bs['total_relax_sessions']
        bs['avg_relax_duration']=round(bs['total_relax_seconds']/total_sessions,1) if total_sessions>0 else 0
        sdist=bs.get('stress_type_distribution',{})
        if isinstance(sdist,dict): sdist[stress_type]=sdist.get(stress_type,0)+1
        bs['last_relax_date']=today
        yd=(now-timedelta(days=1)).strftime('%Y-%m-%d')
        lr=bs.get('last_relax_date') or ''
        bs['relax_streak_days']=(bs.get('relax_streak_days',0)+1) if(lr==yd or lr==today)else 1
        ws=(now-timedelta(days=now.weekday())).strftime('%Y-%m-%d')
        wc=bs.get('weekly_counts',[])
        fnd=False
        for w in wc:
            if w.get('week_start')==ws: w['count']=w.get('count',0)+1; fnd=True; break
        if not fnd: wc.append({'week_start':ws,'count':1})
        if len(wc)>12: bs['weekly_counts']=wc[-12:]
        _save_user_profile(p,openid)
    except Exception as e: print(f'[Profile] log_intervention: {e}')

def _handle_intervention_complete(data):
    oid=data.get('openid','')
    if not oid: return {'success':False,'error':'missing openid'}
    _log_intervention(oid,'relaxation',data.get('pattern','unknown'),
        rounds=data.get('rounds',0),duration=data.get('duration',0),
        completed=data.get('completed',True))
    try:
        _atomic_write_profile(oid,lambda p:{**p,'last_intervention':{
            'timestamp':datetime.now().strftime('%Y-%m-%d %H:%M'),'pattern':data.get('pattern'),
            'rounds':data.get('rounds'),'duration':data.get('duration'),
            'completed':data.get('completed')},'_pending_review':True})
    except: pass
    return {'success':True,'recorded':True}

def _update_user_profile(ed,wmr,msg,openid='default'):
    p=_load_user_profile(openid)
    today=datetime.now().strftime('%Y-%m-%d')
    ic=any(w in msg for w in ['记错','不是','不对','错了','纠正','更正','修正','其实','搞错','你弄错','说错了'])
    es={}
    if wmr:
        dims=wmr.get('analysis',{}).get('dimensions',{}) if isinstance(wmr.get('analysis'),dict) else {}
        for dn,di in dims.items():
            if isinstance(di,dict) and di.get('score')is not None:
                s={'score':di['score'],'findings':di.get('findings',[]),'risk_flags':di.get('risk_flags',[]),
                   'recommended_therapies':di.get('recommended_therapies',[]),'specialty':di.get('specialty',dn)}
                for ek in ['sleep_efficiency','arousal_type','osa_risk','chronotype',
                           'phq9_sim','gad7_sim','glymphatic_efficiency','risk_score',
                           'physiological_arousal','cognitive_arousal']:
                    if ek in di: s[ek]=di[ek]
                es[dn]=s
    se={'date':today,'timestamp':datetime.now().strftime('%Y-%m-%d %H:%M'),'extracted':ed or {},
        'wm_score':wmr.get('total_score',0) if wmr else 0,
        'wm_quality':wmr.get('quality','') if wmr else '',
        'user_said':msg[:100],'type':'correction' if ic else 'normal','experts':es}
    p['history'].append(se)
    if len(p['history'])>30: p['history']=p['history'][-30:]
    p['latest']={'date':today,'score':wmr.get('total_score',0) if wmr else 0,
        'quality':wmr.get('quality','') if wmr else '',
        'pain':ed.get('pain',False) if ed else False,'pain_area':ed.get('pain_area','') if ed else '',
        'environment_cold':ed.get('environment_cold',False) if ed else False,
        'environment_hot':ed.get('environment_hot',False) if ed else False,
        'snore_related':ed.get('snore_related',False) if ed else False,
        'awake_times':ed.get('awake_times',0) if ed else 0,
        'stress':ed.get('stress_level',0) if ed else 0,'feeling':ed.get('feeling','') if ed else '',
        'confirmed':not ic}
    p['total_sessions']+=1
    mb=p.setdefault('member',_get_default_profile()['member'])
    mb['last_active']=datetime.now().strftime('%Y-%m-%d %H:%M')
    if 'active_dates' not in mb: mb['active_dates']=[]
    if today not in mb['active_dates']:
        mb['active_dates'].append(today); mb['total_days']=len(mb['active_dates'])
    if mb['active_dates']:
        sd=sorted(mb['active_dates'],reverse=True); streak=0; cd=datetime.now().date()
        for d in sd:
            try:
                do=datetime.strptime(d,'%Y-%m-%d').date()
                if do==cd: streak+=1; cd-=timedelta(days=1)
                elif do<cd: break
            except: continue
        mb['streak_days']=streak
    if 'daily_scores' not in mb: mb['daily_scores']=[]
    ws=wmr.get('total_score',0) if wmr else 0
    if ws>0:
        ex=[x for x in mb['daily_scores'] if x.get('date')==today]
        if ex: ex[0]['score']=ws
        else: mb['daily_scores'].append({'date':today,'score':ws})
        mb['daily_scores']=mb['daily_scores'][-90:]
    _save_user_profile(p,openid)

def _safe_update_profile(ed,wmr,msg,openid):
    try: _update_user_profile(ed,wmr,msg,openid)
    except: pass

def _extract_features(profile,msg,stress_type=''):
    f=[0.0]*8
    sw=['压力','累','烦','难受','痛苦','焦虑','紧张','不安','担心','崩溃']
    f[0]=min(1.0,sum(1 for w in sw if w in msg)/5.0)
    iw=['睡不着','失眠','醒了','醒来','熬夜','难入睡','睡不好','做梦','噩梦']
    f[1]=min(1.0,sum(1 for w in iw if w in msg)/4.0)
    aw=['心慌','心跳','喘不过气','胸闷','手抖','出汗','害怕','恐惧']
    f[2]=min(1.0,sum(1 for w in aw if w in msg)/4.0)
    et=profile.get('emotion_timeline',[])
    if et:
        lf=str(et[-1].get('feeling','')).lower()
        f[3]=0.2 if lf in('bad','terrible','anxious') else(0.8 if lf in('good','great','happy') else 0.5)
    else: f[3]=0.5
    f[4]=min(1.0,len(profile.get('history',[]))/20.0)
    h=datetime.now().hour
    f[5]=1.0 if h>=23 or h<3 else(0.8 if h<6 else(0.3 if h<12 else(0.5 if h<18 else 0.7)))
    bs=profile.get('behavior_stats',{})
    f[6]=round(bs.get('total_completed_sessions',0)/max(1,bs.get('total_relax_sessions',0)),2)
    sd=bs.get('stress_type_distribution',{})
    f[7]=round(sd.get(stress_type,0)/max(1,sum(sd.values())),2) if stress_type and sd else 0.5
    return f

def _run_daily_batch_optimization(profile,openid):
    mp=profile.setdefault('meta_params',{})
    today=datetime.now().strftime('%Y-%m-%d')
    if mp.get('_last_meta_batch','')==today: return False
    logs=profile.get('relax_log',[])
    if logs:
        yd=(datetime.now()-timedelta(days=1)).strftime('%Y-%m-%d')
        tgt=[l for l in logs if l.get('timestamp','').startswith(yd)]
        if not tgt: tgt=[l for l in logs if l.get('timestamp','').startswith(today)]
        if not tgt: tgt=logs[-5:]
        tl=len(tgt); cl=sum(1 for l in tgt if l.get('completed'))
        rt=cl/tl if tl>0 else 0; ar=sum(l.get('rounds',3) for l in tgt)/tl if tl>0 else 3
        ot=mp.get('intervention_threshold',0.5)
        if rt>=0.7: mp['intervention_threshold']=round(max(0.25,ot-0.05),2)
        elif rt<=0.3: mp['intervention_threshold']=round(min(0.75,ot+0.08),2)
        else: mp['intervention_threshold']=round((ot+0.5)/2,2)
        if ar>=4: mp['breath_rounds_scale']=min(3.5,mp.get('breath_rounds_scale',2.0)+0.3)
        elif ar<=2: mp['breath_rounds_scale']=max(0.5,mp.get('breath_rounds_scale',2.0)-0.3)
        if rt>=0.7 and mp.get('breath_rounds_base',3)<6: mp['breath_rounds_base']=min(6,mp['breath_rounds_base']+1)
        elif rt<=0.3 and mp.get('breath_rounds_base',3)>2: mp['breath_rounds_base']=max(2,mp['breath_rounds_base']-1)
    mp['_last_meta_batch']=today
    _save_user_profile(profile,openid)
    return True


# ===== 旧兼容：允许 import _store_feedback 之前没定义的问题 =====
# 上面已定义全部所需函数
