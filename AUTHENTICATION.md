# Citeo API 认证指南

## 快速开始

### 1. 配置

在 `.env` 文件中添加：

```bash
# 必需配置
AUTH_API_KEY=your-secure-api-key-min-16-chars
AUTH_JWT_SECRET=your-jwt-secret-at-least-32-chars

# 可选配置
AUTH_JWT_ACCESS_TOKEN_EXPIRY_MINUTES=60  # Access token 过期时间（分钟）
AUTH_JWT_REFRESH_TOKEN_EXPIRY_DAYS=7      # Refresh token 过期时间（天）
RATE_LIMIT_ANALYZE_REQUESTS=10            # /analyze 端点速率限制
```

### 2. 获取 Token

```bash
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "your-api-key"}'
```

响应：
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 3. 使用 Token 访问 API

```bash
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/papers/by-date
```

## 认证方式

### 方式 1: API Key（直接认证）

```bash
# Header 方式（推荐）
curl -H "X-API-Key: your-api-key" \
  http://localhost:8000/api/papers/by-date

# Query 参数方式（仅用于测试）
curl "http://localhost:8000/api/papers/by-date?api_key=your-api-key"
```

### 方式 2: JWT Token（推荐）

**Token 类型：**
- **Access Token**: 1小时有效，用于 API 调用
- **Refresh Token**: 7天有效，用于获取新的 Access Token

**工作流程：**
```
API Key → /auth/token → Access Token (1h) + Refresh Token (7d)
                          ↓
                    使用 Access Token 访问 API
                          ↓
                    Token 过期前刷新
                          ↓
                    /auth/refresh → 新的 Token Pair
```

## API 端点

### POST /api/auth/token
使用 API Key 获取 Token Pair

**请求：**
```json
{"api_key": "your-api-key"}
```

**响应：**
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_in": 3600
}
```

### POST /api/auth/refresh
刷新 Access Token

**请求：**
```json
{"refresh_token": "your-refresh-token"}
```

**响应：**
```json
{
  "access_token": "...",    // 新的 access token
  "refresh_token": "...",   // 新的 refresh token
  "expires_in": 3600
}
```

### POST /api/auth/revoke
撤销 Refresh Token（登出）

**请求：**
```json
{"token": "your-refresh-token"}
```

**响应：**
```json
{"message": "Token revoked successfully"}
```

### GET /api/auth/health
认证服务健康检查

**响应：**
```json
{"message": "Authentication service is healthy. Active tokens: 5"}
```

## 受保护的端点

| 端点 | 认证 | 速率限制 |
|------|------|----------|
| `GET /api/health` | ❌ 无需 | ❌ 无 |
| `POST /api/papers/{id}/analyze` | ✅ 需要 | ✅ 10/分钟 |
| `GET /api/papers/{id}/analysis` | ✅ 需要 | ❌ 无 |
| `GET /api/papers/by-date` | ✅ 需要 | ❌ 无 |
| `GET /api/papers/{id}` | ✅ 需要 | ❌ 无 |

## 客户端实现

### Python 智能客户端

使用 `examples/smart_client.py`：

```python
from examples.smart_client import CiteoClient

# 初始化
client = CiteoClient("http://localhost:8000", "your-api-key")

# 使用（自动处理 Token 管理）
papers = client.get_papers_by_date()
result = client.analyze_paper("2512.14709")

# 登出
client.logout()
```

### 手动实现

```python
import httpx
from datetime import datetime, timedelta

class SimpleClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None

    def login(self):
        """获取 Token"""
        response = httpx.post(
            f"{self.base_url}/api/auth/token",
            json={"api_key": self.api_key}
        )
        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.expires_at = datetime.now() + timedelta(seconds=data["expires_in"])

    def refresh(self):
        """刷新 Token"""
        response = httpx.post(
            f"{self.base_url}/api/auth/refresh",
            json={"refresh_token": self.refresh_token}
        )
        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.expires_at = datetime.now() + timedelta(seconds=data["expires_in"])

    def ensure_token(self):
        """确保 Token 有效"""
        if not self.access_token:
            self.login()
        elif datetime.now() >= self.expires_at - timedelta(minutes=5):
            try:
                self.refresh()
            except:
                self.login()

    def api_call(self, endpoint):
        """调用 API"""
        self.ensure_token()
        response = httpx.get(
            f"{self.base_url}{endpoint}",
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        return response.json()
```

## Token 生命周期

```
第 1-7 天: 正常使用
  ├─ 每小时自动刷新 Access Token
  └─ Refresh Token 保持有效

第 8 天: Refresh Token 过期
  ├─ 刷新失败（401 错误）
  └─ 自动使用 API Key 重新登录
```

## 常见问题

### Q: Token 过期后会发生什么？
A: Access Token 过期后返回 401 错误，客户端应使用 Refresh Token 刷新。Refresh Token 也过期时，使用 API Key 重新登录。

### Q: 如何生成安全的密钥？
A:
```bash
# API Key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# JWT Secret
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Q: 可以同时使用 API Key 和 JWT Token 吗？
A: 可以。推荐流程：使用 API Key 获取 JWT Token，然后用 JWT Token 访问 API。

### Q: 如何实现"记住我"功能？
A: 安全存储 Refresh Token（加密），客户端启动时自动刷新。

### Q: 多设备如何处理？
A: 每个设备有独立的 Token Pair，互不影响。

### Q: 如何强制所有客户端重新登录？
A: 更换 `AUTH_JWT_SECRET`，所有现有 Token 将失效。

## 安全建议

1. **密钥管理**
   - API Key 和 JWT Secret 至少 32 字符
   - 不要将密钥提交到版本控制
   - 定期轮换密钥

2. **Token 存储**
   - API Key: 环境变量/配置文件
   - Access Token: 内存（不持久化）
   - Refresh Token: 安全存储（加密）

3. **传输安全**
   - 生产环境必须使用 HTTPS
   - 不要在 URL 中传递 Token

4. **监控**
   - 记录认证失败次数
   - 监控速率限制触发
   - 异常访问模式告警

## 配置调优

根据场景调整过期时间：

```bash
# 高安全场景（金融、医疗）
AUTH_JWT_ACCESS_TOKEN_EXPIRY_MINUTES=15
AUTH_JWT_REFRESH_TOKEN_EXPIRY_DAYS=1

# 普通场景（推荐）
AUTH_JWT_ACCESS_TOKEN_EXPIRY_MINUTES=60
AUTH_JWT_REFRESH_TOKEN_EXPIRY_DAYS=7

# 内部工具（便利优先）
AUTH_JWT_ACCESS_TOKEN_EXPIRY_MINUTES=240
AUTH_JWT_REFRESH_TOKEN_EXPIRY_DAYS=30
```

## 错误处理

| 状态码 | 说明 | 处理方式 |
|--------|------|----------|
| 401 | 未认证或 Token 无效 | 刷新或重新登录 |
| 429 | 速率限制 | 等待 Retry-After 秒后重试 |
| 500 | 服务器错误 | 检查配置和日志 |

## 禁用认证（仅开发）

```bash
AUTH_ENABLED=false
```

**警告：** 生产环境不要禁用认证！

## 相关文件

- `examples/smart_client.py` - 智能客户端实现
- `examples/README.md` - 使用示例
- `.env.example` - 配置示例
