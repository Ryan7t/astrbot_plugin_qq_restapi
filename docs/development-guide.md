# qq_restapi 开发指南

> 本文档整理了开发所需的关键信息，方便研究和参考

## 1. 项目结构（当前）

```
qq_restapi/
├── main.py                      # 插件入口
├── adapters/
│   ├── qq_restapi_adapter.py     # Gateway 适配器
│   ├── qq_restapi_webhook_adapter.py
│   ├── qq_restapi_webhook_server.py
│   └── ws_client.py
├── commands/
│   └── welcome_card_test.py      # 指令示例
├── runtime/
│   ├── context.py
│   ├── auto_events.py
│   ├── message_parser.py
│   ├── qq_restapi_event.py
│   ├── sender.py
│   ├── template_registry.py
│   ├── template_store.py
│   └── token_manager.py
├── utils/
│   └── scene.py                  # ✅ 场景解析工具
├── core/
│   └── qq/
│       ├── sender.py
│       └── token_manager.py
├── templates/
│   └── 102283541_1754015696.md
│   └── registry.yaml
└── doc/
    ├── astrbot-elaina-integration-proposal.md
    ├── astrbot-elaina-integration-requirements.md
    └── development-guide.md
```

## 2. 模块职责（调整后）

```
adapters/  - 平台适配器入口（WebSocket / Webhook）
runtime/   - 事件解析、发送、Token、模板渲染、自动业务逻辑
commands/  - 业务指令与测试入口
utils/     - 场景解析与公共工具
templates/ - Markdown 模板文本 + 模板注册表
core/      - 旧封装残留，后续可逐步合并到 runtime
```

---

## 3. 如何获取 appid/secret

### 方法一：从 context 获取配置

```python
from astrbot.api.star import Context, Star, register

@register("qq_restapi", "YourName", "描述", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

        # 获取配置
        config = context.get_config()

        # 从 platform 数组中找到 QQ 官方平台配置
        for platform in config.get("platform", []):
            if platform.get("type") in ["qq_official", "qq_official_webhook"]:
                if platform.get("enable"):
                    self.appid = platform.get("appid")
                    self.secret = platform.get("secret")
                    break
```

### 方法二：从 event 获取平台信息

```python
async def some_handler(self, event: AstrMessageEvent):
    platform_name = event.get_platform_name()  # "qq_official" 或 "qq_official_webhook"
    platform_id = event.get_platform_id()      # 配置中的 id，如 "小万小万"

    # 获取平台实例
    platform_inst = self.context.get_platform_inst(platform_id)
    # 注意：platform_inst 是 QQOfficialPlatformAdapter 实例
    # 但其 appid/secret 是私有属性
```

---

## 4. 关键 API 参考

### 4.1 AstrBot 事件对象 (AstrMessageEvent)

```python
# 常用属性和方法
event.message_str          # 纯文本消息字符串
event.message_obj          # AstrBotMessage 对象
event.message_obj.message_id   # 消息 ID（msg_id）
event.message_obj.group_id     # 群 ID
event.message_obj.sender.user_id  # 发送者 ID
event.message_obj.raw_message  # 原始消息对象（botpy 的 Message）

event.get_sender_id()      # 获取发送者 ID
event.get_sender_name()    # 获取发送者名称
event.get_platform_name()  # 获取平台名称 "qq_official"
event.get_platform_id()    # 获取平台配置 ID
event.get_message_type()   # 获取消息类型

# 发送消息（AstrBot 原生方式）
yield event.plain_result("文本内容")
yield event.image_result("图片路径或URL")
```

### 4.2 场景解析工具 (scene.py)

```python
from qq_restapi.utils.scene import resolve_scene, SceneContext, SceneType

# 解析场景
context = resolve_scene(self, event)

# 使用场景信息
context.scene_type     # SceneType.GROUP_CHAT / PRIVATE_CHAT / CHANNEL_SUB_CHANNEL / CHANNEL_DM
context.group_id       # 群 ID
context.user_id        # 用户 ID
context.channel_id     # 频道 ID
context.message_id     # 消息 ID
context.api_url        # API 端点 URL（已拼好）

# 场景判断
context.is_group       # 是否群聊
context.is_private     # 是否单聊
context.is_channel     # 是否频道相关
```

### 4.3 模板注册表（registry.yaml）

> 用于统一维护模板 ID / 参数 / 模板正文文件，同时映射自动业务事件

