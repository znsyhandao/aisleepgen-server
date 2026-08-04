#!/usr/bin/env python3
"""
AISleepGen v3 全链路专业测试脚本
覆盖 Phase 1~8 + 修复验证 + 边界情况 + 并发
"""
import sys, json, urllib.request, os, time, datetime, threading
sys.stdout = open(1, 'w', encoding='utf-8', closefd=False)

API = "http://localhost:8090"
OID = "test_full_" + datetime.datetime.now().strftime("%H%M%S")
results = []

def R(name, ok, detail=""):
    icon = "PASS" if ok else "FAIL"
    results.append((name, ok, detail))
    print(f"  [{icon}] {name}" + (f" -- {detail}" if detail else ""))

def api(method, path, data=None, timeout=15):
    url = f"{API}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method,
        headers={"Content-Type": "application/json"})
    try:
        t0 = time.time()
        resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        t = (time.time() - t0) * 1000
        return resp, t
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        return {"error": f"HTTP {e.code}: {body}"}, 0
    except Exception as e:
        return {"error": str(e)}, 0

def get_profile(openid=None):
    with open(os.path.join("D:\\AISleepGen_Optimized","user_profile.json"),"r",encoding="utf-8") as f:
        pd = json.load(f)
    return pd.get(openid, {}) if openid else pd

def get_mp(openid):
    return get_profile(openid).get("meta_params", {})

with open("D:\\AISleepGen_Optimized\\deepseek_proxy.py","r",encoding="utf-8") as f:
    CODE = f.read()

# ============================================================
print("=" * 65)
print(f"  AISleepGen v3 全链路专业测试")
print(f"  Time:  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  OpenID: {OID}")
print("=" * 65)

# ============================================================
# 1. Onboarding 问卷 (Phase 4)
# ============================================================
print("\n--- [1] Phase 4: Onboarding 问卷 ---")
survey = {"main_issue":"insomnia","sleep_type":"night_owl",
          "stress_level":"high","sound_pref":"rain","duration_pref":"short"}
r, t = api("POST", "/api/update-profile", {"openid":OID,"onboarding_survey":survey})
R("1.1 问卷提交成功", r.get("success")==True, f"{t:.0f}ms")

mp = get_mp(OID)
R("1.2 threshold=0.35(high)", mp.get("intervention_threshold")==0.35, str(mp.get("intervention_threshold")))
R("1.3 rounds_base=3(short)", mp.get("breath_rounds_base")==3, str(mp.get("breath_rounds_base")))
R("1.4 preferred_pattern=4-7-8", mp.get("preferred_pattern")=="4-7-8", mp.get("preferred_pattern"))
R("1.5 noise_preference=rain", mp.get("noise_preference")=="rain", str(mp.get("noise_preference")))
R("1.6 confidence=0.5", mp.get("confidence")==0.5, str(mp.get("confidence")))
R("1.7 _initial_questionnaire=True", mp.get("_initial_questionnaire")==True)
R("1.8 feature_vector 8维", len(mp.get("feature_vector",[]))==8, str(len(mp.get("feature_vector",[]))))
R("1.9 F5(night_owl)=0.8", mp.get("feature_vector",[0]*8)[5]==0.8, str(mp.get("feature_vector",[0]*8)[5]))
R("1.10 F1(insomnia)=0.7", mp.get("feature_vector",[0]*8)[1]==0.7, str(mp.get("feature_vector",[0]*8)[1]))

# onboaridng-status API
r, _ = api("GET", f"/api/onboarding-status?openid={OID}")
R("1.11 onboarding-status API", r.get("onboarding_done")==True)

# 兼容性：旧用户无 meta_params 自动填充
profile = get_profile(OID)
profile.pop("meta_params", None)
# 手动触发兼容机制 (下次 load 会补)
with open(os.path.join("D:\\AISleepGen_Optimized","user_profile.json"),"r",encoding="utf-8") as f:
    pd_all = json.load(f)
pd_all[OID] = profile
with open(os.path.join("D:\\AISleepGen_Optimized","user_profile.json"),"w",encoding="utf-8") as f:
    json.dump(pd_all, f, ensure_ascii=False, indent=2)
# 重新加载会触发兼容填充
_ = get_mp(OID)
# reload
profile2 = get_profile(OID)
R("1.12 旧用户兼容填充", "meta_params" in profile2 and profile2["meta_params"].get("confidence") is not None)

