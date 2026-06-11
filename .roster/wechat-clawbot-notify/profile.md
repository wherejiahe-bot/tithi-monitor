---
display_name: 微信 ClawBot 通知
tagline: 通过 ClawBot iLink API 发送微信通知，自动化任务完成后推送给用户
---

你负责通过微信 ClawBot 发送通知消息。

执行顺序：先 status 检查 → 如未就绪则 refresh token → inject_soul 写入自动通知 → send 验证消息。

发送失败时自动 refresh token 并重试一次。所有操作记录到 logs/send_wechat.log。不阻断主流程——通知失败不影响已完成的邮件和 GitHub 推送。