示例结构（简化）：

```yaml
templates:
  welcome_card:
    id: "102283541_1754015696"
    params: ["username", "daily_member_count", "channel_description"]
    file: "102283541_1754015696.md"
    keyboard_id: "102283541_1768141142"
    scenes: ["group", "channel"]

auto_events:
  group_add_robot:
    enabled: true
    fallback_text: "欢迎加入，本机器人已入群～"
    log: true
```

加载逻辑在 `runtime/template_registry.py`，支持 YAML/JSON，并带内存缓存。

### 4.4 自动业务事件（auto_events）

- 处理事件：入群/退群、好友添加/删除、新用户首次交互欢迎、频道事件/子频道事件/频道成员事件  
- 处理位置：`runtime/auto_events.py`  
- 行为特点：这些“关系事件”默认 **不进入 AstrBot 指令/LLM 管线**，避免被当作普通消息处理  
- 频道类事件默认仅记录日志，不发送通知

建议的插件配置项（`data/config/qq_restapi_config.json`）：

```json
{
  "group_add_robot_message": "欢迎加入，本机器人已入群～",
  "friend_add_message": "你好，我是小万，欢迎添加好友～",
  "new_user_welcome_message": "欢迎第一次和我聊天～",
  "enable_group_remove_notice": false,
  "enable_friend_remove_notice": false
}
```

---

## 5. QQ 官方 API 参考

### 5.1 获取 Token

```
POST https://bots.qq.com/app/getAppAccessToken
Content-Type: application/json

{
    "appId": "你的appid",
    "clientSecret": "你的secret"
}

响应：
{
    "access_token": "xxx",
    "expires_in": 7200
}
```

### 5.2 发送群消息

```
POST https://api.sgroup.qq.com/v2/groups/{group_id}/messages
Authorization: QQBot {access_token}
Content-Type: application/json

{
    "msg_type": 0,           // 0=文本, 2=Markdown, 3=Ark, 7=媒体
    "msg_id": "原消息ID",     // 被动回复必须携带
    "msg_seq": 12345,        // 随机序号
    "content": "消息内容"
}
```

### 5.3 发送 Markdown 模板

```json
{
    "msg_type": 2,
    "msg_id": "原消息ID",
    "msg_seq": 12345,
    "markdown": {
        "custom_template_id": "模板ID",
        "params": [
            {"key": "参数名1", "values": ["参数值1"]},
            {"key": "参数名2", "values": ["参数值2"]}
        ]
    },
    "keyboard": {
        "id": "按钮面板ID"
    }
}
```

### 5.4 构建按钮（如果不用面板ID）

```json
{
    "keyboard": {
        "content": {
            "rows": [
                {
                    "buttons": [
                        {
                            "id": "1",
                            "render_data": {
                                "label": "按钮文字",
                                "visited_label": "点击后文字",
                                "style": 0
                            },
                            "action": {
                                "type": 2,  // 0=跳转, 1=回调, 2=指令
                                "data": "/指令内容",
                                "permission": {"type": 2}
                            }
                        }
                    ]
                }
            ]
        }
    }
}
```

---

## 6. ElainaBot 关键代码参考

### 6.1 Token 管理 (function/Access.py)

路径：`/mnt/d/code/bot/ElainaBot/function/Access.py`

```python
# 核心逻辑
_token_info = {'access_token': None, 'expires_in': 0, 'last_update': 0}

def 获取新Token():
    response = requests.post(
        "https://bots.qq.com/app/getAppAccessToken",
        json={"appId": appid, "clientSecret": secret}
    )
    _token_info['access_token'] = response.json()['access_token']
    _token_info['expires_in'] = response.json()['expires_in']
    _token_info['last_update'] = time.time()

def BOT凭证():
    if not _token_info['access_token'] or 过期:
        获取新Token()
    return _token_info['access_token']

def BOTAPI(endpoint, method, data):
    return requests.request(
        method,
        f"https://api.sgroup.qq.com{endpoint}",
        headers={"Authorization": f"QQBot {BOT凭证()}"},
        json=data
    )
```

### 6.2 消息发送 (core/event/MessageEvent.py)

路径：`/mnt/d/code/bot/ElainaBot/core/event/MessageEvent.py`

关键方法：
- `reply()` - 通用回复（第435行）
- `reply_markdown()` - Markdown 模板（第473行）
- `reply_image()` - 图片消息（第456行）
- `button()` / `rows()` - 构建按钮（第1167行）
- `upload_media()` - 媒体上传（第955行）