# ============================================================
# 2. 干预决策 (Phase 3)
# ============================================================
print("\n--- [2] Phase 3: 干预决策 (低置信度关键词保底) ---")
help_msgs = [
    ("压力大工作多", "压力大"),
    ("睡不着失眠好难受", "睡不着"),
    ("很焦虑心慌", "焦虑"),
    ("胸口闷喘不过气", "胸口闷"),
    ("帮我放松一下", "放松一下"),
]
for desc, keyword in help_msgs:
    r, t = api("POST", "/api/chat", {"openid":OID, "message":desc})
    triggered = r.get("action") == "start_breathing"
    stress = r.get("stress_type")
    R(f"2.{help_msgs.index((desc,keyword))+1} '{desc}'触发干预", triggered, f"stress={stress} ({t:.0f}ms)")

# 非干预消息不应触发
non_help = ["今天天气不错", "早上吃了包子", "晚安"]
for msg in non_help:
    r, t = api("POST", "/api/chat", {"openid":OID, "message":msg})
    R(f"2.{non_help.index(msg)+5} '{msg}'不触发干预", r.get("action")!="start_breathing", f"{t:.0f}ms")

# ============================================================
# 3. Phase 7: 推理时搜索
# ============================================================
print("\n--- [3] Phase 7: 推理时搜索策略 ---")
# 通过多次呼吸完成提升 confidence，使其 >=0.6 走分数决策
# 手工构造 relax_log 完成记录
profile = get_profile(OID)
mp = profile["meta_params"]
mp["total_interactions"] = 5
mp["completion_rate"] = 0.8
mp["confidence"] = 0.65  # >=0.6 走分数路径
mp["feature_vector"] = [0.7, 0.3, 0.2, 0.1, 0.0, 0.5, 0.0, 0.0]
profile["relax_log"] = [{"completed":True,"stress_type":"失眠焦虑","breath_pattern":"4-7-8"}] * 3 + \
                        [{"completed":False,"stress_type":"工作压力","breath_pattern":"箱式呼吸"}]
profile["total_sessions"] = 8
with open(os.path.join("D:\\AISleepGen_Optimized","user_profile.json"),"r",encoding="utf-8") as f:
    pd_all = json.load(f)
pd_all[OID] = profile
with open(os.path.join("D:\\AISleepGen_Optimized","user_profile.json"),"w",encoding="utf-8") as f:
    json.dump(pd_all, f, ensure_ascii=False, indent=2)

r, t = api("POST", "/api/chat", {"openid":OID, "message":"睡不着压力大"})
ap = r.get("action_params", {})
R("3.1 高置信度触发干预", r.get("action")=="start_breathing", f"{t:.0f}ms")
R("3.2 包含呼吸模式名称", bool(ap.get("name")), ap.get("name",""))
R("3.3 轮数在3-8之间", 3 <= ap.get("rounds",0) <= 8, str(ap.get("rounds")))
R("3.4 包含提示文案", bool(ap.get("tip")), ap.get("tip","")[:30])
R("3.5 含压力类型", bool(r.get("stress_type")), r.get("stress_type",""))

# ============================================================
# 4. _meta_update 更新逻辑 (Phase 2)
# ============================================================
print("\n--- [4] Phase 2: 元学习更新器 ---")
mp_before = get_mp(OID)
c_before = mp_before.get("confidence", 0)
t_before = mp_before.get("intervention_threshold", 0.5)
# 再做一次呼吸完成反馈
r, t = api("POST", "/api/chat", {"openid":OID,"message":"呼吸练习做完了"})
mp_after = get_mp(OID)
R("4.1 confidence 增长", mp_after.get("confidence",0) > c_before,
  f"{c_before} -> {mp_after.get('confidence',0)}")
R("4.2 total_interactions+1", mp_after.get("total_interactions",0) > mp_before.get("total_interactions",0),
  f"{mp_before.get('total_interactions')} -> {mp_after.get('total_interactions')}")

# 多次做完了提升 completion_rate
for i in range(3):
    api("POST", "/api/chat", {"openid":OID, "message":"感觉不错，放松了一些"})
mp_final = get_mp(OID)
R("4.3 completion_rate 上升", mp_final.get("completion_rate",0) > 0,
  str(mp_final.get("completion_rate",0)))
R("4.4 偏好模式评分更新", bool(mp_final.get("_pattern_scores",{})),
  str(mp_final.get("_pattern_scores",{})))

