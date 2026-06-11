"""
send_email_helper.py — 由 tithi_monitor.py 通过 subprocess 调用。

从 stdin 读取 JSON: {"to": "...", "subject": "...", "body": "..."}
通过 MorphMind Gmail API 发送邮件。
成功退出码 0，失败退出码 1。

注意：此脚本依赖 /workspace/.platform/gmail_token.json 中的 OAuth token，
由平台注入。若 token 不存在，使用 requests 调用平台内部 API。
"""

import sys
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def main():
    raw = sys.stdin.read().strip()
    data = json.loads(raw)
    to_addr = data['to']
    subject = data['subject']
    body = data['body']

    # 尝试通过平台内置 Gmail relay 发送
    # 平台在 /workspace/.platform/ 下提供凭据
    platform_dir = '/workspace/.platform'

    # 方法1: 检查平台 Gmail relay 配置
    relay_config = os.path.join(platform_dir, 'gmail_relay.json')
    if os.path.exists(relay_config):
        with open(relay_config) as f:
            cfg = json.load(f)
        _send_via_smtp(cfg, to_addr, subject, body)
        return

    # 方法2: 通过平台 HTTP API
    api_token_file = os.path.join(platform_dir, 'api_token')
    if os.path.exists(api_token_file):
        with open(api_token_file) as f:
            token = f.read().strip()
        _send_via_api(token, to_addr, subject, body)
        return

    # 方法3: 直接 import MorphMind SDK（若在平台 Python 环境中）
    try:
        _send_via_sdk(to_addr, subject, body)
        return
    except Exception as e:
        print(f"SDK 发送失败: {e}", file=sys.stderr)

    print("无可用发送方式", file=sys.stderr)
    sys.exit(1)


def _send_via_smtp(cfg: dict, to_addr: str, subject: str, body: str):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = cfg.get('from', 'noreply@morphmind.ai')
    msg['To'] = to_addr
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    with smtplib.SMTP(cfg['host'], cfg.get('port', 587)) as server:
        server.starttls()
        server.login(cfg['user'], cfg['password'])
        server.sendmail(msg['From'], [to_addr], msg.as_string())
    print("SMTP 发送成功")


def _send_via_api(token: str, to_addr: str, subject: str, body: str):
    import urllib.request
    payload = json.dumps({
        'to': to_addr,
        'subject': subject,
        'body': body
    }).encode()
    req = urllib.request.Request(
        'https://api.morphmind.ai/v1/gmail/send',
        data=payload,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
        if result.get('success'):
            print("API 发送成功")
        else:
            raise Exception(f"API 返回错误: {result}")


def _send_via_sdk(to_addr: str, subject: str, body: str):
    """通过平台内置工具直接调用 Gmail send"""
    # 这个路径在 cron 环境中通常不可用；作为最后备选
    raise NotImplementedError("SDK path not available in cron context")


if __name__ == '__main__':
    main()