---

## 7. 技术验证代码

### 验证脚本 (test_technical.py)

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
技术验证脚本 - 验证整合方案的可行性
"""

import asyncio
import httpx

# ========== 配置 ==========
APPID = "102083853"  # 从 cmd_config.json 获取
SECRET = "你的secret"  # 从 cmd_config.json 获取
TEST_GROUP_ID = "测试群ID"  # 需要一个测试群
TEST_MSG_ID = ""  # 需要一个消息ID来回复

# ========== Token 验证 ==========
async def test_token():
    """验证1：独立获取 token"""
    print("=" * 50)
    print("验证1：独立获取 Token")
    print("=" * 50)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://bots.qq.com/app/getAppAccessToken",
            json={"appId": APPID, "clientSecret": SECRET}
        )
        data = resp.json()

        if "access_token" in data:
            print(f"✅ Token 获取成功")
            print(f"   Token: {data['access_token'][:20]}...")
            print(f"   有效期: {data.get('expires_in', 'N/A')} 秒")
            return data["access_token"]
        else:
            print(f"❌ Token 获取失败: {data}")
            return None

# ========== 消息发送验证 ==========
async def test_send_message(token, group_id, msg_id):
    """验证2：直接 HTTP 发送消息"""
    print("\n" + "=" * 50)
    print("验证2：直接 HTTP 发送消息")
    print("=" * 50)

    if not token:
        print("❌ 无 Token，跳过")
        return

    if not group_id or not msg_id:
        print("⚠️ 需要提供 group_id 和 msg_id")
        print("   请在收到消息后，从日志中获取这些 ID")
        return

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.sgroup.qq.com/v2/groups/{group_id}/messages",
            headers={
                "Authorization": f"QQBot {token}",
                "Content-Type": "application/json"
            },
            json={
                "msg_type": 0,
                "msg_id": msg_id,
                "msg_seq": 12345,
                "content": "✅ 技术验证：HTTP 直接发送成功！"
            }
        )

        if resp.status_code == 200:
            print(f"✅ 消息发送成功")
            print(f"   响应: {resp.text[:100]}...")
        else:
            print(f"❌ 消息发送失败")
            print(f"   状态码: {resp.status_code}")
            print(f"   响应: {resp.text}")

# ========== 主函数 ==========
async def main():
    print("\n🔬 开始技术验证...\n")

    # 验证1：Token
    token = await test_token()

    # 验证2：发送消息（需要手动填写 group_id 和 msg_id）
    await test_send_message(token, TEST_GROUP_ID, TEST_MSG_ID)

    print("\n" + "=" * 50)
    print("验证完成")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. 下一步行动

### 阶段 -1：技术验证
1. 运行 `test_technical.py` 验证 Token 获取
2. 在插件中打印 `event.message_obj.message_id` 和 `event.message_obj.group_id`
3. 用获取到的 ID 测试消息发送

### 阶段 1：开发顺序
1. `runtime/token_manager.py` - Token 管理
2. `runtime/sender.py` - HTTP 发送封装
3. `runtime/message_parser.py` - 事件解析
4. `adapters/qq_restapi_adapter.py` - Gateway 适配器
5. `adapters/qq_restapi_webhook_adapter.py` - Webhook 适配器
6. `runtime/template_registry.py` - 模板注册表
7. `runtime/auto_events.py` - 自动业务逻辑

---

## 9. 参考文件路径

| 文件 | 路径 | 说明 |
|------|------|------|
| ElainaBot Token 管理 | `/mnt/d/code/bot/ElainaBot/function/Access.py` | Token 获取逻辑 |
| ElainaBot 消息发送 | `/mnt/d/code/bot/ElainaBot/core/event/MessageEvent.py` | 发送方法实现 |
| AstrBot QQ 适配器 | `/mnt/d/code/bot/AstrBotLauncher/AstrBot/astrbot/core/platform/sources/qqofficial/` | 参考消息接收 |
| AstrBot Context | `/mnt/d/code/bot/AstrBotLauncher/AstrBot/astrbot/core/star/context.py` | 插件上下文 |
| 主配置文件 | `/mnt/d/code/bot/AstrBotLauncher/AstrBot/data/cmd_config.json` | appid/secret 位置 |

---

*更新时间：2026-01-12*
