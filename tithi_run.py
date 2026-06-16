"""
tithi_run.py — GitHub Actions 单次运行入口

由 GitHub Actions 每天北京时间 05:00（UTC 21:00 前一天）触发，单次执行后退出。
SMTP 配置从环境变量读取（GitHub Secrets 注入）：
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_SENDER, SMTP_RECIPIENT

核心逻辑（印度历法日规则）：
- 印度历法的一天（Ahoratra）从日出开始，到次日日出结束
- 日出瞬间处于哪个 Tithi，这一整天就命名为那个 Tithi
- 不管这个 Tithi 是否在日出后几分钟就结束
"""

import sys, os, json, smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, os.path.dirname(__file__))

from tithi_calc import (
    get_tithi_number, get_tithi_name, get_tithi_start_end,
    get_moon_phase_exact_time, get_sunrise_for_tithi,
    MONITORED_TITHIS, TZ_UTC, TZ_BEIJING,
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


def get_today_tithi(day_bj: datetime) -> dict:
    """
    根据印度历法日规则（Ahoratra）：
    - 一天从日出到次日日出
    - 日出瞬间处于哪个 Tithi，这天就叫哪个 Tithi 名
    
    返回 dict 或 None：
      {
        'tithi_num': 30,
        'tithi_name': 'Amavasya',
        'start_bj': 日出时的 Tithi 开始时间,
        'end_bj': 日出时的 Tithi 结束时间,
      }
    """
    bj_date = day_bj.date()
    
    # 直接计算当天日出
    sunrise_bj = get_sunrise_bj(bj_date.year, bj_date.month, bj_date.day)
    sunrise_utc = sunrise_bj.astimezone(TZ_UTC)
    
    # 日出瞬间的 Tithi 就是这天的名字
    tnum = get_tithi_number(sunrise_utc)
    
    if tnum not in MONITORED_TITHIS:
        return None
    
    tithi_start, tithi_end = get_tithi_start_end(sunrise_utc)
    tname = get_tithi_name(tnum)
    
    return {
        'tithi_num':  tnum,
        'tithi_name': tname,
        'start_bj':   tithi_start,
        'end_bj':     tithi_end,
        'sample_utc': sunrise_utc,
    }


def daily_check():
    now_utc = datetime.now(TZ_UTC)
    now_bj  = now_utc.astimezone(TZ_BEIJING)
    log(f"=== 每日检查 {now_bj.strftime('%Y-%m-%d %H:%M')} ===")

    cfg = load_smtp_config()
    if not cfg.get('password'):
        log("✗ SMTP 密码未配置，无法发送邮件。")
        sys.exit(1)

    recipient = os.environ.get('SMTP_RECIPIENT', RECIPIENT)

    # 使用日出规则确定今天的 Tithi
    today_tithi = get_today_tithi(now_bj)
    if not today_tithi:
        log("今日日出时的 Tithi 不在监控列表中，无需发送邮件。")
        return

    tnum  = today_tithi['tithi_num']
    tname = today_tithi['tithi_name']
    start_bj = today_tithi['start_bj']
    end_bj = today_tithi['end_bj']
    sample_utc = today_tithi['sample_utc']

    log(f"日出 Tithi: {tnum} ({tname})")
    log(f"日出日期: {now_bj.date()}")
    log(f"Tithi 范围: {fmt_bj(start_bj)} ~ {fmt_bj(end_bj)}")

    state = load_state()

    if already_sent(state, tnum, start_bj):
        log(f"  [{tname}] 今日已发送，跳过。")
        return

    subject, body = build_email(tnum, tname, start_bj, end_bj, sample_utc)
    sent = send_via_smtp(cfg, recipient, subject, body)
    if sent:
        mark_sent(state, tnum, start_bj)
        save_state(state)


if __name__ == '__main__':
    daily_check()
