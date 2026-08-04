import redis  # Add this import at top of file

class PerformanceMonitor:

    def __init__(self, redis_host='localhost'):
        self.redis = redis.Redis(host=redis_host)
        
    def track_critical_metrics(self):
        """核心性能指标采集"""
        return {
            'throughput': self._calc_requests_per_second(),
            'latency': self._avg_network_latency(),
            'shard_balance': self._shard_imbalance_score(),
            'audio_sync': self._audio_video_drift(),
            'failover_count': self._count_failovers()
        }
    

    
    def _calc_requests_per_second(self):
        """计算每秒请求量"""
        return self.redis.info('stats')['instantaneous_ops_per_sec']
    
    def _avg_network_latency(self):
        """计算平均网络延迟(毫秒)"""
        cluster_info = self.redis.execute_command('CLUSTER INFO')
        return float(cluster_info['avg_cluster_latency']) * 1000
    
    def _shard_imbalance_score(self):
        """计算分片不均衡分数(0-1)"""
        shards = self.redis.hgetall('cluster_shard_distribution')
        counts = [int(c) for c in shards.values()]
        return (max(counts) - min(counts)) / max(counts) if counts else 0


    
    def _count_failovers(self):
        """统计故障转移次数"""
        return self.redis.info('replication').get('failover_count', 0)

    
    def _audio_video_drift(self):
        """计算音视频同步误差(毫秒)"""
        try:
            sync_data = self.redis.get('audio_sync_metrics') or '{}'
            return json.loads(sync_data).get('max_drift_ms', 0)
        except:
            return 0


class ShardMonitor:
    def __init__(self, redis_host='localhost'):
        self.redis = redis.Redis(host=redis_host)
        
    def get_shard_health(self):
        """获取分片健康状态"""
        return {
            'unbalanced_shards': self._detect_unbalanced(),
            'migration_history': self._get_migration_stats(),
            'recommendations': self._generate_sharding_advice()
        }

    
    def _detect_unbalanced(self):
        """检测不均衡分片"""
        shards = self.redis.hgetall('cluster_shard_distribution')
        avg = sum(int(c) for c in shards.values()) / len(shards)
        return [
            shard for shard, count in shards.items()
            if int(count) > avg * 1.5  # 超过平均值1.5倍视为不均衡
        ]
    
    def _generate_sharding_advice(self):
        """生成分片优化建议"""
        imbalance = self._shard_imbalance_score()
        if imbalance > 0.3:
            return "建议立即执行分片再平衡"
        elif imbalance > 0.1:
            return "建议在低峰期执行分片再平衡"
        return "当前分片分布均衡"
    
class AlertManager:
    def __init__(self, performance_monitor=None):
        self.performance_monitor = performance_monitor or PerformanceMonitor()
    def check_alerts(self):
        """检查并触发告警"""
        metrics = self.performance_monitor.track_critical_metrics()
        if metrics['latency'] > 300:  # 300ms延迟阈值
            self._trigger_alert('high_latency', metrics)
        if metrics['shard_balance'] > 0.3:
            self._trigger_alert('shard_imbalance', metrics)
            
    def _trigger_alert(self, alert_type, context):
        """触发告警"""
        message = {
            'high_latency': '网络延迟过高',
            'shard_imbalance': '分片负载不均衡'
        }.get(alert_type, '系统告警')
        print(f"[ALERT] {message} - {context}")
