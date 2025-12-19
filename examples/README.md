# Citeo API 客户端示例

本目录包含使用 Citeo API 的示例代码。

## 示例列表

### `smart_client.py` - 智能客户端（推荐）

完整的 Python 客户端实现，自动处理所有 Token 管理：

**特性：**
- ✅ 自动登录（使用 API Key）
- ✅ 自动刷新 Access Token（过期前 5 分钟）
- ✅ Refresh Token 过期时自动重新登录
- ✅ 错误处理和重试
- ✅ 支持所有 API 端点

**使用方法：**
```python
from smart_client import CiteoClient

# 初始化客户端
client = CiteoClient("http://localhost:8000", "your-api-key")

# 获取论文（自动处理所有 Token 管理）
papers = client.get_papers_by_date()
print(f"Found {papers['count']} papers")

# 分析论文
result = client.analyze_paper("2512.14709")

# 登出
client.logout()
```

**适用场景：**
- 长期运行的应用程序
- 需要频繁调用 API 的脚本
- 不想手动管理 Token 的场景

## Token 生命周期说明

### 完整流程

```
1. 初始登录
   client = CiteoClient(base_url, api_key)
   papers = client.get_papers_by_date()  # 自动调用 login()

2. 正常使用（1小时内）
   papers = client.get_papers_by_date()  # 使用现有 access token

3. Token 快过期（第55分钟）
   papers = client.get_papers_by_date()  # 自动调用 refresh_tokens()

4. Refresh Token 也过期了（第8天）
   papers = client.get_papers_by_date()  # refresh 失败，自动重新 login()
```

### 关键时间点

| 事件 | 时间 | 处理方式 |
|------|------|----------|
| Access Token 有效期 | 1 小时 | 自动刷新 |
| Refresh Token 有效期 | 7 天 | 过期后自动重新登录 |
| 提前刷新时间 | 过期前 5 分钟 | 避免 Token 过期导致请求失败 |

## 手动实现示例

如果你想手动控制 Token 管理：

```python
import httpx

# 1. 使用 API Key 获取 Token Pair
response = httpx.post(
    "http://localhost:8000/api/auth/token",
    json={"api_key": "your-api-key"}
)
data = response.json()
access_token = data["access_token"]
refresh_token = data["refresh_token"]

# 2. 使用 Access Token 调用 API
response = httpx.get(
    "http://localhost:8000/api/papers/by-date",
    headers={"Authorization": f"Bearer {access_token}"}
)
papers = response.json()

# 3. Access Token 过期后，使用 Refresh Token 刷新
response = httpx.post(
    "http://localhost:8000/api/auth/refresh",
    json={"refresh_token": refresh_token}
)
data = response.json()
access_token = data["access_token"]   # 新的 access token
refresh_token = data["refresh_token"]  # 新的 refresh token

# 4. Refresh Token 也过期了？重复步骤 1
```

## 常见问题

### Q: 为什么需要同时有 API Key 和 JWT Token？

A:
- **API Key**: 长期凭证，用于初始登录和重新登录
- **JWT Token**: 短期凭证，用于日常 API 调用
- **Refresh Token**: 中期凭证，用于获取新的 Access Token

这种设计更安全：如果 Access Token 泄露，影响只有 1 小时。

### Q: Refresh Token 过期后会发生什么？

A: 客户端会自动使用 API Key 重新登录，对用户透明。

### Q: 如何实现"记住我"功能？

A: 安全存储 API Key，客户端启动时自动登录。

### Q: 多个客户端可以同时使用吗？

A: 可以。每个客户端有独立的 Token Pair，互不影响。

### Q: 如何强制所有客户端重新登录？

A: 更换 `AUTH_JWT_SECRET`，所有现有 Token 将失效。

## 运行要求

```bash
pip install httpx
# 或
uv add httpx
```

## 更多信息

- [AUTH_REFRESH.md](../AUTH_REFRESH.md) - 完整的认证文档
- [AUTH.md](../AUTH.md) - 基础认证说明
