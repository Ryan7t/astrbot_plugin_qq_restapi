# 机器人 Bot API 文档

## 概述
- **服务名称**：机器人对接接口
- **版本**：v1.1
- **基础路径**：`/bot`
- **认证方式**：HMAC-SHA256 请求签名（非 JWT）
- **时间格式**：`YYYY-MM-DD HH:MM:SS`
- **用户身份要求**：所有读写接口都必须提供 `unionid`
- **隐私约束**：所有 Bot 接口不返回数据库自增 `id`

## 统一响应格式

### 成功响应
```json
{
  "success": true,
  "data": {}
}
```

### 失败响应
```json
{
  "success": false,
  "error": "错误描述",
  "code": "错误码"
}
```

### 失败响应示例
鉴权失败（401）：
```json
{
  "success": false,
  "error": "signature_failed",
  "code": "INVALID_SIGNATURE"
}
```

业务失败（400/404/500）：
```json
{
  "success": false,
  "error": "name 不能为空",
  "code": "MISSING_PARAMS"
}
```

## 认证机制

### 请求头（必填）
- `X-Bot-App-Id`
- `X-Bot-Timestamp`（Unix 秒级时间戳）
- `X-Bot-Nonce`（随机字符串）
- `X-Bot-Signature`（HMAC-SHA256 十六进制字符串）

### 签名参数来源
签名参数按以下顺序合并：
1. 路径参数（`request.view_args`）
2. Query 参数（`request.args`）
3. JSON Body 顶层参数（`POST/PUT/PATCH`）

参数处理规则：
- `None` 值忽略
- `list` 使用逗号拼接（如 `["a","b"] -> "a,b"`）
- 其他类型转字符串
- 按参数名升序排序后拼接 `k=v&k=v`

### 签名原串
`<sorted_params>&timestamp=<ts>&nonce=<nonce>&key=<BOT_API_SECRET>`

算法：`HMAC-SHA256`

### 时效与防重放
- 时间窗：`abs(now - timestamp) <= BOT_SIGNATURE_TTL_SECONDS`（默认 300 秒）
- nonce：5 分钟内不可重复（当前为进程内内存缓存）

### 鉴权错误码（HTTP 401）
| code | 说明 |
| --- | --- |
| `BOT_CONFIG_MISSING` | 后端未配置 `BOT_APP_ID` 或 `BOT_API_SECRET` |
| `MISSING_PARAMS` | 缺少签名头 |
| `INVALID_APP_ID` | `X-Bot-App-Id` 不匹配 |
| `IP_NOT_ALLOWED` | IP 不在白名单（启用时） |
| `INVALID_TIMESTAMP` | 时间戳格式非法 |
| `TIMESTAMP_EXPIRED` | 时间戳超时 |
| `NONCE_REPLAY` | nonce 重放 |
| `INVALID_SIGNATURE` | 签名不匹配 |

## 数据模型说明

### 用户识别与映射
后端映射凭证：
- `credential_type = qqbot_unionid`
- `credential_value = unionid`
- `issuer = X-Bot-App-Id`

映射结果：
- 命中则复用 `users.id`
- 未命中则创建 `users` 与 `user_credentials` 记录

### 数据库迁移
`user_credentials.credential_type` 需包含 `qqbot_unionid`：
```sql
ALTER TABLE user_credentials
MODIFY credential_type ENUM(
  'phone','wechat_openid','qq_openid','bot','qq_unionid','wx_unionid','email','qqbot_unionid'
);
```

## 接口列表

### 1) 搜索留言
- **URL**：`GET /bot/messages/search`
- **说明**：按姓名搜索留言（分页）
- **Query 参数**：
  - `unionid`：必填
  - `name`：必填，搜索关键词
  - `page`：可选，默认 `1`
  - `page_size`：可选，默认 `10`，范围 `1-50`

**成功响应（200）**
```json
{
  "success": true,
  "data": {
    "list": [
      {
        "name": "张三",
        "content": "你好",
        "created_at": "2026-01-29 20:00:00",
        "like_count": 0,
        "sender": {
          "nickname": "用户昵称",
          "avatar_url": "https://example.com/avatar.png"
        }
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 10,
      "total": 1,
      "total_pages": 1
    }
  }
}
```

