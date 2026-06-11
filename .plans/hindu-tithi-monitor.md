## Context
- 目标：每整点检查当前是否处于 Saptami / Navami / Amavasya / Purnima 四个 tithi 之一
- 若是，发送邮件到 455048345@qq.com，说明该 tithi 的北京时间起止范围
- Amavasya / Purnima 需额外给出月相精确时刻（新月/满月的精确时间）
- 运行于云端 workspace，使用 cron 实现整点调度

## Plan

### 1. 安装依赖和计算核心模块
使用 pyswisseph + Lagrange 插值计算 tithi 起止时间；ephem 计算新月/满月精确时刻。
→ /workspace/tithi_calc.py

*Considered: drik-panchanga（需 git clone，依赖复杂，overkill），astropy（不含 tithi 逻辑，redundant）*

**Assumption:** Tithi 边界用 pyswisseph 计算；所有时间输出转为北京时间（UTC+8）

### 2. 主调度脚本（含邮件逻辑）
整点 cron 触发：检查当前 tithi → 去重判断 → 若符合条件则构建邮件内容并用 Gmail 发送。
→ /workspace/tithi_monitor.py（含去重状态文件 /workspace/.tithi_state.json）

*Considered: APScheduler（进程级，容器重启后丢失，fragile），cron（系统级，持久，稳定）*

### 3. 注册 cron 任务
写入 crontab：每小时整点运行 tithi_monitor.py，日志写入 /workspace/tithi_monitor.log

## Risks
- 云容器重启后 cron 丢失 — 可重新执行 setup 步骤恢复
- 同一 tithi 跨越多个整点 → 状态文件记录已发送的 tithi+日期，防止重复邮件
- Gmail 发送账号是 MorphMind 平台账号（非 QQ 邮箱），收件人是 455048345@qq.com
