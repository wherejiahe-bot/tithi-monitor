"""
tithi_scheduler.py — 每日北京时间 05:00 预测当天 Tithi 并发送邮件

逻辑：
- 每天 05:00（北京时间）运行一次
- 扫描当天 00:00 ~ 23:59（北京时间）内出现的所有监控 Tithi
- 每个 Tithi 单独发一封邮件（格式与原来相同）
- 去重：同一自然日同一 Tithi 只发一次

启动: nohup python3 /workspace/tithi_scheduler.py >> /workspace/tithi_monitor.log 2>&1 &
"""

import sys, os, json, smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, '/workspace')

from tithi_calc import (
    get_tithi_number, get_tithi_name, get_tithi_start_end,
    get_moon_phase_exact_time, MONITORED_TITHIS,
    TZ_UTC, TZ_BEIJING, _utc_to_jd, _moon_sun_diff
)
from tithi_monitor import (
    build_email, load_state, save_state,
    already_sent, mark_sent, fmt_bj, log, RECIPIENT
)

SMTP_CONFIG_FILE = '/workspace/.smtp_config.json'


def load_smtp_config():
    if os.path.exists(SMTP_CONFIG_FILE):
        with open(SMTP_CONFIG_FILE) as f:
            return json.load(f)
    host = os.environ.get('SMTP_HOST', 'smtp.qq.com')
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER', '')
    password = os.environ.get('SMTP_PASSWORD', '')
    sender = os.environ.get('SMTP_SENDER', user)
    return {'host': host, 'port': port, 'user': user, 'password': password, 'sender': sender}


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
        log(f"✓ 邮件已发送 via SMTP: {subject}")
        return True
    except Exception as e:
        log(f"✗ SMTP 发送失败: {e}")
        return False


def scan_day_tithis(day_bj: datetime) -> list[dict]:
    """
    扫描给定北京时间日期（00:00 ~ 23:59）内出现的所有监控 Tithi。
    返回列表，每项: {tithi_num, tithi_name, start_bj, end_bj, sample_utc}
    """
    # 当天北京时间 00:00 和 23:59
    day_start_bj = day_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_bj = day_bj.replace(hour=23, minute=59, second=0, microsecond=0)

    day_start_utc = day_start_bj.astimezone(TZ_UTC)
    day_end_utc = day_end_bj.astimezone(TZ_UTC)

    found = {}  # tithi_num → {tithi_num, tithi_name, start_bj, end_bj, sample_utc}

    # 每30分钟采样一次，覆盖全天
    step = timedelta(minutes=30)
    t = day_start_utc
    while t <= day_end_utc + timedelta(minutes=30):
        tnum = get_tithi_number(t)
        if tnum in MONITORED_TITHIS and tnum not in found:
            start_bj, end_bj = get_tithi_start_end(t)
            # 确认该 Tithi 与当天有重叠
            if end_bj >= day_start_bj and start_bj <= day_end_bj:
                found[tnum] = {
                    'tithi_num': tnum,
                    'tithi_name': get_tithi_name(tnum),
                    'start_bj': start_bj,
                    'end_bj': end_bj,
                    'sample_utc': t,
                }
        t += step

    return list(found.values())


def daily_check():
    """每日 05:00 北京时间执行：扫描当天并发送邮件"""
    now_utc = datetime.now(TZ_UTC)
    now_bj = now_utc.astimezone(TZ_BEIJING)
    log(f"=== 每日检查 {now_bj.strftime('%Y-%m-%d %H:%M')} ===")

    cfg = load_smtp_config()
    if not cfg.get('password'):
        log("✗ SMTP 密码未配置，无法发送邮件。")
        return

    tithis = scan_day_tithis(now_bj)
    if not tithis:
        log("今日无监控 Tithi，跳过。")
        return

    log(f"今日发现 {len(tithis)} 个监控 Tithi: {[t['tithi_name'] for t in tithis]}")

    state = load_state()
    for item in tithis:
        tnum = item['tithi_num']
        start_bj = item['start_bj']
        end_bj = item['end_bj']
        tname = item['tithi_name']
        sample_utc = item['sample_utc']

        if already_sent(state, tnum, start_bj):
            log(f"  [{tname}] 今日已发送，跳过。")
            continue

        subject, body = build_email(tnum, tname, start_bj, end_bj, sample_utc)
        sent = send_via_smtp(cfg, RECIPIENT, subject, body)
        if sent:
            mark_sent(state, tnum, start_bj)
            save_state(state)


def main():
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        log("✗ apscheduler 未安装，请运行: pip install apscheduler")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone='Asia/Shanghai')
    # 每天北京时间 05:00 运行
    scheduler.add_job(daily_check, 'cron', hour=5, minute=0)
    log("调度器启动：每天北京时间 05:00 检查当日 Tithi...")

    # 启动时立即运行一次（方便验证）
    daily_check()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log("调度器已停止。")


if __name__ == '__main__':
    main()
