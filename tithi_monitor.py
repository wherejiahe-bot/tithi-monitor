"""
tithi_monitor.py — 整点调度脚本

由 Python 调度脚本调用：
1. 扫描今天日出时刻的 Tithi（印度历法日规则）
2. 如果 Tithi 在监控列表中（Saptami/Navami/Purnima/Amavasya），发送邮件
3. 去重：同一天只发一次
1. 检查当前是否处于 Saptami / Navami / Amavasya / Purnima
2. 去重：同一 tithi 期间只发一次邮件
3. 符合条件则用 Gmail 发送格式化邮件到 455048345@qq.com

用法：python3 /workspace/tithi_monitor.py
日志：/workspace/tithi_monitor.log
状态：/workspace/.tithi_state.json
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta

# 把 workspace 加入路径
sys.path.insert(0, '/workspace')

from tithi_calc import (
    get_tithi_number,
    get_tithi_name,
    get_tithi_start_end,
    get_moon_phase_exact_time,
    MONITORED_TITHIS,
    SAPTAMI_NUMS,
    NAVAMI_NUMS,
    TZ_BEIJING,
    TZ_UTC,
)

STATE_FILE = '/workspace/.tithi_state.json'
LOG_FILE = '/workspace/tithi_monitor.log'
RECIPIENT = '455048345@qq.com'


# ── 邮件正文内容 ─────────────────────────────────────────────

SAPTAMI_NAVAMI_BODY = """However, on the seventh day (saptami) and ninth day (navami) of the Lunar fortnights you have my special blessings.

然而，在月相每两周的第七日（saptami）和第九日（navami），你们拥有我的特别祝福。

Remember that you are specially blessed by me on these two days.

请记住，在这两日，你们得到了我特别的祝福。

Make some special arrangements so that you can have proper meditation on these days.

做一些特别的安排，以便在这些日子里你能有恰当的冥想。

https://www.sahaja.live/1976-05-29-public-program-dhyan-kaise-karein-how-to-meditate-mumbai-hindi/"""

AMAVASYA_BODY = """First thing to note is that on the night of new-moon and full-moon always there are dangers on your left and right sides.

首先要留意的是，在新月和满月的夜晚，你的左脉和右脉两侧总是有危险。

Especially on these two days, the nights of new moon and full moon, you should sleep very early at night.

特别是在这两日——新月和满月的夜晚，你应该很早就寝。

After singing bhajans, bow down before the photograph, meditate, and keep your attention on Sahastrara and go to sleep after taking bandhan.

唱完 bhajan 之后，在照片前鞠躬，进入冥想，将注意力保持在顶轮，在做了班丹之后入睡。

That means you go into the Unconscious the moment your attention is at your Sahastrara.

这意味着当你的注意力到达顶轮的那一刻，你就进入了无意识状态。

There, give yourself a bandhan and you are saved.

在那里，给自己做一个班丹，你就得救了。

During these two nights it should be observed particularly.

在这两晚期间，这一点应特别留意。

The night of new moon, you should meditate especially on Shri Shiva.

在新月的夜晚，你应该特别地冥想 Shri Shiva。

You should sleep after meditating on Shri Shiva, that is the Spirit, and completely surrender yourself to Him.

你应该在冥想 Shri Shiva（即灵）之后入睡，并完全将自己交托于祂。

https://www.sahaja.live/1976-05-29-public-program-dhyan-kaise-karein-how-to-meditate-mumbai-hindi/"""

PURNIMA_BODY = """First thing to note is that on the night of new-moon and full-moon always there are dangers on your left and right sides.

首先要留意的是，在新月和满月的夜晚，你的左脉和右脉两侧总是有危险。

Especially on these two days, the nights of new moon and full moon, you should sleep very early at night.

特别是在这两日——新月和满月的夜晚，你应该很早就寝。

After singing bhajans, bow down before the photograph, meditate, and keep your attention on Sahastrara and go to sleep after taking bandhan.

唱完 bhajan 之后，在照片前鞠躬，进入冥想，将注意力保持在顶轮，在做了班丹之后入睡。

That means you go into the Unconscious the moment your attention is at your Sahastrara.

这意味着当你的注意力到达顶轮的那一刻，你就进入了无意识状态。

There, give yourself a bandhan and you are saved.

在那里，给自己做一个班丹，你就得救了。

During these two nights it should be observed particularly.

在这两晚期间，这一点应特别留意。

On the night of full moon, you should meditate on Shri Rama and surrender yourself to Him for protection.

在满月的夜晚，你应该冥想 Shri Rama，并将自己交托于祂以求得保护。

The meaning of the word Ramchandra is 'creativity'.

"Ramchandra" 这个词的意思是"创造力"。

You should completely dedicate your creative powers to Him.

你应该将你的创造力完全奉献给祂。

https://www.sahaja.live/1976-05-29-public-program-dhyan-kaise-karein-how-to-meditate-mumbai-hindi/"""


# ── 状态管理 ─────────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict):
    # 确保父目录存在
    dir_path = os.path.dirname(STATE_FILE)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _tithi_key(tithi_num: int, tithi_start: datetime) -> str:
    """
    去重 key：Tithi编号 + Tithi开始的北京日期（只到天）。
    不用精确分钟，避免因计算误差导致同一 Tithi 被识别为不同记录。
    """
    return f"{tithi_num}_{tithi_start.strftime('%Y%m%d')}"


