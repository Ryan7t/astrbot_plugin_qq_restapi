Title: 杂项 | AstrBot

URL Source: https://docs.astrbot.app/dev/star/guides/other.html

Published Time: Fri, 09 Jan 2026 09:10:49 GMT

Markdown Content:
杂项 [​](https://docs.astrbot.app/dev/star/guides/other.html#%E6%9D%82%E9%A1%B9)
==============================================================================

获取消息平台实例 [​](https://docs.astrbot.app/dev/star/guides/other.html#%E8%8E%B7%E5%8F%96%E6%B6%88%E6%81%AF%E5%B9%B3%E5%8F%B0%E5%AE%9E%E4%BE%8B)
------------------------------------------------------------------------------------------------------------------------------------------

> v3.4.34 后

```python
from astrbot.api.event import filter, AstrMessageEvent

@filter.command("test")
async def test_(self, event: AstrMessageEvent):
    from astrbot.api.platform import AiocqhttpAdapter # 其他平台同理
    platform = self.context.get_platform(filter.PlatformAdapterType.AIOCQHTTP)
    assert isinstance(platform, AiocqhttpAdapter)
    # platform.get_client().api.call_action()
```

调用 QQ 协议端 API [​](https://docs.astrbot.app/dev/star/guides/other.html#%E8%B0%83%E7%94%A8-qq-%E5%8D%8F%E8%AE%AE%E7%AB%AF-api)
----------------------------------------------------------------------------------------------------------------------------

```py
@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    if event.get_platform_name() == "aiocqhttp":
        # qq
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
        assert isinstance(event, AiocqhttpMessageEvent)
        client = event.bot # 得到 client
        payloads = {
            "message_id": event.message_obj.message_id,
        }
        ret = await client.api.call_action('delete_msg', **payloads) # 调用 协议端  API
        logger.info(f"delete_msg: {ret}")
```

关于 CQHTTP API，请参考如下文档：

Napcat API 文档：[https://napcat.apifox.cn/](https://napcat.apifox.cn/)

Lagrange API 文档：[https://lagrange-onebot.apifox.cn/](https://lagrange-onebot.apifox.cn/)

获取载入的所有插件 [​](https://docs.astrbot.app/dev/star/guides/other.html#%E8%8E%B7%E5%8F%96%E8%BD%BD%E5%85%A5%E7%9A%84%E6%89%80%E6%9C%89%E6%8F%92%E4%BB%B6)
----------------------------------------------------------------------------------------------------------------------------------------------------

py`plugins = self.context.get_all_stars() # 返回 StarMetadata 包含了插件类实例、配置等等`

获取加载的所有平台 [​](https://docs.astrbot.app/dev/star/guides/other.html#%E8%8E%B7%E5%8F%96%E5%8A%A0%E8%BD%BD%E7%9A%84%E6%89%80%E6%9C%89%E5%B9%B3%E5%8F%B0)
----------------------------------------------------------------------------------------------------------------------------------------------------

```py
from astrbot.api.platform import Platform
platforms = self.context.platform_manager.get_insts() # List[Platform]
```
