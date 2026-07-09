# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

如果你发现了安全漏洞，请通过以下方式报告：

1. **不要** 在公开 Issue 中报告
2. 发送邮件至：请通过 GitHub Private Security Advisory 功能提交
3. 或者通过 GitHub Discussions 私信

我们会在 48 小时内确认收到报告，并在 7 天内给出初步评估。

## 安全实践

本项目采取以下安全措施：

- 对话历史使用 AES-256 加密存储
- JWT Token 用于认证，有有效期限制
- AI API Key 不暴露在客户端
- 环境变量隔离敏感配置
