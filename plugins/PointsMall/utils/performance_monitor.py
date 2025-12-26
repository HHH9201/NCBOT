# /home/hjh/BOT/NCBOT/plugins/PointsMall/utils/performance_monitor.py
# 性能监控和统计工具

import time
import psutil
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List
import sqlite3
import json

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, db_path: str = "/home/hjh/BOT/NCBOT/mydb/mydb.db"):
        """初始化性能监控器"""
        self.db_path = db_path
        self.metrics = {}
        self.start_time = time.time()
        self.monitor_thread = None
        self.monitoring = False
        
        # 初始化数据库
        self.init_database()
        
        # 启动监控线程
        self.start_monitoring()
    
    def init_database(self):
        """初始化性能监控数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 性能指标表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS performance_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        metric_name TEXT NOT NULL,
                        metric_value REAL NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        group_id TEXT,
                        user_id TEXT
                    )
                ''')
                
                # 系统资源表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_resources (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cpu_percent REAL,
                        memory_percent REAL,
                        disk_usage REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # API调用统计表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS api_statistics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        api_name TEXT NOT NULL,
                        call_count INTEGER DEFAULT 0,
                        avg_response_time REAL,
                        error_count INTEGER DEFAULT 0,
                        last_called DATETIME,
                        group_id TEXT
                    )
                ''')
                
                # 创建索引
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_perf_metrics_name_time ON performance_metrics(metric_name, timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_sys_resources_time ON system_resources(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_api_stats_name ON api_statistics(api_name)')
                
                conn.commit()
                
        except Exception as e:
            print(f"性能监控数据库初始化失败: {e}")
    
    def start_monitoring(self):
        """启动性能监控"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_system, daemon=True)
        self.monitor_thread.start()
    
    def _monitor_system(self):
        """监控系统资源"""
        while self.monitoring:
            try:
                # 收集系统资源信息
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                # 记录到数据库
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO system_resources 
                        (cpu_percent, memory_percent, disk_usage) 
                        VALUES (?, ?, ?)
                    ''', (cpu_percent, memory.percent, disk.percent))
                    conn.commit()
                
                # 每30秒收集一次
                time.sleep(30)
                
            except Exception as e:
                print(f"系统监控错误: {e}")
                time.sleep(60)  # 出错时等待更长时间
    
    def record_metric(self, metric_name: str, value: float, group_id: str = None, user_id: str = None):
        """记录性能指标"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO performance_metrics 
                    (metric_name, metric_value, group_id, user_id) 
                    VALUES (?, ?, ?, ?)
                ''', (metric_name, value, group_id, user_id))
                conn.commit()
                
        except Exception as e:
            print(f"记录性能指标失败: {e}")
    
    def record_api_call(self, api_name: str, response_time: float, success: bool = True, group_id: str = None):
        """记录API调用统计"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 检查是否已有记录
                cursor.execute('''
                    SELECT call_count, avg_response_time, error_count 
                    FROM api_statistics 
                    WHERE api_name = ? AND group_id = ?
                ''', (api_name, group_id))
                
                result = cursor.fetchone()
                
                if result:
                    # 更新现有记录
                    call_count = result[0] + 1
                    avg_time = ((result[1] * result[0]) + response_time) / call_count
                    error_count = result[2] + (0 if success else 1)
                    
                    cursor.execute('''
                        UPDATE api_statistics 
                        SET call_count = ?, avg_response_time = ?, error_count = ?, last_called = CURRENT_TIMESTAMP
                        WHERE api_name = ? AND group_id = ?
                    ''', (call_count, avg_time, error_count, api_name, group_id))
                else:
                    # 插入新记录
                    cursor.execute('''
                        INSERT INTO api_statistics 
                        (api_name, call_count, avg_response_time, error_count, last_called, group_id)
                        VALUES (?, 1, ?, ?, CURRENT_TIMESTAMP, ?)
                    ''', (api_name, response_time, 0 if success else 1, group_id))
                
                conn.commit()
                
        except Exception as e:
            print(f"记录API调用统计失败: {e}")
    
    def get_system_stats(self, hours: int = 24) -> Dict[str, Any]:
        """获取系统统计信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 获取CPU使用率统计
                cursor.execute('''
                    SELECT 
                        AVG(cpu_percent) as avg_cpu,
                        MAX(cpu_percent) as max_cpu,
                        MIN(cpu_percent) as min_cpu
                    FROM system_resources 
                    WHERE timestamp > datetime('now', ?)
                ''', (f'-{hours} hours',))
                
                cpu_stats = cursor.fetchone()
                
                # 获取内存使用率统计
                cursor.execute('''
                    SELECT 
                        AVG(memory_percent) as avg_memory,
                        MAX(memory_percent) as max_memory,
                        MIN(memory_percent) as min_memory
                    FROM system_resources 
                    WHERE timestamp > datetime('now', ?)
                ''', (f'-{hours} hours',))
                
                memory_stats = cursor.fetchone()
                
                # 获取API调用统计
                cursor.execute('''
                    SELECT 
                        api_name,
                        SUM(call_count) as total_calls,
                        AVG(avg_response_time) as avg_response,
                        SUM(error_count) as total_errors
                    FROM api_statistics 
                    GROUP BY api_name
                    ORDER BY total_calls DESC
                ''')
                
                api_stats = cursor.fetchall()
                
                return {
                    'cpu_usage': {
                        'average': round(cpu_stats[0], 2) if cpu_stats[0] else 0,
                        'maximum': round(cpu_stats[1], 2) if cpu_stats[1] else 0,
                        'minimum': round(cpu_stats[2], 2) if cpu_stats[2] else 0
                    },
                    'memory_usage': {
                        'average': round(memory_stats[0], 2) if memory_stats[0] else 0,
                        'maximum': round(memory_stats[1], 2) if memory_stats[1] else 0,
                        'minimum': round(memory_stats[2], 2) if memory_stats[2] else 0
                    },
                    'api_statistics': [
                        {
                            'api_name': row[0],
                            'total_calls': row[1],
                            'avg_response_time': round(row[2], 3) if row[2] else 0,
                            'error_count': row[3],
                            'success_rate': round((row[1] - row[3]) / row[1] * 100, 2) if row[1] > 0 else 100
                        }
                        for row in api_stats
                    ]
                }
                
        except Exception as e:
            return {'error': str(e)}
    
    def get_performance_metrics(self, metric_name: str, hours: int = 24) -> List[Dict[str, Any]]:
        """获取特定性能指标的历史数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT metric_value, timestamp, group_id, user_id
                    FROM performance_metrics
                    WHERE metric_name = ? AND timestamp > datetime('now', ?)
                    ORDER BY timestamp ASC
                ''', (metric_name, f'-{hours} hours'))
                
                results = cursor.fetchall()
                
                return [
                    {
                        'value': row[0],
                        'timestamp': row[1],
                        'group_id': row[2],
                        'user_id': row[3]
                    }
                    for row in results
                ]
                
        except Exception as e:
            return []
    
    def cleanup_old_data(self, days: int = 30):
        """清理旧数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 删除旧数据
                cursor.execute('DELETE FROM performance_metrics WHERE timestamp < datetime("now", ?)', 
                             (f'-{days} days',))
                cursor.execute('DELETE FROM system_resources WHERE timestamp < datetime("now", ?)', 
                             (f'-{days} days',))
                
                deleted_rows = cursor.rowcount
                conn.commit()
                
                return {'deleted_rows': deleted_rows}
                
        except Exception as e:
            return {'error': str(e)}

# 创建全局性能监控器实例
performance_monitor = PerformanceMonitor()

def performance_decorator(api_name: str):
    """性能监控装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise e
            finally:
                end_time = time.time()
                response_time = end_time - start_time
                
                # 记录API调用统计
                group_id = None
                if len(args) > 0 and hasattr(args[0], 'group_id'):
                    group_id = args[0].group_id
                elif 'group_id' in kwargs:
                    group_id = kwargs['group_id']
                
                performance_monitor.record_api_call(api_name, response_time, success, group_id)
        
        return wrapper
    
    return decorator