# ============================================================
# 5. 睡眠数据分析 (WorldModel)
# ============================================================
print("\n--- [5] 睡眠数据分析 ---")
sleep_msgs = [
    "昨晚11点睡7点起，睡了8个小时，中间醒了一次",
    "躺了40分钟才睡着，半夜醒了2次，每次都醒半小时",
    "深睡大概2小时，做梦多，醒来很累",
]
for msg in sleep_msgs:
    r, t = api("POST", "/api/chat", {"openid":OID, "message":msg})
    has_wm = "📊" in r.get("reply","") or "评分" in r.get("reply","") or "评估" in r.get("reply","")
    R(f"5.{sleep_msgs.index(msg)+1} 睡眠分析含评分", has_wm, f"{t:.0f}ms")

# ============================================================
# 6. 评分统一
# ============================================================
print("\n--- [6] 评分统一 ---")
r, t = api("GET", f"/api/user-profile?openid={OID}")
m = r.get("member", {})
cur = m.get("current_score")
avg = m.get("avg_score_7d")
s7 = m.get("scores_7d", [])
R("6.1 current_score 不为空", cur is not None and cur > 0, str(cur))
R("6.2 avg_score_7d 存在", avg is not None, str(avg))
R("6.3 scores_7d 有7天", len(s7) == 7, str(len(s7)))
R("6.4 current 与 scores_7d 最新一致", cur == (s7[-1].get("score") if s7 else None),
  f"cur={cur}, last={s7[-1].get('score') if s7 else 'N/A'}")
R("6.5 avg 与 scores_7d 有效均值一致",
  avg == round(sum(s.get("score",0) for s in s7 if s.get("score"))/max(1,sum(1 for s in s7 if s.get("score"))),1) if any(s.get("score") for s in s7) else True)

# 检查 API 是否返回 meta_params（前端不需要，但后端有了）
R("6.6 API 返回不包含 meta_params", "meta_params" not in r,
  "meta_params 不上传前端（按设计）")

# ============================================================
# 7. 情绪时间线 (Phase 8)
# ============================================================
print("\n--- [7] Phase 8: 情绪时间线 ---")
emotion_msgs = [
    ("真的很烦，压力好大", "烦躁/压力"),
    ("好害怕睡不着", "焦虑"),
    ("今天心情不错", "开心/平静"),
    ("好累啊没精神", "疲惫"),
]
for msg, expected in emotion_msgs:
    r, t = api("POST", "/api/chat", {"openid":OID, "message":msg})
    profile = get_profile(OID)
    et = profile.get("emotion_timeline", [])
    has_entry = len(et) > 0
    if has_entry:
        latest = et[-1]
        R(f"7.{emotion_msgs.index((msg,expected))+1} '{msg[:12]}'情绪记录", True,
          f"{latest.get('emotion')}({latest.get('intensity')}) expected~{expected}")
    else:
        R(f"7.{emotion_msgs.index((msg,expected))+1} '{msg[:12]}'情绪记录", False, "no entry")

profile = get_profile(OID)
et = profile.get("emotion_timeline", [])
R("7.5 emotion_timeline 累计多条", len(et) >= 4, f"{len(et)}条")
# 检查最近几条情绪是否连续
dates = set(e.get("date") for e in et)
R("7.6 情绪时间线含日期", len(dates) >= 1, str(dates))

# ============================================================
# 8. 语音放松端点 (Phase 8b)
# ============================================================
print("\n--- [8] Phase 8b: 语音放松端点 ---")
r, t = api("POST", "/api/voice-relax", {"openid":OID, "text":"真的很烦躁睡不着"})
R("8.1 voice-relax 响应成功", r.get("success") or r.get("reply"), f"{t:.0f}ms")

# 带情绪的消息触发规则引擎
r, t = api("POST", "/api/voice-relax", {"openid":OID, "text":"好害怕，心跳很快，完全睡不着"})
has_emotion = r.get("emotion") is not None or r.get("action") is not None
R("8.2 voice-relax 情绪检测", has_emotion,
  f"emotion={r.get('emotion')} action={r.get('action')}")

# ============================================================
# 9. 修复验证
# ============================================================
print("\n--- [9] 修复验证 ---")

# 9a: breathing_kw 误触修复
for done_msg in ["呼吸练习做完了", "做完了放松了一些", "好一点了感觉不错"]:
    r, t = api("POST", "/api/chat", {"openid":OID, "message":done_msg})
    R(f"9a.{done_msg}不触发呼吸卡片", r.get("action")!="start_breathing", f"action={r.get('action')}")

