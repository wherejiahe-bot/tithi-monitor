"""
tithi_calc.py — 印度历法 Tithi 计算核心模块

Tithi 定义：月亮与太阳黄经差每增加 12° 为一个 Tithi（共 30 个/月）
- Tithi 1~15: Shukla Paksha（白月，月亮由新到满）
- Tithi 16~30: Krishna Paksha（黑月，月亮由满到新）
- Tithi 15 = Purnima（满月）
- Tithi 30 = Amavasya（新月）
- Tithi 7 和 22 = Saptami（白月第7 / 黑月第7）
- Tithi 9 和 24 = Navami（白月第9 / 黑月第9）

使用 pyswisseph 高精度计算；ephem 给出新月/满月精确时刻。
"""

import swisseph as swe
import ephem
from datetime import datetime, timedelta, timezone

# 北京时间 UTC+8
TZ_BEIJING = timezone(timedelta(hours=8))
# UTC
TZ_UTC = timezone.utc


def _utc_to_jd(dt_utc: datetime) -> float:
    """UTC datetime → 儒略日"""
    return swe.julday(
        dt_utc.year, dt_utc.month, dt_utc.day,
        dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    )


def _moon_sun_diff(jd: float) -> float:
    """给定儒略日，返回 (月亮黄经 - 太阳黄经) mod 360，单位度"""
    moon_long = swe.calc_ut(jd, swe.MOON)[0][0]
    sun_long = swe.calc_ut(jd, swe.SUN)[0][0]
    return (moon_long - sun_long) % 360.0


def get_tithi_number(dt_utc: datetime) -> int:
    """
    返回给定 UTC 时刻的 Tithi 编号（1~30）
    公式：ceil((moon_long - sun_long) / 12)，若结果为 0 则取 30
    """
    diff = _moon_sun_diff(_utc_to_jd(dt_utc))
    tithi = int(diff / 12.0) + 1
    if tithi > 30:
        tithi = 30
    return tithi


def get_tithi_start_end(dt_utc: datetime) -> tuple[datetime, datetime]:
    """
    给定 UTC 时刻，返回当前 Tithi 的（开始时间, 结束时间），均为北京时间 datetime。
    使用二分法搜索边界，精度 ~30秒。
    """
    jd_now = _utc_to_jd(dt_utc)
    current_tithi = get_tithi_number(dt_utc)

    # 当前 Tithi 对应的角度范围
    target_start_deg = (current_tithi - 1) * 12.0  # 例如 Tithi 7 → 72°
    target_end_deg = current_tithi * 12.0            # 例如 Tithi 7 → 84°

    # 搜索"开始时间"：往前找 (moon-sun) 恰好等于 target_start_deg 的时刻
    # 往前搜索最多 2 天
    jd_start = _find_boundary(jd_now, target_start_deg, direction=-1)
    # 搜索"结束时间"：往后找 (moon-sun) 恰好等于 target_end_deg 的时刻
    jd_end = _find_boundary(jd_now, target_end_deg, direction=1)

    start_bj = _jd_to_beijing(jd_start)
    end_bj = _jd_to_beijing(jd_end)
    return start_bj, end_bj


def _find_boundary(jd_ref: float, target_deg: float, direction: int,
                   max_days: float = 2.5, precision_sec: float = 5) -> float:
    """
    月日差（moon-sun）单调递增（约 0.5°/小时）。
    direction=+1：向未来搜索（找 Tithi 结束，diff 增大至 target）
    direction=-1：向过去搜索（找 Tithi 开始，diff 减小至 target）

    粗搜步长 ~10 分钟，发现跨越后二分精化至 precision_sec 秒。
    处理 360°→0° 回绕（Amavasya→Purnima 边界附近）。
    """
    STEP_DAYS = 10.0 / 1440.0  # 10分钟

    def wrapped_diff(jd):
        """返回 (moon-sun) mod 360，但在搜索目标附近展开，避免回绕跳变"""
        d = _moon_sun_diff(jd)
        return d

    def unwrap_pair(a, b):
        """处理 a~360°, b~0° 的跨越情况，把 b 展开为 b+360"""
        if abs(a - b) > 180:
            if b < a:
                b += 360
            else:
                a += 360
        return a, b

    jd = jd_ref
    prev_jd = jd
    prev_d = wrapped_diff(jd)

    n_steps = int(max_days / STEP_DAYS) + 1
    for _ in range(n_steps):
        jd += direction * STEP_DAYS
        curr_d = wrapped_diff(jd)

        # 展开处理回绕
        a, b = unwrap_pair(prev_d, curr_d)

        # 展开后的 target（如果 a 或 b 被展开超过 360，target 也要同步）
        t = target_deg
        if a > 360 or b > 360:
            # 区间在 [360, 372] 之类——target 若是小值需加 360
            if t < 180:
                t += 360

        # 检测跨越：direction=+1 时 a→b 递增，找 a<=t<b
        #           direction=-1 时 a→b 递减，找 b<=t<a（注意 a,b 此时 a>b）
        if direction > 0:
            crossed = (a <= t < b)
        else:
            crossed = (b <= t < a) if a >= b else (a <= t < b)

        if crossed:
            # 二分精化
            lo, hi = (min(prev_jd, jd), max(prev_jd, jd))
            prec_jd = precision_sec / 86400.0
            for _ in range(40):
                if (hi - lo) < prec_jd:
                    break
                mid = (lo + hi) / 2
                mid_a = wrapped_diff(lo)
                mid_b = wrapped_diff(mid)
                ma, mb = unwrap_pair(mid_a, mid_b)
                mt = target_deg
                if ma > 360 or mb > 360:
                    if mt < 180:
                        mt += 360
                if direction > 0:
                    if ma <= mt < mb:
                        hi = mid
                    else:
                        lo = mid
                else:
                    if mb <= mt < ma if ma >= mb else ma <= mt < mb:
                        hi = mid
                    else:
                        lo = mid
            return (lo + hi) / 2

        prev_jd = jd
        prev_d = curr_d

    return jd_ref


