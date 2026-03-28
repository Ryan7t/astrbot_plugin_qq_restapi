Title: 插件存储 | AstrBot

URL Source: https://docs.astrbot.app/dev/star/guides/storage.html

Published Time: Fri, 09 Jan 2026 09:10:49 GMT

Markdown Content:
插件存储 [​](https://docs.astrbot.app/dev/star/guides/storage.html#%E6%8F%92%E4%BB%B6%E5%AD%98%E5%82%A8)
====================================================================================================

简单 KV 存储 [​](https://docs.astrbot.app/dev/star/guides/storage.html#%E7%AE%80%E5%8D%95-kv-%E5%AD%98%E5%82%A8)
------------------------------------------------------------------------------------------------------------

TIP

该功能需要 AstrBot 版本 >= 4.9.2。

插件可以使用 AstrBot 提供的简单 KV 存储功能来存储一些配置信息或临时数据。该存储是基于插件维度的，每个插件有独立的存储空间，互不干扰。

```py
class Main(star.Star):
    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        """Aloha!"""
        await self.put_kv_data("greeted", True)
        greeted = await self.get_kv_data("greeted", False)
        await self.delete_kv_data("greeted")
```

存储大文件规范 [​](https://docs.astrbot.app/dev/star/guides/storage.html#%E5%AD%98%E5%82%A8%E5%A4%A7%E6%96%87%E4%BB%B6%E8%A7%84%E8%8C%83)
----------------------------------------------------------------------------------------------------------------------------------

为了规范插件存储大文件的行为，请将大文件存储于 `data/plugin_data/{plugin_name}/` 目录下。

你可以通过以下代码获取插件数据目录：

```py
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

plugin_data_path = get_astrbot_data_path() / "plugin_data" / self.name # self.name 为插件名称，在 v4.9.2 及以上版本可用，低于此版本请自行指定插件名称
```
