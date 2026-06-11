#!/bin/bash
# 确保 tithi_scheduler.py 在运行，不在则拉起
if ! pgrep -f tithi_scheduler.py > /dev/null; then
    pip install pyswisseph ephem apscheduler -q 2>/dev/null
    cd /workspace
    python3 -c "
import subprocess
p = subprocess.Popen(
    ['python3', 'tithi_scheduler.py'],
    stdout=open('tithi_monitor.log','a'),
    stderr=subprocess.STDOUT,
    start_new_session=True
)
print(f'已启动 PID: {p.pid}')
"
else
    echo "进程已在运行: $(pgrep -f tithi_scheduler.py)"
fi
