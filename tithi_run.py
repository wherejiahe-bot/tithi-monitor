"""
tithi_run.py — GitHub Actions 单次运行入口

由 GitHub Actions 每天北京时间 05:00（UTC 21:00 前一天）触发，单次执行后退出。
SMTP 配置从环境变量读取（GitHub Secrets 注入）：
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_SENDER, SMTP_RECIPIENT
"""

import sys, os, json, smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, os.path.dirname(__file__))

from tithi_calc import (
    get_tithi_number, get_tithi_name, get_tithi_start_end,
    get_moon_phase_exact_time, MONITORED_TITHIS,
    TZ_UTC, TZ_BEIJING,
)
from tithi_monitor import (
    build_email, load_state, save_state,
    already_sent, mark_sent, fmt_bj, RECIPIENT,
)

STATE_FILE = os.path.join(os.path.dirname(__file__), '.tithi_state.json')


def log(msg):
    now = datetime.now(TZ_BEIJING).strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}", flush=True)


def load_smtp_config():
    """优先读环境变量（GitHub Actions），本地 fallback 到 .smtp_config.json"""
    env_password = os.environ.get('SMTP_PASSWORD', '')
    if env_password:
        return {
            'host':     os.environ.get('SMTP_HOST', 'smtp.qq.com'),
            'port':     int(os.environ.get('SMTP_PORT', '587')),
            'user':     os.environ.get('SMTP_USER', ''),
            'password': env_password,
            'sender':   os.environ.get('SMTP_SENDER', os.environ.get('SMTP_USER', '')),
        }
    # 本地开发：读 .smtp_config.json
    cfg_file = os.path.join(os.path.dirname(__file__), '.smtp_config.json')
    if os.path.exists(cfg_file):
        with open(cfg_file) as f:
            return json.load(f)
    return {}


def send_via_smtp(cfg, to_addr, subject, body):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = cfg['sender']
    msg['To'] = to_addr
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    try:
        with smtplib.SMTP(cfg['host'], cfg['port'], timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg['user'], cfg['password'])
            server.sendmail(cfg['sender'], [to_addr], msg.as_string())
        log(f"✓ 邮件已发送: {subject}")
        return True
    except Exception as e:
        log(f"✗ SMTP 发送失败: {e}")
        return False


def scan_day_tithis(day_bj: datetime) -> list:
    """扫描给定北京时间日期（00:00 ~ 23:59）内出现的所有监控 Tithi"""
    day_start_bj = day_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_bj   = day_bj.replace(hour=23, minute=59, second=0, microsecond=0)
    day_start_utc = day_start_bj.astimezone(TZ_UTC)
    day_end_utc   = day_end_bj.astimezone(TZ_UTC)

    found = {}
    step = timedelta(minutes=30)
    t = day_start_utc
    while t <= day_end_utc + timedelta(minutes=30):
        tnum = get_tithi_number(t)
        if tnum in MONITORED_TITHIS and tnum not in found:
            start_bj, end_bj = get_tithi_start_end(t)
            if end_bj >= day_start_bj and start_bj <= day_end_bj:
                found[tnum] = {
                    'tithi_num':  tnum,
                    'tithi_name': get_tithi_name(tnum),
                    'start_bj':   start_bj,
                    'end_bj':     end_bj,
                    'sample_utc': t,
                }
        t += step
    return list(found.values())


def daily_check():
    now_utc = datetime.now(TZ_UTC)
    now_bj  = now_utc.astimezone(TZ_BEIJING)
    log(f"=== 每日检查 {now_bj.strftime('%Y-%m-%d %H:%M')} ===")

    cfg = load_smtp_config()
    if not cfg.get('password'):
        log("✗ SMTP 密码未配置，无法发送邮件。")
        sys.exit(1)

    # 收件人：优先环境变量，否则用 tithi_monitor 中的默认值
    recipient = os.environ.get('SMTP_RECIPIENT', RECIPIENT)

    tithis = scan_day_tithis(now_bj)
    if not tithis:
        log("今日无监控 Tithi，无需发送邮件。")
        return

    log(f"今日发现 {len(tithis)} 个监控 Tithi: {[t['tithi_name'] for t in tithis]}")

    state = load_state()
    for item in tithis:
        tnum       = item['tithi_num']
        start_bj   = item['start_bj']
        end_bj     = item['end_bj']
        tname      = item['tithi_name']
        sample_utc = item['sample_utc']

        if already_sent(state, tnum, start_bj):
            log(f"  [{tname}] 今日已发送，跳过。")
            continue

        subject, body = build_email(tnum, tname, start_bj, end_bj, sample_utc)
        sent = send_via_smtp(cfg, recipient, subject, body)
        if sent:
            mark_sent(state, tnum, start_bj)
            save_state(state)


if __name__ == '__main__':
    daily_check()