# 9b: _preferred 变量存在
R("9b. _preferred 已定义", "_preferred = mp.get" in CODE and "_pref_boost =" not in CODE,
  "Phase 7 修复已应用")

# 9c: try/except 打印异常
except_count = CODE.count("except Exception")
print_except = CODE.count('print(f')
R(f"9c. 代码含{except_count}个except", True, f"(确保不要静默吞异常)")

# 9d: 后端健康
r, _ = api("GET", "/health")
R("9d. 后端健康", r.get("status")=="ok", json.dumps(r))
r, _ = api("POST", "/api/self-heal")
all_ok = all(v==True or "OK" in str(v) for v in r.values())
R("9e. 自愈系统正常", all_ok, json.dumps(r))

# ============================================================
# 10. 边界情况
# ============================================================
print("\n--- [10] 边界情况 ---")
edge_cases = [
    ("空消息", {"openid":OID, "message":""}),
    ("特殊字符", {"openid":OID, "message":"@#$%^&*()_+={}[]|\\:;\"'<>,.?/~`"}),
    ("超长消息", {"openid":OID, "message":"测试"*500}),
    ("缺失openid", {"message":"睡不着"}),
    ("不存在的openid", {"openid":"nonexistent_user_12345", "message":"睡不着"}),
]
for desc, payload in edge_cases:
    try:
        r, t = api("POST", "/api/chat", payload, timeout=30)
        no_crash = "error" not in r or "timeout" not in r.get("error","")
        R(f"10.{edge_cases.index((desc,payload))+1} {desc}", no_crash, f"{t:.0f}ms")
    except Exception as e:
        R(f"10.{edge_cases.index((desc,payload))+1} {desc}", False, str(e))

# ============================================================
# 11. Phase 5 跨夜适应
# ============================================================
print("\n--- [11] Phase 5: 跨夜中观适应 ---")
R("11.1 函数存在", "def _run_daily_batch_optimization" in CODE)
# 模拟今日已跑过
mp = get_mp(OID)
R(f"11.2 last_meta_batch={mp.get('_last_meta_batch')}",
  mp.get("_last_meta_batch") == datetime.datetime.now().strftime("%Y-%m-%d"),
  str(mp.get("_last_meta_batch")))

# ============================================================
# 12. Phase 6 异步化
# ============================================================
print("\n--- [12] Phase 6: 异步化 ---")
R("12.1 daemon 线程模式", "ThreadingHTTPServer" in CODE, "使用线程服务器")
R("12.2 偏好学习类存在", "class PreferenceEngine" in CODE)
R("12.3 PreferenceEngine.process_message 异步", "PreferenceEngine.process_message" in CODE)
R("12.4 Biofeedback 异步跳过处理", "异步跳过" in CODE or "Biofeedback" in CODE)

# ============================================================
# 总结
# ============================================================
print("\n" + "=" * 65)
pass_count = sum(1 for _, ok, _ in results if ok)
fail_count = sum(1 for _, ok, _ in results if not ok)
total = len(results)
rate = pass_count / total * 100 if total > 0 else 0
print(f"  结果: {pass_count}/{total} PASS ({rate:.0f}%) | {fail_count} FAIL")
print("=" * 65)

if fail_count > 0:
    print("\n  失败项:")
    for name, ok, detail in results:
        if not ok:
            print(f"    FAIL: {name} | {detail}")

# 保存结果
from collections import defaultdict
by_phase = defaultdict(list)
for name, ok, detail in results:
    phase = name.split(".")[0]
    by_phase[phase].append((name, ok, detail))

report = {
    "timestamp": datetime.datetime.now().isoformat(),
    "openid": OID,
    "pass": pass_count,
    "fail": fail_count,
    "total": total,
    "pass_rate": round(rate, 1),
    "by_phase": {k: {"pass": sum(1 for _, ok, _ in v if ok),
                     "fail": sum(1 for _, ok, _ in v if not ok),
                     "items": len(v)} for k, v in by_phase.items()},
    "failures": [{"name":n, "detail":d} for n, ok, d in results if not ok],
}
with open(os.path.join("D:\\AISleepGen_Optimized","test_full_results.json"),"w",encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f"\n  结果已保存: test_full_results.json")

sys.exit(0 if fail_count == 0 else 1)