**失败响应**
- `401`：签名错误（见鉴权错误码）
- `400 MISSING_PARAMS`：缺少 `unionid` 或 `name`
- `400 INVALID_PARAMS`：参数非法
- `500 INTERNAL_ERROR`：服务异常

### 2) 最新留言（固定 5 条）
- **URL**：`GET /bot/messages/latest`
- **说明**：按创建时间倒序返回最新 5 条留言
- **Query 参数**：
  - `unionid`：必填

**成功响应（200）**
```json
{
  "success": true,
  "data": {
    "list": [
      {
        "name": "张三",
        "to_name": "张三",
        "content": "最新留言",
        "created_at": "2026-01-29 20:00:00",
        "like_count": 0,
        "sender": {
          "nickname": "用户昵称",
          "avatar_url": "https://example.com/avatar.png"
        }
      }
    ]
  }
}
```

**失败响应**
- `401`：签名错误（见鉴权错误码）
- `400 MISSING_PARAMS`：缺少 `unionid`
- `400 INVALID_PARAMS`：参数非法
- `500 INTERNAL_ERROR`：服务异常

### 3) 随机留言（固定 1 条）
- **URL**：`GET /bot/messages/random`
- **说明**：返回 1 条随机留言
- **Query 参数**：
  - `unionid`：必填
  - `first_char`：可选，按首字筛选

**成功响应（200）**
```json
{
  "success": true,
  "data": {
    "message": {
      "name": "张三",
      "to_name": "张三",
      "content": "你好",
      "created_at": "2026-01-29 20:00:00",
      "like_count": 0,
      "sender": {
        "nickname": "用户昵称",
        "avatar_url": "https://example.com/avatar.png"
      }
    }
  }
}
```

**失败响应**
- `401`：签名错误（见鉴权错误码）
- `400 MISSING_PARAMS`：缺少 `unionid`
- `400 INVALID_PARAMS`：参数非法
- `404 NOT_FOUND`：暂无可用留言
- `500 INTERNAL_ERROR`：服务异常

### 4) 随机树洞（固定 1 条）
- **URL**：`GET /bot/tree-holes/random`
- **说明**：随机返回 1 条树洞
- **Query 参数**：
  - `unionid`：必填
  - `exclude_ids`：可选，逗号分隔（仅数字会生效）
  - `seed`：可选，浮点数

**成功响应（200）**
```json
{
  "success": true,
  "data": {
    "tree_hole": {
      "content": "树洞内容",
      "images": [],
      "is_anonymous": true,
      "created_at": "2026-01-29 20:00:00"
    },
    "statistics": {
      "like_count": 0,
      "comment_count": 0
    },
    "sender": {
      "nickname": "用户昵称",
      "avatar_url": "https://example.com/avatar.png"
    }
  }
}
```

**失败响应**
- `401`：签名错误（见鉴权错误码）
- `400 MISSING_PARAMS`：缺少 `unionid`
- `400 INVALID_PARAMS`：参数非法
- `404 NOT_FOUND`：暂无可用树洞
- `500 INTERNAL_ERROR`：服务异常

### 5) 写留言
- **URL**：`POST /bot/messages`
- **说明**：创建留言，作者为 `unionid` 映射用户
- **Body**：
```json
{
  "unionid": "u001",
  "name": "张三",
  "content": "留言内容",
  "show_author": false,
  "nickname": "机器人昵称",
  "avatar_url": "https://example.com/avatar.png"
}
```

字段说明：
- `unionid`：必填
- `name`：必填
- `content`：必填
- `show_author`：可选，默认 `false`
- `nickname`：可选，存在则更新用户昵称
- `avatar_url`：可选，存在则更新用户头像

**成功响应（200）**
```json
{
  "success": true,
  "data": {
    "message": {
      "name": "张三",
      "to_name": "张三",
      "content": "留言内容",
      "created_at": "2026-01-29 20:00:00",
      "like_count": 0,
      "sender": {
        "nickname": "机器人昵称",
        "avatar_url": "https://example.com/avatar.png"
      }
    }
  }
}
```

**失败响应**
- `401`：签名错误（见鉴权错误码）
- `400 MISSING_PARAMS`：缺少 `unionid`、`name` 或 `content`
- `400 INVALID_PARAMS`：业务参数校验失败
- `500 INTERNAL_ERROR`：服务异常

