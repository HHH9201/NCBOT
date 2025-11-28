# Root用户配置说明

## 功能概述
Root用户是签到插件的特殊管理员用户，仅拥有必要的特权功能，与普通用户保持一致的体验。

### Root用户特权
- **无限签到**：不受每日签到次数限制（主要用于测试）
- **连续签到保护**：连续签到天数不会因中断而重置

## 配置方法

### 1. 修改配置文件
Root用户配置已迁移到独立文件 `/home/hjh/BOT/NCBOT/plugins/PointsMall/config/root.yaml`，请在该文件中进行配置：

```yaml
# Root用户配置
root_config:
  # Root用户QQ号列表 - 修改这里添加你的QQ号
  root_users:
    - "123456789"  # 默认root用户，替换为你的QQ号
    - "987654321"  # 可以添加多个Root用户
  
  # Root用户特权配置
  privileges:
    unlimited_sign_in: true           # 无限签到
    sign_in_multiplier: 10            # 积分倍数
    extra_bonus: 100                  # 固定额外奖励
    consecutive_days_protected: true  # 连续签到保护
    special_title: "👑 Root管理员"     # 特殊称号
    message_prefix: "🔱【Root特权】"    # 消息前缀
```

### 2. 添加Root用户
将你希望设置为Root用户的QQ号添加到 `root_users` 列表中：

```yaml
root_users:
  - "你的QQ号"  # 替换为实际QQ号
  - "朋友的QQ号"  # 可以添加多个
```



## 使用说明



## 注意事项

1. **安全第一**：谨慎添加Root用户，确保只添加可信任的用户
2. **配置生效**：修改配置后无需重启，配置会实时生效
3. **数据安全**：Root用户的签到记录会正常保存到数据库
4. **兼容性好**：Root用户功能不影响普通用户的正常使用
5. **积分一致**：Root用户与普通用户积分计算完全一致，无额外加分

## 示例配置

```yaml
root_config:
  root_users:
    - "10001"  # 管理员QQ号
    - "10002"  # 副管理员QQ号
  
  privileges:
    unlimited_sign_in: true
    consecutive_days_protected: true
```

这样配置后，指定的Root用户将享受超级管理员的特权待遇！