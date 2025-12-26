# /home/hjh/BOT/NCBOT/plugins/PointsMall/utils/error_handler.py
# 错误处理和日志系统

import logging
import traceback
import sys
import os
from datetime import datetime
from typing import Dict, Any

class ErrorHandler:
    """错误处理管理器"""
    
    def __init__(self, log_dir: str = "/home/hjh/BOT/NCBOT/logs"):
        """初始化错误处理器"""
        self.log_dir = log_dir
        self.setup_logging()
        
    def setup_logging(self):
        """设置日志系统"""
        # 创建日志目录
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 配置日志格式
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        date_format = '%Y-%m-%d %H:%M:%S'
        
        # 文件处理器
        log_file = os.path.join(self.log_dir, f"points_mall_{datetime.now().strftime('%Y%m%d')}.log")
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        
        # 配置根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        # 创建模块特定的日志器
        self.logger = logging.getLogger('PointsMall')
        
    def log_error(self, error: Exception, context: Dict[str, Any] = None):
        """记录错误日志"""
        error_info = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'traceback': traceback.format_exc(),
            'timestamp': datetime.now().isoformat(),
            'context': context or {}
        }
        
        self.logger.error(f"错误类型: {error_info['error_type']}")
        self.logger.error(f"错误信息: {error_info['error_message']}")
        self.logger.error(f"上下文: {error_info['context']}")
        self.logger.error(f"堆栈跟踪:\n{error_info['traceback']}")
        
        return error_info
    
    def log_warning(self, message: str, context: Dict[str, Any] = None):
        """记录警告日志"""
        warning_info = {
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'context': context or {}
        }
        
        self.logger.warning(f"警告: {message}")
        if context:
            self.logger.warning(f"上下文: {context}")
            
        return warning_info
    
    def log_info(self, message: str, context: Dict[str, Any] = None):
        """记录信息日志"""
        info = {
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'context': context or {}
        }
        
        self.logger.info(f"信息: {message}")
        if context:
            self.logger.info(f"上下文: {context}")
            
        return info
    
    def log_debug(self, message: str, context: Dict[str, Any] = None):
        """记录调试日志"""
        debug_info = {
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'context': context or {}
        }
        
        self.logger.debug(f"调试: {message}")
        if context:
            self.logger.debug(f"上下文: {context}")
            
        return debug_info
    
    def handle_database_error(self, error: Exception, operation: str, params: Dict[str, Any] = None):
        """处理数据库错误"""
        context = {
            'operation': operation,
            'params': params,
            'error_type': 'DatabaseError'
        }
        
        error_info = self.log_error(error, context)
        
        # 返回用户友好的错误消息
        if "UNIQUE constraint failed" in str(error):
            return "操作失败：数据已存在"
        elif "FOREIGN KEY constraint failed" in str(error):
            return "操作失败：关联数据不存在"
        elif "no such table" in str(error):
            return "操作失败：数据库表不存在，请联系管理员"
        else:
            return "操作失败：数据库错误，请稍后重试"
    
    def handle_config_error(self, error: Exception, config_file: str, operation: str):
        """处理配置错误"""
        context = {
            'config_file': config_file,
            'operation': operation,
            'error_type': 'ConfigError'
        }
        
        error_info = self.log_error(error, context)
        
        if "YAMLError" in str(error):
            return "配置错误：YAML格式错误，请检查配置文件"
        elif "FileNotFoundError" in str(error):
            return "配置错误：配置文件不存在"
        else:
            return "配置错误：无法加载配置，请联系管理员"
    
    def handle_business_error(self, error: Exception, operation: str, user_id: str = None, group_id: str = None):
        """处理业务逻辑错误"""
        context = {
            'operation': operation,
            'user_id': user_id,
            'group_id': group_id,
            'error_type': 'BusinessError'
        }
        
        error_info = self.log_error(error, context)
        
        return "操作失败：系统繁忙，请稍后重试"
    
    def get_error_stats(self, hours: int = 24) -> Dict[str, Any]:
        """获取错误统计信息"""
        try:
            log_file = os.path.join(self.log_dir, f"points_mall_{datetime.now().strftime('%Y%m%d')}.log")
            
            if not os.path.exists(log_file):
                return {'total_errors': 0, 'error_types': {}}
            
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            error_count = 0
            error_types = {}
            
            for line in lines:
                if 'ERROR' in line:
                    error_count += 1
                    # 提取错误类型
                    if '错误类型:' in line:
                        error_type = line.split('错误类型:')[1].strip().split(' ')[0]
                        error_types[error_type] = error_types.get(error_type, 0) + 1
            
            return {
                'total_errors': error_count,
                'error_types': error_types,
                'time_range': f'最近{hours}小时'
            }
            
        except Exception as e:
            self.log_error(e, {'operation': 'get_error_stats'})
            return {'total_errors': 0, 'error_types': {}, 'error': str(e)}

# 创建全局错误处理器实例
error_handler = ErrorHandler()

def error_decorator(func):
    """错误处理装饰器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # 获取函数名和参数
            func_name = func.__name__
            func_args = {
                'args': str(args),
                'kwargs': str(kwargs)
            }
            
            # 记录错误
            error_handler.log_error(e, {
                'function': func_name,
                'arguments': func_args
            })
            
            # 重新抛出异常或返回错误信息
            raise
    
    return wrapper