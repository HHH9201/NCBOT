# Trae 项目规则：NapCat + NcatBot 开发

## 1. 项目背景与参考 (Context & References)
- **核心框架**: 基于 `napcat` + `ncatbot` 进行开发。
- **实现规范**:
  - 必须严格参考 `/home/hjh/BOT/NCBOT/plugins` 目录下现有插件的实现方式。
  - 所有插件**必须**使用 **装饰器模式**（如 `@bot.group_event`）进行事件注册。
- **文档参考**:
  - NapCat 协议说明：`/home/hjh/BOT/NCBOT/.trae/napcat.md`
  - NcatBot 框架说明：`/home/hjh/BOT/NCBOT/.trae/ncatbot.md`

## 2. 文件结构规范 (File Structure Guidelines)
- 每个插件的最上方注释一下改插件的简要功能。
- **路径注释**: **[强制]** 每个文件的第一行必须包含该文件的绝对路径注释。
  - 示例：`# /home/hjh/BOT/NCBOT/plugins/my_plugin/main.py`
- **插件目录结构**:
  - 插件主目录下 **只允许保留**：
    - `main.py`
    - `__init__.py`
  - **资源与工具**: 所有其他文件（辅助脚本、图片、数据资源等）必须存放在同级的 `tool` 文件夹内。
- **禁止项**:
  - **严禁**创建测试文件（`test_*.py`）、Markdown 文档或预览文件。
- **[强制]** 清理代码内的测试代码，只保留必要日志和可运行的代码

## 3. 数据库规范 (Database Standards)
- **数据库路径**: `/home/hjh/BOT/NCBOT/mydb/mydb.db`
- **表结构注释**:
  - 当在 `mydb.db` 中检测到或创建新表时，**必须**同步更新结构说明文件：`/home/hjh/BOT/NCBOT/mydb/mydb.db.comments.json`。
  - 在该 JSON 文件中添加对应的表注释和字段说明。

## 4. 业务逻辑：长消息转发 (Message Forwarding)
- **触发条件**: 当消息内容过多或过长不适合直接发送时，**必须**使用伪造合并转发 API。
- **API 配置**:
  - **URL**: `http://101.35.164.122:3006/send_group_forward_msg`
  - **Headers**:
    ```python
    {'Content-Type': 'application/json', 'Authorization': 'Bearer he031701'}
    ```
  - **Payload 结构**:
    ```python
    {"group_id": group_id, "messages": nodes}
    ```

## 5. 禁止安装pip包
- **[强制]** 严禁在插件开发过程中使用 `pip install` 安装任何第三方库。
- **[强制]** 优先查看虚拟环境是否存在该依赖，如不存在则安装依赖只在source ~/.ncatbot/bin/activate  中虚拟环境(.ncatbot) hjh@VM-0-13-ubuntu:~/BOT/NCBOT$ 中进行。
- **[强制]** 启动测试命令python main.py之后，运行成功，立即退出，不要保留，只保留一个。(TraeAI-9)终端即可