def _jd_to_beijing(jd: float) -> datetime:
    """儒略日 → 北京时间 datetime"""
    y, mo, d, h = swe.revjul(jd)
    total_seconds = h * 3600
    hour = int(total_seconds // 3600)
    minute = int((total_seconds % 3600) // 60)
    second = int(total_seconds % 60)
    dt_utc = datetime(y, mo, d, hour, minute, second, tzinfo=TZ_UTC)
    return dt_utc.astimezone(TZ_BEIJING)


def get_moon_phase_exact_time(dt_utc: datetime, phase: str) -> datetime:
    """
    返回距离 dt_utc 最近的新月（phase='new'）或满月（phase='full'）的精确北京时间。
    使用 ephem 库计算。
    """
    d = ephem.Date(dt_utc.strftime('%Y/%m/%d %H:%M:%S'))
    if phase == 'new':
        prev_t = ephem.previous_new_moon(d)
        next_t = ephem.next_new_moon(d)
    else:
        prev_t = ephem.previous_full_moon(d)
        next_t = ephem.next_full_moon(d)

    # 选择最近的（前一个或后一个）
    prev_dt = ephem.Date(prev_t).datetime().replace(tzinfo=TZ_UTC)
    next_dt = ephem.Date(next_t).datetime().replace(tzinfo=TZ_UTC)

    diff_prev = abs((dt_utc.replace(tzinfo=TZ_UTC) - prev_dt).total_seconds())
    diff_next = abs((next_dt - dt_utc.replace(tzinfo=TZ_UTC)).total_seconds())

    closest = prev_dt if diff_prev < diff_next else next_dt
    return closest.astimezone(TZ_BEIJING)


def get_tithi_name(tithi_num: int) -> str:
    """返回 tithi 编号对应的名称"""
    names = {
        7: "Saptami (Shukla Paksha, 7th)",
        9: "Navami (Shukla Paksha, 9th)",
        15: "Purnima",
        22: "Saptami (Krishna Paksha, 7th)",
        24: "Navami (Krishna Paksha, 9th)",
        30: "Amavasya",
    }
    return names.get(tithi_num, f"Tithi {tithi_num}")


# 需要监控的 Tithi 编号集合
MONITORED_TITHIS = {7, 9, 15, 22, 24, 30}

# Tithi 类型分类
SAPTAMI_NUMS = {7, 22}
NAVAMI_NUMS = {9, 24}


if __name__ == "__main__":
    # 快速自测
    now_utc = datetime.now(TZ_UTC)
    now_bj = now_utc.astimezone(TZ_BEIJING)
    t = get_tithi_number(now_utc)
    start, end = get_tithi_start_end(now_utc)
    print(f"当前北京时间: {now_bj.strftime('%Y年%m月%d日 %H:%M')}")
    print(f"当前 Tithi: {t} ({get_tithi_name(t)})")
    print(f"Tithi 开始: {start.strftime('%Y年%m月%d日 %H:%M')}")
    print(f"Tithi 结束: {end.strftime('%Y年%m月%d日 %H:%M')}")
    if t == 15:
        exact = get_moon_phase_exact_time(now_utc, 'full')
        print(f"满月精确时间: {exact.strftime('%Y年%m月%d日 %H:%M')}")
    elif t == 30:
        exact = get_moon_phase_exact_time(now_utc, 'new')
        print(f"新月精确时间: {exact.strftime('%Y年%m月%d日 %H:%M')}")
