- 每个文件最上方放一个路径注释
- mydb.db撞见新表之后，在mydb.db.comments.json文件内创建对应的表注释
- 可以参考/home/hjh/BOT/NCBOT/plugins是如何实现的，这里的全都是可以正常运行的插件，插件使用的是装饰器模式（ @bot.group_event ）
- 参考/home/hjh/BOT/NCBOT/plugins/napcat.md
- 参考/home/hjh/BOT/NCBOT/plugins/ncatbot.md
- 数据库/home/hjhBOT/NCBOT/mydb/mydb.db
- 如果消息过多过长需要要进行伪造转发消息则使用
    url = "http://101.35.164.122:3006/send_group_forward_msg"
    headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer he031701'}
    payload = {"group_id": group_id, "messages": nodes}  

- 强制禁止创建测试文件，文档，预览文件，
- 当前插件主文件下只保留main.py和__init__.py，其他文件均放到该插件主文件同目录下，创建图片文件等资源tool目录下，存放在与main.py相同目录下的tool文件夹内

