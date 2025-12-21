# 网页查看功能使用说明

## 功能概述

现在当您在 Telegram 或飞书收到深度分析推送后，除了 Abstract 和 PDF 链接外，还会有一个「完整查看」按钮/链接，点击后可以在浏览器中查看格式化的深度分析报告。

## 特性

✨ **公共访问**: 无需登录，链接可以分享给任何人
🔄 **永久有效**: 不是一次性链接，可以重复访问和收藏
📱 **响应式设计**: 自动适配手机和电脑屏幕
🌓 **深色模式**: 自动适配系统深色模式偏好
🎨 **简洁现代**: Medium/Notion 风格的阅读体验
🔒 **速率限制**: IP 限制 100 次/分钟，防止滥用

## 链接格式

```
{API_BASE_URL}/api/view/{arxiv_id}
```

例如:
- 本地开发: `http://localhost:8000/api/view/2512.15117`
- 生产环境: `https://your-domain.com/api/view/2512.15117`

## 配置

在 `.env` 文件中设置：

```bash
# API 基础 URL（用于生成通知链接）
API_BASE_URL=http://localhost:8000

# 网页查看功能开关（可选，默认开启）
ENABLE_WEB_VIEW=true

# 速率限制（可选，默认 100 次/分钟）
WEB_VIEW_RATE_LIMIT=100
```

## 通知变化

### Telegram

深度分析消息现在包含三个链接：

```
🔗 Abstract | PDF | 完整查看
```

### 飞书

深度分析卡片现在包含三个按钮：

```
[📄 Abstract] [📥 PDF] [🌐 完整查看]
```

## 页面内容

网页查看页面包含：

1. **论文信息**
   - 中文标题（如有）
   - 原始英文标题
   - arXiv ID
   - 作者列表
   - 发布日期
   - 分类标签

2. **深度分析内容**
   - 完整的 Markdown 格式化内容
   - 支持标题、列表、代码块、表格等
   - 自动转换为美观的 HTML

3. **快捷链接**
   - arXiv Abstract 链接
   - PDF 下载链接

## 安全性

- ✅ arXiv ID 格式验证（防止注入攻击）
- ✅ IP 速率限制（防止 DoS 攻击）
- ✅ HTML 自动转义（防止 XSS 攻击）
- ✅ 无论文列表端点（防止爬虫遍历）

## 测试

运行测试脚本验证功能：

```bash
uv run python scripts/test_web_view.py
```

## 示例

假设您收到了关于论文 `2512.15117` 的深度分析推送：

1. 点击 Telegram 中的「完整查看」链接
2. 浏览器打开 `http://localhost:8000/api/view/2512.15117`
3. 看到格式化的深度分析报告
4. 可以将链接分享给同事或收藏

## 故障排除

### 404 Not Found

- 确认论文已经进行了深度分析（`deep_analysis` 字段不为空）
- 确认 arXiv ID 格式正确

### 429 Too Many Requests

- 您的 IP 在 1 分钟内访问超过了 100 次
- 等待 1 分钟后重试
- 如需调整限制，修改 `.env` 中的 `WEB_VIEW_RATE_LIMIT`

### 链接无法访问

- 确认 `API_BASE_URL` 配置正确
- 确认 API 服务正在运行（`uv run citeo`）
- 检查防火墙设置

## 文件变更

本次实现涉及以下文件：

- ✅ `pyproject.toml` - 添加 jinja2 和 markdown 依赖
- ✅ `src/citeo/api/templates/analysis_view.html` - 新增：网页模板
- ✅ `src/citeo/api/routes.py` - 新增：`GET /view/{arxiv_id}` 端点
- ✅ `src/citeo/notifiers/telegram.py` - 更新：添加完整查看链接
- ✅ `src/citeo/notifiers/feishu.py` - 更新：添加完整查看按钮
- ✅ `src/citeo/config/settings.py` - 新增：网页查看配置
- ✅ `scripts/test_web_view.py` - 新增：测试脚本
