# /home/hjh/BOT/NCBOT/plugins/PointsMall/config/config_manager.py
# 配置管理器 - 支持热重载和多群组配置

import yaml
import os
import time
import threading
from typing import Dict, Any
import json
import sys
import os

# 添加错误处理器路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.error_handler import error_handler, error_decorator

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            # 使用 pathlib 获取当前文件目录的父目录的 config 目录
            from pathlib import Path
            current_dir = Path(__file__).parent.parent
            self.config_dir = str(current_dir / "config")
        else:
            self.config_dir = config_dir
        self.global_config = {}
        self.group_configs = {}
        self.config_files = {}
        self.last_modified = {}
        self.watch_thread = None
        self.watching = False
        
        # 加载配置
        self.load_all_configs()
        
        # 启动配置监控
        self.start_config_watch()
    
    def load_all_configs(self):
        """加载所有配置文件"""
        try:
            # 加载全局配置
            self.load_global_config()
            
            # 加载群组配置
            self.load_group_configs()
            
            print("✅ 配置加载完成")
            
        except Exception as e:
            print(f"❌ 配置加载失败: {e}")
    
    def load_global_config(self):
        """加载全局配置"""
        config_files = [
            'sign_in.yaml',
            'root.yaml', 
            'mall.yaml'
        ]
        
        self.global_config = {}
        
        for config_file in config_files:
            file_path = os.path.join(self.config_dir, config_file)
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        config_data = yaml.safe_load(f)
                        self.global_config[config_file.replace('.yaml', '')] = config_data
                    
                    # 记录文件修改时间
                    self.last_modified[file_path] = os.path.getmtime(file_path)
                    self.config_files[file_path] = config_file
                    
                    print(f"✅ 加载全局配置: {config_file}")
                    
                except Exception as e:
                    print(f"❌ 加载配置文件失败 {config_file}: {e}")
    
    def load_group_configs(self):
        """加载群组配置"""
        group_config_dir = os.path.join(self.config_dir, 'groups')
        
        if not os.path.exists(group_config_dir):
            os.makedirs(group_config_dir, exist_ok=True)
            return
        
        self.group_configs = {}
        
        for filename in os.listdir(group_config_dir):
            if filename.endswith('.yaml'):
                group_id = filename.replace('.yaml', '')
                file_path = os.path.join(group_config_dir, filename)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        group_config = yaml.safe_load(f)
                        self.group_configs[group_id] = group_config
                    
                    # 记录文件修改时间
                    self.last_modified[file_path] = os.path.getmtime(file_path)
                    self.config_files[file_path] = f"groups/{filename}"
                    
                    print(f"✅ 加载群组配置: {group_id}")
                    
                except Exception as e:
                    print(f"❌ 加载群组配置失败 {filename}: {e}")
    
    def get_config(self, group_id: str = None, config_type: str = 'sign_in') -> Dict[str, Any]:
        """获取配置
        
        Args:
            group_id: 群组ID，为None时返回全局配置
            config_type: 配置类型 sign_in/mall
        """
        config = self.global_config.get(config_type, {})
        
        # 如果指定了群组且有群组配置，则合并配置
        if group_id and group_id in self.group_configs:
            group_config = self.group_configs[group_id]
            
            # 合并配置，群组配置覆盖全局配置
            if config_type in group_config:
                config = self.deep_merge(config, group_config[config_type])
        
        return config
    
    def deep_merge(self, base: Dict, update: Dict) -> Dict:
        """深度合并字典"""
        result = base.copy()
        
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def set_group_config(self, group_id: str, config_type: str, config_data: Dict) -> bool:
        """设置群组配置"""
        try:
            group_config_dir = os.path.join(self.config_dir, 'groups')
            os.makedirs(group_config_dir, exist_ok=True)
            
            file_path = os.path.join(group_config_dir, f"{group_id}.yaml")
            
            # 读取现有配置
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_config = yaml.safe_load(f) or {}
            else:
                existing_config = {}
            
            # 更新配置
            existing_config[config_type] = config_data
            
            # 保存配置
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(existing_config, f, allow_unicode=True, indent=2)
            
            # 更新内存中的配置
            self.group_configs[group_id] = existing_config
            self.last_modified[file_path] = os.path.getmtime(file_path)
            self.config_files[file_path] = f"groups/{group_id}.yaml"
            
            print(f"✅ 群组 {group_id} 配置已更新")
            return True
            
        except Exception as e:
            print(f"❌ 设置群组配置失败: {e}")
            return False
    
    def start_config_watch(self):
        """启动配置监控线程"""
        if self.watch_thread and self.watch_thread.is_alive():
            return
        
        self.watching = True
        self.watch_thread = threading.Thread(target=self._watch_configs, daemon=True)
        self.watch_thread.start()
        
        print("🔍 配置监控已启动")
    
    def stop_config_watch(self):
        """停止配置监控"""
        self.watching = False
        if self.watch_thread:
            self.watch_thread.join(timeout=5)
        
        print("🔍 配置监控已停止")
    
    def _watch_configs(self):
        """监控配置文件变化"""
        while self.watching:
            try:
                time.sleep(10)  # 每10秒检查一次
                
                for file_path, last_mtime in self.last_modified.items():
                    if not os.path.exists(file_path):
                        continue
                    
                    current_mtime = os.path.getmtime(file_path)
                    
                    if current_mtime > last_mtime:
                        print(f"🔄 检测到配置文件变化: {self.config_files[file_path]}")
                        
                        # 重新加载配置
                        if file_path.startswith(os.path.join(self.config_dir, 'groups')):
                            self.load_group_configs()
                        else:
                            self.load_global_config()
                        
                        # 更新修改时间
                        self.last_modified[file_path] = current_mtime
                        
                        print("✅ 配置热重载完成")
                
            except Exception as e:
                print(f"❌ 配置监控错误: {e}")
    
    def validate_config(self, config_type: str, config_data: Dict) -> Dict[str, Any]:
        """验证配置有效性"""
        errors = []
        
        if config_type == 'sign_in':
            # 验证签到配置
            points_config = config_data.get('points_config', {})
            
            if points_config.get('base_points', 0) < 0:
                errors.append("基础积分不能为负数")
            
            if points_config.get('consecutive_bonus', 0) < 0:
                errors.append("连续签到奖励不能为负数")
            
            if points_config.get('max_consecutive_bonus', 0) < 0:
                errors.append("最大连续奖励不能为负数")
        
        elif config_type == 'mall':
            # 验证商城配置
            mall_config = config_data.get('mall_config', {})
            
            if mall_config.get('daily_limit', 0) < 0:
                errors.append("每日兑换限制不能为负数")
            
            lottery_config = config_data.get('lottery_config', {})
            if lottery_config.get('cost_per_try', 0) < 0:
                errors.append("抽奖消耗积分不能为负数")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def get_config_summary(self) -> str:
        """获取配置摘要"""
        summary = ["📋 配置摘要"]
        summary.append("=" * 30)
        
        # 全局配置
        summary.append("🌐 全局配置:")
        for config_name in self.global_config.keys():
            summary.append(f"  • {config_name}.yaml")
        
        # 群组配置
        summary.append(f"\n👥 群组配置 ({len(self.group_configs)}个群组):")
        for group_id in self.group_configs.keys():
            summary.append(f"  • {group_id}.yaml")
        
        # 监控状态
        summary.append(f"\n🔍 配置监控: {'运行中' if self.watching else '已停止'}")
        
        return "\n".join(summary)
    
    def __del__(self):
        """析构函数，确保监控线程正确停止"""
        self.stop_config_watch()