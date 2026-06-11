## Context
- 三个核心文件：tithi_calc.py（天文计算）、tithi_monitor.py（邮件构建）、tithi_scheduler.py（调度入口）
- SMTP 配置（QQ 邮箱账号+授权码）需作为 GitHub Secrets 存储，不能明文提交
- 目标：每天北京时间 05:00 自动触发，检测当天 Tithi 并按需发邮件
- 现无 Git 仓库，需新建

## Plan

### 1. 改写入口脚本（适配 Actions 无调度器模式）
新增 `tithi_run.py`：单次运行版本，直接调用 daily_check()，适合 Actions 触发。
→ tithi_run.py

*Considered: 直接改 tithi_scheduler.py（破坏本地兼容性，拒绝）*

### 2. 创建 GitHub Actions workflow 文件
路径：`.github/workflows/tithi_daily.yml`
- schedule: `cron: '0 21 * * *'`（UTC 21:00 = 北京时间 05:00）
- workflow_dispatch：手动触发，方便测试
- 步骤：checkout → install deps → python tithi_run.py
- SMTP 配置从 Secrets 注入环境变量
→ .github/workflows/tithi_daily.yml

*Considered: Docker 容器（过重，拒绝）*

**Assumption:** SMTP_PASSWORD 等敏感信息由脚本从 Secrets 读取，用户在 GitHub 仓库 Settings 手动填入

### 3. 创建 .gitignore 和 requirements.txt
- .gitignore：排除 .smtp_config.json、tithi_state.json、*.log
- requirements.txt：pyswisseph、ephem、apscheduler
→ .gitignore, requirements.txt

### 4. 初始化 Git 仓库并推送到 GitHub（私有）
git init → git add → git commit → gh repo create → git push
仓库名：tithi-monitor（私有，保护邮箱配置）
→ GitHub 远程仓库

**Critical:** .smtp_config.json 在 .gitignore 中，确认排除后才 push

### 5. 通过 gh secret set 注入 SMTP 配置
SMTP_HOST、SMTP_PORT、SMTP_USER、SMTP_PASSWORD、SMTP_SENDER、SMTP_RECIPIENT
→ GitHub Secrets 已配置

### 6. 手动触发一次 workflow 验证
gh workflow run → 查看日志 → 确认邮件收到
→ 端到端验证通过

## Risks
- pyswisseph 在 ubuntu-latest 编译可能需要系统库 — workflow 中加 apt-get install libswe-dev
- UTC 换算：cron `0 21 * * *` = 北京时间 05:00，正确
- GitHub Actions 免费额度：每月 2000 分钟，每天一次约 2 分钟，全年约 730 分钟，远不超限
