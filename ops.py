#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ops.py — AISleepGen 运维模块

职责：日志系统 + 进程保活 + 版本号 + 健康上报
不依赖其他业务模块，启动时自动初始化。
"""
import os, sys, json, logging, threading, time, signal
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ===== 版本号 =====
VERSION = '5.1.0'
VERSION_TAG = 'online-rl+active-sampling'  # Online RL module: active sampling to reduce uncertainty. Q-learning with Double Q, context-aware epsilon, reward extraction. Integrates into conscious_decider (35% voting weight), chat_prompt_builder, dp_router. 4 new RL management routes. Paradigm shift from passive waiting to active questioning.
CHANGES = [
    'v2.14.0 Survey page rebuilt as 3-step wizard UI',
    'v2.14.0 Step 1: bedtime selection (10pm-2am+) with emoji picker',
    'v2.14.0 Step 2: sleep latency (5min-90min+) with mood icons',
    'v2.14.0 Step 3: awake times + total duration with grid picker',
    'v2.14.0 Step progress bar with dot indicators (1/2/3 -> checkmarks)',
    'v2.14.0 Saves to /api/update-profile (latest + history append)',
    'v2.14.0 After save: redirects to chat page with toast',
    'v2.14.0 Dark frosted glass theme, full-screen step layout',
    'v2.15.0 body_context module: synthesizes companion/emotion/survey data into embodied state',
    'v2.15.0 SCAN-inspired: body state injected as cognitive background into AI prompts',
    'v2.15.0 report_body_event API: companion_mode/emotion_monitor/dp_router all wired',
    'v2.15.0 recovery_state assessment: sleep_debt + emotion_baseline + circadian risk',
    'v2.15.0 render_body_context_text: readable body state for prompt injection',
    'v2.16.0 homeostatic_circuit module: parallel steady-state circuit with SignalBoard',
    'v2.16.0 SignalBoard: shared memory channel between homeostatic + intervention circuits',
    'v2.16.0 Homeostatic circuit: 3-min background scan, writes signals (sleep_debt/mood/risk)',
    'v2.16.0 Intervention circuit: reads signals via get_circuit_context() instead of re-scanning profile',
    'v2.16.0 Quiet hours enforcement (23:00-7:00): suppresses push signals',
    'v2.16.0 Scheduler daemon uses homeostatic signals for periodic_scan',
    'v2.16.0 Dual parallel architecture: SCAN-inspired "全身稳控 + 精确操作"',
    'v2.17.0 interoceptive_prediction module: simulate before acting (SCAN internal model)',
    'v2.17.0 simulate_suggestion_effect: predicts score change for each coach suggestion',
    'v2.17.0 select_suggestion_with_simulation: replaces weighted-random with sim-enhanced selection',
    'v2.17.0 simulate_push_effect: predicts if pushing will backfire on this user',
    'v2.17.0 simulate_companion_duration: predicts optimal companion length + protocol',
    'v2.17.0 sleep_coach._select_suggestion: enhanced with simulation engine',
    'v2.17.0 push_decision.decide_interaction: simulation suppresses push if user reacts negatively',
    'v2.17.0 Sim suppression: score<45 immediate push downgraded to delayed if simulation says avoid',
    'v2.17.0 Historical weighted moving average + confidence = interoceptive prediction engine',
    'v3.0.0 circadian_phase_model: individualized circadian rhythm model (cosine fitting)',
    'v3.0.0 acrophase/baseline/amplitude/drift_rate from bedtime history',
    'v3.0.0 drowsiness_at(hour): continuous 0~1 drowsiness prediction',
    'v3.0.0 get_circadian_signal: feeds phase/drift/drowsiness into homeostatic circuit',
    'v3.0.0 Homeostatic circuit: 5 new circadian signals (phase/drift/drowsiness/window)',
    'v3.0.0 get_circuit_context: includes circadian_drift/drowsiness/in_bedtime_window',
    'v3.0.0 Pure math fitting: no LLM, no training data, ~3ms per user',
    'v3.1.0 predict_tonight enhanced: circadian drift penalty (-2 to -4 pts if drift >5 min/d)',
    'v3.1.0 predict_tonight: weak circadian amplitude reduces confidence level',
    'v3.1.0 scheduler passes openid to predict_tonight for circadian lookup',
    'v3.1.0 get_daily_suggestion enhanced: circadian-aware action text',
    'v3.1.0 Coach suggests "in bedtime window" or "X min until window" cues',
    'v3.1.0 Coach appends drift warning if circadian rhythm is slipping',
    'v3.1.0 body_context renders time-of-day awareness + drowsiness + drift alerts',
    'v3.1.0 get_body_context marks available=True even without survey if circadian data exists',
    'v3.2.0 predictive_coding module: full predictive coding architecture',
    'v3.2.0 PredictionLayer: generic Bayesian update with uncertainty tracking',
    'v3.2.0 HierarchicalPredictor: score + circadian + response layers with cross-propagation',
    'v3.2.0 should_intervene: uncertainty-driven decision (replaces rule: score<50=>push)',
    'v3.2.0 High uncertainty -> chat mode (gather info, not push)',
    'v3.2.0 Low uncertainty + low score -> push only when system is confident',
    'v3.2.0 Intervention feedback updates response prediction layer',
    'v3.2.0 dp_router: predictive_coding context injected into chat prompt',
    'v3.2.0 dp_router: handle_sleep_analyze updates predictive_coding on survey submit',
    'v3.3.0 experiment_log module: every interaction logged as a scientific experiment',
    'v3.3.0 Experiment lifecycle: design -> deploy -> observe -> conclude',
    'v3.3.0 get_effectiveness: statistical analysis of past intervention outcomes',
    'v3.3.0 get_best_intervention: finds best intervention type for user',
    'v3.3.0 decide_with_history: active inference - use past experiments to choose action',
    'v3.3.0 New users default to chat (no history)',
    'v3.3.0 dp_router: chat interactions logged as experiments',
    'v3.3.0 dp_router: survey submission triggers experiment conclusion',
    'v3.4.0 meta_learner: daily self-review of experiments + auto-parameter tuning',
    'v3.4.0 ParamHistory: snapshot/rollback with safety bounds',
    'v3.4.0 SAFETY_BOUNDS: learning_rate(0.05-0.8), cooldown(1-60), push_threshold(30-70)',
    'v3.4.0 Review: success_rate drives learning_rate, push_success drives threshold',
    'v3.4.0 5 new routes: /api/meta/daily-review, /rollback, /summary, /adjustments, /param-history',
    'v3.4.0 Rollback: ctrl+z for parameter changes, continuous rollback supported',
    'v3.4.0 16 business modules, 40 routes, 35 Python files',
    'v3.5.0 conscious_decider: multi-signal weighted voting replaces push_decision rules',
    'v3.5.0 6 signals: predictive_coding(0.30) + experiment_log(0.20) + body_context(0.15)',
    'v3.5.0   + circadian(0.15) + interoceptive(0.10) + circuit_board(0.10)',
    'v3.5.0 5 actions: push_now, delay_push, in_chat, probe, skip',
    'v3.5.0 Curiosity: high uncertainty -> probe (active information gathering)',
    'v3.5.0 Safety: all weights clamped [0.05,0.5], normalized sum=1.0',
    'v3.5.0 Weight history: supports rollback (global WEIGHT_HISTORY)',
    'v3.5.0 dp_router: conscious_decider integrates as primary decision path',
    'v3.5.0 Fallback: push_decision remains as safety net',
    'v3.6.0 kalman_filter: 4D Kalman filter replaces heuristic PredictionLayer',
    'v3.6.0 State: [score, score_rate, bedtime, bedtime_rate] — optimal linear estimator',
    'v3.6.0 Adaptive Kalman gain: K automatically balances prediction vs observation',
    'v3.6.0 Regime change detection: z-score based anomaly detection in innovations',
    'v3.6.0 KalmanManager: per-user persistence in profile._kalman_filter',
    'v3.6.0 dp_router: KF updated on survey submit alongside predictive_coding',
    'v3.6.0 conscious_decider: KF signal (score, uncertainty, regime_change) added to voting',
    'v3.6.0 Regime change suppresses push (enters observation mode)',
    'v3.6.0 18 business modules, 7 new modules today, 37 Python files',
    'v3.7.0 free_energy: Free Energy Principle decision engine',
    'v3.7.0 F = prediction_energy - beta * KL_exploration_gain',
    'v3.7.0 KL: computes expected information gain of each action',
    'v3.7.0 Bayesian surprise: KL(posterior||prior) for anomaly detection',
    'v3.7.0 4 belief dimensions: score, bedtime, mood, rhythm (48 states total)',
    'v3.7.0 Action modifiers: probe(high info/low energy), push(low info/high energy)',
    'v3.7.0 F > 0 → action suppressed (not worth doing)',
    'v3.7.0 conscious_decider: FE correction kills positive-FE actions (-30%)',
    'v3.7.0 19 business modules, 39 Python files',
    'v3.7.0 Algorithm types: rules + cosine + Bayesian + Kalman + FE (KL-based)',
    'v3.8.0 active_inference: full POMDP-based belief state (150 hidden states)',
    'v3.8.0 BeliefState: entropy, predict_step (random walk), update_with_obs (Bayes)',
    'v3.8.0 Transition matrix T(s|s): diagonal-dominant (0.7 stay, 0.3 drift)',
    'v3.8.0 Likelihood matrix A(o|s): P(observation|hidden state)',
    'v3.8.0 FEP policy selection: G = utility + prior - beta * info_gain',
    'v3.8.0 Satisficing: good score + low entropy penalizes non-skip policies',
    'v3.8.0 Sequential decisions: belief converges, G differentiates over time',
    'v3.8.0 dp_router: AI (active inference) as primary decision path',
    'v3.8.0 Fallback chain: AI -> CD -> push_decision',
    'v3.8.0 40 Python files, 19 business modules, 40+ routes',
    'v3.9.0 pomdp_learner: online A matrix learning (Dirichlet posterior, forget factor)',
    'v3.9.0 Text observations: natural language -> obs dimensions -> POMDP belief update',
    'v3.9.0 Survey bypass: no structured input needed, text is the observation',
    'v3.9.0 A matrix learned from inferred state + count matrix with decay rate lambda',
    'v3.9.0 Combined FEP decision: utility + prior divergence - beta * info gain',
    'v3.9.0 dp_router: POMDP engine primary, CD fallback, push_decision last resort',
    'v3.9.0 41 Python files, 20 business modules',
]


# ===== 日志系统 =====
_LOGGER_INITIALIZED = False
_LOG_LEVELS = {'debug': logging.DEBUG, 'info': logging.INFO,
               'warn': logging.WARNING, 'error': logging.ERROR}


def init_logger(level='info', log_dir=None):
    """初始化统一日志系统。只应调用一次。
    level: debug/info/warn/error
    """
    global _LOGGER_INITIALIZED
    if _LOGGER_INITIALIZED:
        return logging.getLogger('aisleepgen')

    if log_dir is None:
        log_dir = os.path.join(PROJECT_ROOT, 'data', 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, 'aisleepgen.log')
    lvl = _LOG_LEVELS.get(level, logging.INFO)

    logger = logging.getLogger('aisleepgen')
    logger.setLevel(lvl)
    logger.handlers.clear()

    # 文件日志（轮转）
    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    except ImportError:
        fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(lvl)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(fh)

    # 控制台日志
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(lvl)
    ch.setFormatter(logging.Formatter(
        '[%(levelname)s] %(message)s'))
    logger.addHandler(ch)

    _LOGGER_INITIALIZED = True
    logger.info('AISleepGen v%s (%s) logger initialized', VERSION, VERSION_TAG)
    logger.info('Log file: %s', log_file)
    return logger


def get_logger():
    """获取日志器（惰性初始化）"""
    if not _LOGGER_INITIALIZED:
        return init_logger()
    return logging.getLogger('aisleepgen')


# ===== 进程保活 =====
_HEARTBEAT_THREAD = None
_HEARTBEAT_STOP = threading.Event()
_WATCHDOG_CALLBACKS = []


def register_watchdog(path, interval_seconds=3600, callback=None):
    """注册健康检查回调。返回控制函数。
    path: 检查的资源路径（如 /api/metrics）
    callback: 出问题时调用的函数
    """
    _WATCHDOG_CALLBACKS.append({
        'path': path,
        'interval': interval_seconds,
        'callback': callback or (lambda: None),
        'last_check': 0,
        'failures': 0,
    })
    return len(_WATCHDOG_CALLBACKS) - 1


def _heartbeat_loop():
    """保活线程：定期检查服务器健康"""
    import urllib.request
    get_logger().info('Heartbeat monitor started')
    while not _HEARTBEAT_STOP.is_set():
        for wd in _WATCHDOG_CALLBACKS:
            now = time.time()
            if now - wd['last_check'] < wd['interval']:
                continue
            wd['last_check'] = now
            try:
                url = 'http://127.0.0.1:8090' + wd['path']
                r = urllib.request.urlopen(url, timeout=5)
                body = r.read()
                wd['failures'] = 0
                get_logger().debug('Heartbeat OK: %s', wd['path'])
            except Exception as e:
                wd['failures'] += 1
                get_logger().error('Heartbeat FAIL (%d/%d): %s - %s',
                                   wd['failures'], 3, wd['path'], e)
                if wd['failures'] >= 3:
                    get_logger().critical('Server unhealthy after 3 failures! Running callback.')
                    try:
                        wd['callback']()
                    except Exception as cb_e:
                        get_logger().critical('Watchdog callback failed: %s', cb_e)
        _HEARTBEAT_STOP.wait(30)  # 每 30 秒检查一次


def start_heartbeat():
    """启动心跳保活线程"""
    global _HEARTBEAT_THREAD
    if _HEARTBEAT_THREAD and _HEARTBEAT_THREAD.is_alive():
        get_logger().warning('Heartbeat already running')
        return
    _HEARTBEAT_STOP.clear()
    _HEARTBEAT_THREAD = threading.Thread(target=_heartbeat_loop, daemon=True,
                                         name='heartbeat')
    _HEARTBEAT_THREAD.start()
    get_logger().info('Heartbeat monitor started')


def stop_heartbeat():
    """停止心跳"""
    _HEARTBEAT_STOP.set()
    if _HEARTBEAT_THREAD:
        _HEARTBEAT_THREAD.join(timeout=3)
    get_logger().info('Heartbeat monitor stopped')


# ===== 健康检查端点（供 server 注册路由） =====
def get_server_info():
    """返回服务器版本+状态快照"""
    return {
        'version': VERSION,
        'tag': VERSION_TAG,
        'uptime': time.time() - _SERVER_START_TIME,
        'started_at': datetime.fromtimestamp(_SERVER_START_TIME).isoformat(),
        'watchdogs': len(_WATCHDOG_CALLBACKS),
    }


_SERVER_START_TIME = time.time()


# ===== 初始化（import 时自动执行） =====
_init_logger = init_logger()
