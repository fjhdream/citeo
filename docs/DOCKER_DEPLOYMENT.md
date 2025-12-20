# Docker 部署指南

本文档说明如何使用预构建的 Docker 镜像部署 Citeo。

## 自动构建

每次推送到 `master` 分支或创建版本标签时，GitHub Actions 会自动构建并发布 Docker 镜像到 GitHub Container Registry (ghcr.io)。

### 镜像标签策略

- `latest` - 最新的 master 分支构建
- `vX.Y.Z` - 版本标签（如 `v1.0.0`）
- `master-<sha>` - 特定 commit SHA

## 部署步骤

### 1. 准备配置文件

创建 `.env` 文件并配置必要的环境变量：

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env，必填项：
nano .env
```

**必填配置：**

```bash
# OpenAI API
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx

# Telegram（如使用）
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=-1001234567890

# API 配置（用于深度分析链接）
API_BASE_URL=https://your-domain.com  # 或 http://your-public-ip:8000
SIGNED_URL_SECRET=<至少32字符的随机字符串>

# 认证（可选但推荐）
AUTH_API_KEY=<你的API密钥>
```

**生成随机密钥的方法：**

```bash
# 生成 SIGNED_URL_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 生成 AUTH_API_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. 创建 docker-compose.yml

项目已包含 `docker-compose.yml`，默认使用 `ghcr.io/carota/citeo:latest` 镜像。

**验证配置：**

```bash
cat docker-compose.yml | grep image
# 应该看到: image: ghcr.io/carota/citeo:latest
```

### 3. 登录 GitHub Container Registry（如果镜像是私有的）

如果仓库是私有的，需要先登录 GHCR：

```bash
# 创建 GitHub Personal Access Token (PAT):
# 1. 访问 https://github.com/settings/tokens
# 2. 点击 "Generate new token (classic)"
# 3. 勾选 "read:packages" 权限
# 4. 生成并复制 token

# 登录 GHCR
echo "<YOUR_PAT>" | docker login ghcr.io -u <YOUR_GITHUB_USERNAME> --password-stdin
```

**如果是公开仓库，可以跳过此步骤。**

### 4. 启动服务

```bash
# 拉取最新镜像并启动
docker-compose pull
docker-compose up -d

# 查看日志
docker-compose logs -f citeo

# 检查健康状态
curl http://localhost:8000/api/health
```

### 5. 更新镜像

当有新版本发布时：

```bash
# 拉取最新镜像
docker-compose pull

# 重启服务
docker-compose up -d

# 清理旧镜像
docker image prune -f
```

## 使用特定版本

如果想使用特定版本而不是 `latest`：

```yaml
# docker-compose.yml
services:
  citeo:
    image: ghcr.io/carota/citeo:v1.0.0  # 使用特定版本
```

## 数据持久化

数据存储在 `./data` 目录：

```bash
# 查看数据目录
ls -lh data/

# 备份数据库
cp data/citeo.db data/citeo.db.backup
```

## 故障排查

### 1. 无法拉取镜像

**问题：** `Error response from daemon: pull access denied`

**解决：**
- 确认仓库是公开的，或已登录 GHCR
- 检查镜像名称是否正确（区分大小写）

### 2. 容器启动失败

**查看详细日志：**

```bash
docker-compose logs citeo
```

**常见原因：**
- `.env` 文件缺少必填配置
- 端口 8000 已被占用
- 数据目录权限问题

### 3. API 无法访问

**检查容器状态：**

```bash
docker-compose ps
```

**检查端口映射：**

```bash
docker-compose port citeo 8000
```

### 4. 深度分析链接无法点击

**检查配置：**

```bash
# 运行诊断脚本
docker-compose exec citeo python check_config.py
```

**常见问题：**
- `API_BASE_URL` 未配置或使用了 `localhost`
- `SIGNED_URL_SECRET` 未配置

## 生产环境建议

1. **使用反向代理**（Nginx/Caddy）：

```nginx
# Nginx 配置示例
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

2. **启用 HTTPS**（使用 Let's Encrypt）

3. **配置日志轮转**（已在 docker-compose.yml 中配置）

4. **监控和告警**：

```bash
# 添加健康检查监控
curl -f http://localhost:8000/api/health || echo "Service down!"
```

5. **备份策略**：

```bash
# 定期备份脚本
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
cp data/citeo.db backups/citeo_${DATE}.db
find backups/ -name "citeo_*.db" -mtime +30 -delete
```

## 环境变量完整列表

参考 `src/citeo/config/settings.py` 查看所有可配置选项。

**关键配置：**

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `OPENAI_API_KEY` | ✅ | - | OpenAI API 密钥 |
| `TELEGRAM_BOT_TOKEN` | ⚠️ | - | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | ⚠️ | - | Telegram Chat ID |
| `API_BASE_URL` | 推荐 | `http://localhost:8000` | 公网可访问的 API 地址 |
| `SIGNED_URL_SECRET` | 推荐 | - | 签名 URL 密钥（32+ 字符）|
| `AUTH_API_KEY` | 推荐 | - | API 认证密钥 |
| `MIN_NOTIFICATION_SCORE` | ❌ | `8.0` | 推送评分阈值（1-10）|
| `DAILY_FETCH_HOUR` | ❌ | `8` | 定时任务小时（0-23）|

⚠️ 表示至少需要配置一个通知渠道（Telegram 或 Feishu）

## 联系方式

如有问题，请：
1. 查看日志：`docker-compose logs -f citeo`
2. 提交 Issue：https://github.com/carota/citeo/issues
