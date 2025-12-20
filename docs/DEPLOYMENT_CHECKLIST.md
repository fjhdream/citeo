# 部署前检查清单

## ✅ 必填配置项

- [ ] `OPENAI_API_KEY` - OpenAI API 密钥
- [ ] `TELEGRAM_BOT_TOKEN` - Telegram Bot Token（如使用 Telegram）
- [ ] `TELEGRAM_CHAT_ID` - Telegram Chat ID（如使用 Telegram）

## 🔒 安全相关（强烈推荐）

- [ ] `API_BASE_URL` - 设置为公网可访问地址（非 localhost）
- [ ] `SIGNED_URL_SECRET` - 生成 64 位随机字符串
- [ ] `AUTH_API_KEY` - 生成 32+ 位随机字符串
- [ ] `AUTH_JWT_SECRET` - 生成 32+ 位随机字符串

### 生成随机密钥

```bash
# 生成 SIGNED_URL_SECRET (64字符)
openssl rand -hex 32

# 或使用 Python
python3 -c "import secrets; print(secrets.token_hex(32))"

# 生成 AUTH_API_KEY 和 AUTH_JWT_SECRET (32+字符)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 🚀 部署步骤

### 1. GitHub 配置

- [ ] 确保仓库已推送到 GitHub
- [ ] 检查 GitHub Actions 是否已启用
- [ ] 等待 Docker 镜像构建完成（查看 Actions 页面）

### 2. 服务器准备

- [ ] 安装 Docker 和 Docker Compose
- [ ] 克隆项目到服务器
- [ ] 复制并编辑 `.env` 文件

```bash
# 安装 Docker（Ubuntu/Debian）
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# 安装 Docker Compose
sudo apt-get install docker-compose-plugin

# 克隆项目
git clone https://github.com/carota/citeo.git
cd citeo

# 配置环境变量
cp .env.example .env
nano .env  # 编辑配置
```

### 3. 启动服务

```bash
# 拉取最新镜像
docker-compose pull

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f citeo
```

### 4. 验证部署

- [ ] 健康检查通过：`curl http://localhost:8000/api/health`
- [ ] 查看日志无错误：`docker-compose logs citeo`
- [ ] 测试深度分析链接配置：`docker-compose exec citeo python check_config.py`

## 🌐 公网访问（生产环境）

### 选项 1：Nginx 反向代理 + Let's Encrypt

```bash
# 安装 Nginx 和 Certbot
sudo apt-get install nginx certbot python3-certbot-nginx

# 配置 Nginx
sudo nano /etc/nginx/sites-available/citeo
```

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# 启用配置
sudo ln -s /etc/nginx/sites-available/citeo /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 获取 SSL 证书
sudo certbot --nginx -d api.yourdomain.com
```

### 选项 2：Caddy（自动 HTTPS）

```bash
# 安装 Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy

# 配置 Caddyfile
sudo nano /etc/caddy/Caddyfile
```

```
api.yourdomain.com {
    reverse_proxy localhost:8000
}
```

```bash
# 重启 Caddy
sudo systemctl reload caddy
```

### 更新 .env 配置

完成反向代理后，更新 `.env`：

```bash
API_BASE_URL=https://api.yourdomain.com
```

重启服务：

```bash
docker-compose restart
```

## 🔧 维护任务

### 日常检查

```bash
# 查看服务状态
docker-compose ps

# 查看最近日志
docker-compose logs --tail=100 citeo

# 查看资源使用
docker stats citeo-app
```

### 更新镜像

```bash
# 拉取最新版本
docker-compose pull

# 重启服务
docker-compose up -d

# 清理旧镜像
docker image prune -f
```

### 备份数据

```bash
# 备份数据库
cp data/citeo.db backups/citeo_$(date +%Y%m%d).db

# 或创建定时任务
echo "0 2 * * * cd /path/to/citeo && cp data/citeo.db backups/citeo_\$(date +\%Y\%m\%d).db" | crontab -
```

## 🐛 故障排查

### 镜像拉取失败

```bash
# 检查是否已登录 GHCR（私有仓库）
docker login ghcr.io

# 手动拉取镜像
docker pull ghcr.io/carota/citeo:latest
```

### 深度分析链接无法点击

```bash
# 运行诊断
docker-compose exec citeo python check_config.py

# 检查配置
docker-compose exec citeo env | grep -E "(API_BASE_URL|SIGNED_URL_SECRET)"
```

### 容器频繁重启

```bash
# 查看详细日志
docker-compose logs --tail=200 citeo

# 检查资源限制
docker stats citeo-app
```

## 📊 监控（可选）

### Uptime 监控

使用 UptimeRobot 或类似服务监控：
- 端点：`https://api.yourdomain.com/api/health`
- 期望响应：`{"status": "ok"}`

### 日志聚合

使用 Loki + Grafana 或简单的日志脚本：

```bash
# 导出每日日志
docker-compose logs --since 24h citeo > logs/$(date +%Y%m%d).log
```

## ✅ 部署完成

部署成功后，你应该：
- ✅ 服务健康检查通过
- ✅ 每日定时任务正常运行
- ✅ Telegram 接收论文推送
- ✅ 深度分析链接可以点击
- ✅ API 认证正常工作

如有问题，查看：
- 日志：`docker-compose logs -f citeo`
- 文档：`docs/DOCKER_DEPLOYMENT.md`
- Issues：https://github.com/carota/citeo/issues