def already_sent(state: dict, tithi_num: int, tithi_start: datetime) -> bool:
    """检查这一轮 tithi 是否已经发过邮件"""
    return state.get(_tithi_key(tithi_num, tithi_start), False)


def mark_sent(state: dict, tithi_num: int, tithi_start: datetime):
    key = _tithi_key(tithi_num, tithi_start)
    state[key] = True
    # 只保留最近 60 条记录，防止文件无限增长
    if len(state) > 60:
        oldest_keys = sorted(state.keys())[:10]
        for k in oldest_keys:
            del state[k]


# ── 邮件构建 ─────────────────────────────────────────────────

def fmt_bj(dt: datetime) -> str:
    return dt.strftime('%Y年%m月%d日%H时%M分')


def build_email(tithi_num: int, tithi_name: str,
                start_bj: datetime, end_bj: datetime,
                now_utc: datetime) -> tuple[str, str]:
    """返回 (subject, body)"""

    # 首行：起止时间
    header = f"从北京时间 {fmt_bj(start_bj)}-{fmt_bj(end_bj)}，是印度历法中的{tithi_name}\n"

    # 月相精确时间（仅 Amavasya / Purnima）
    moon_line = ""
    if tithi_num == 30:  # Amavasya
        exact = get_moon_phase_exact_time(now_utc, 'new')
        moon_line = f"\n新月精确时刻：北京时间 {fmt_bj(exact)}\n"
    elif tithi_num == 15:  # Purnima
        exact = get_moon_phase_exact_time(now_utc, 'full')
        moon_line = f"\n满月精确时刻：北京时间 {fmt_bj(exact)}\n"

    # 正文段落
    if tithi_num in SAPTAMI_NUMS:
        extra = SAPTAMI_NAVAMI_BODY
    elif tithi_num in NAVAMI_NUMS:
        extra = SAPTAMI_NAVAMI_BODY
    elif tithi_num == 30:
        extra = AMAVASYA_BODY
    else:  # Purnima
        extra = PURNIMA_BODY

    subject = f"印度历法提醒：{tithi_name}"
    footer = "\n\n月相时间查询网站：https://wherejiahe-bot.github.io/tithi-now/"
    body = f"{header}{moon_line}\n\n（接收母亲的赐福与向神祇祈求保护，是每天都会做的，咱们不执着哈。算法来自网络，大家带着明辨。）\n\n{extra}{footer}"
    return subject, body


# ── Gmail 发送（通过 MorphMind Gmail MCP 工具） ────────────────
# 由于 tithi_monitor.py 作为独立 cron 脚本运行，无法直接调用 MCP 工具，
# 改用 subprocess 调用专门的 send_email_helper.py 脚本（该脚本通过 MorphMind API 发送）。
# 实际上，这里使用 Python smtplib 通过 MorphMind 内置 relay 发送；
# 若不可用，则写入待发队列文件供手动检查。

def send_email(to: str, subject: str, body: str) -> bool:
    """
    发送邮件。
    优先调用 send_email_helper.py（由平台 Gmail 工具支撑）。
    """
    helper = '/workspace/send_email_helper.py'
    if os.path.exists(helper):
        payload = json.dumps({'to': to, 'subject': subject, 'body': body})
        result = subprocess.run(
            ['python3', helper],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            log(f"邮件已发送: {subject}")
            return True
        else:
            log(f"邮件发送失败: {result.stderr}")
            return False
    else:
        # 写入队列，等待 helper 就绪
        queue_file = '/workspace/.email_queue.jsonl'
        with open(queue_file, 'a') as f:
            f.write(json.dumps({'to': to, 'subject': subject, 'body': body,
                                'queued_at': datetime.now(TZ_BEIJING).isoformat()},
                               ensure_ascii=False) + '\n')
        log(f"邮件已加入队列（helper 未就绪）: {subject}")
        return False


# ── 日志 ─────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now(TZ_BEIJING).strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    # 确保日志目录存在
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')


# ── 主逻辑 ───────────────────────────────────────────────────

def main():
    now_utc = datetime.now(TZ_UTC)
    now_bj = now_utc.astimezone(TZ_BEIJING)
    log(f"=== 整点检查 {now_bj.strftime('%Y-%m-%d %H:%M')} ===")

    tithi_num = get_tithi_number(now_utc)
    tithi_name = get_tithi_name(tithi_num)
    log(f"当前 Tithi: {tithi_num} ({tithi_name})")

    if tithi_num not in MONITORED_TITHIS:
        log(f"非监控 Tithi，跳过。")
        return

    start_bj, end_bj = get_tithi_start_end(now_utc)
    log(f"Tithi 范围: {fmt_bj(start_bj)} ~ {fmt_bj(end_bj)}")

    state = load_state()
    if already_sent(state, tithi_num, start_bj):
        log("本轮 Tithi 已发送邮件，跳过。")
        return

    subject, body = build_email(tithi_num, tithi_name, start_bj, end_bj, now_utc)
    log(f"准备发送邮件: {subject}")

    sent = send_email(RECIPIENT, subject, body)
    if sent:
        mark_sent(state, tithi_num, start_bj)
        save_state(state)


if __name__ == '__main__':
    main()