### 6) 写树洞
- **URL**：`POST /bot/tree-holes`
- **说明**：创建树洞，作者为 `unionid` 映射用户
- **Body**：
```json
{
  "unionid": "u001",
  "content": "树洞内容",
  "images": ["https://example.com/a.jpg"],
  "is_anonymous": true,
  "nickname": "机器人昵称",
  "avatar_url": "https://example.com/avatar.png"
}
```

字段说明：
- `unionid`：必填
- `content`：必填
- `images`：可选，数组
- `is_anonymous`：可选，默认 `true`
- `nickname/avatar_url`：可选，更新用户资料

**成功响应（200）**
```json
{
  "success": true,
  "data": {
    "tree_hole": {
      "content": "树洞内容",
      "images": [],
      "is_anonymous": true,
      "created_at": "2026-01-29 20:00:00"
    },
    "statistics": {
      "like_count": 0,
      "comment_count": 0
    },
    "sender": {
      "nickname": "机器人昵称",
      "avatar_url": "https://example.com/avatar.png"
    }
  }
}
```

**失败响应**
- `401`：签名错误（见鉴权错误码）
- `400 MISSING_PARAMS`：缺少 `unionid` 或 `content`
- `400 INVALID_PARAMS`：业务参数校验失败
- `500 INTERNAL_ERROR`：服务异常

## 已下线接口
- `GET /bot/tree-holes/{tree_hole_id}`（树洞详情接口已下线）

## 业务错误码（HTTP 400/404/500）
| code | 说明 |
| --- | --- |
| `MISSING_PARAMS` | 缺少必要参数 |
| `INVALID_PARAMS` | 参数或业务校验失败 |
| `NOT_FOUND` | 无可用数据或资源不存在 |
| `INTERNAL_ERROR` | 服务端异常 |

## 机器人侧调用参考（Python）
```python
import hashlib
import hmac
import time
import requests


def normalize_value(value):
    if value is None:
        return None
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def build_signature(params: dict, timestamp: str, nonce: str, secret: str) -> str:
    normalized = {}
    for key, value in params.items():
        normalized_value = normalize_value(value)
        if normalized_value is not None:
            normalized[key] = normalized_value

    sign_str = "&".join(f"{k}={normalized[k]}" for k in sorted(normalized.keys()))
    sign_str += f"&timestamp={timestamp}&nonce={nonce}&key={secret}"
    return hmac.new(secret.encode(), sign_str.encode(), hashlib.sha256).hexdigest()


def call_get(base_url: str, path: str, query: dict, path_params: dict, app_id: str, secret: str):
    timestamp = str(int(time.time()))
    nonce = f"n{timestamp}"

    # 注意：路径参数必须参与签名，例如 tree_hole_id
    sign_source = {}
    sign_source.update(path_params or {})
    sign_source.update(query or {})

    signature = build_signature(sign_source, timestamp, nonce, secret)
    headers = {
        "X-Bot-App-Id": app_id,
        "X-Bot-Timestamp": timestamp,
        "X-Bot-Nonce": nonce,
        "X-Bot-Signature": signature,
    }
    return requests.get(base_url + path, params=query, headers=headers, timeout=10)


def call_post(base_url: str, path: str, body: dict, app_id: str, secret: str):
    timestamp = str(int(time.time()))
    nonce = f"n{timestamp}"

    signature = build_signature(body or {}, timestamp, nonce, secret)
    headers = {
        "X-Bot-App-Id": app_id,
        "X-Bot-Timestamp": timestamp,
        "X-Bot-Nonce": nonce,
        "X-Bot-Signature": signature,
    }
    return requests.post(base_url + path, json=body, headers=headers, timeout=10)
```

## 联调建议
1. 先联通 `GET /bot/messages/random`，验证签名和时间窗。  
2. 再联通 `GET /bot/messages/latest`，确认固定返回 5 条最新留言。  
3. 联调 `POST /bot/messages` 与 `POST /bot/tree-holes`，验证 `unionid -> user_id` 自动映射。  
4. 覆盖失败场景：错误签名、重复 nonce、过期 timestamp、缺失 unionid。  
