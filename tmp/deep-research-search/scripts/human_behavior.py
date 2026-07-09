"""人类行为模拟（HumanBehaviorService）

基于 CDP Input domain（isTrusted=true）模拟人类操作：
  - 贝塞尔轨迹鼠标移动（非直线、带弧度）
  - 落点随机化（目标中心区域，非精确点击）
  - 泊松分布间隔（替代固定 sleep，节奏自然）
  - 两类点击：SERP 翻页 + 内容交互（展开全文 / 加载更多）

设计要点：所有交互走 CDP Input 协议（proxy /input/*），不经过 JS dispatchEvent
（后者 isTrusted=false，反爬一查即穿）。
"""

import json
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_client import CdpClient


def poisson_sleep(lam=0.9, cap=(0.25, 4.0)):
    """泊松过程的间隔（指数分布），模拟人类操作节奏。lam 越大节奏越快。"""
    interval = random.expovariate(lam)
    return max(cap[0], min(cap[1], interval))


def bezier_points(p0, p1, p2, p3, n=15):
    """三次贝塞尔曲线，返回 n+1 个点 [(x,y),...]。"""
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = mt ** 3 * p0[0] + 3 * mt ** 2 * t * p1[0] + 3 * mt * t ** 2 * p2[0] + t ** 3 * p3[0]
        y = mt ** 3 * p0[1] + 3 * mt ** 2 * t * p1[1] + 3 * mt * t ** 2 * p2[1] + t ** 3 * p3[1]
        pts.append((int(x), int(y)))
    return pts


def random_landing(cx, cy, w, h, ratio=0.6):
    """在目标中心 ratio 比例区域内随机落点。"""
    dx = (random.random() - 0.5) * w * ratio
    dy = (random.random() - 0.5) * h * ratio
    return int(cx + dx), int(cy + dy)


class HumanBehavior:
    """封装 CDP Input 的人类化操作。"""

    def __init__(self, client: CdpClient):
        self.c = client

    def move_and_click(self, target_id, x, y, w=120, h=36):
        """人类化移动 + 点击：随机起点 → 贝塞尔曲线 → 目标随机落点 → 点击。"""
        sx, sy = random.randint(10, 800), random.randint(10, 600)
        tx, ty = random_landing(x, y, w, h)
        # 两个控制点随机偏移，制造弧线而非直线
        c1 = (sx + (tx - sx) * 0.3 + random.randint(-60, 60),
              sy + (ty - sy) * 0.3 + random.randint(-60, 60))
        c2 = (sx + (tx - sx) * 0.7 + random.randint(-60, 60),
              sy + (ty - sy) * 0.7 + random.randint(-60, 60))
        pts = bezier_points((sx, sy), c1, c2, (tx, ty), n=random.randint(10, 20))
        self.c.mouse_move(target_id, pts)
        poisson_sleep(1.0)
        self.c.mouse_click(target_id, tx, ty)
        poisson_sleep()
        return (tx, ty)

    def click_selector(self, target_id, selector):
        """对 CSS 选择器元素做人类点击：先 eval 取包围盒，再 move_and_click。
        返回 (success, error)。"""
        js = ("(function(){var el=document.querySelector(%s);"
              "if(!el)return null;var r=el.getBoundingClientRect();"
              "return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,h:r.height});})()"
              % json.dumps(selector))
        val, err = self.c.eval(target_id, js)
        if err or not val:
            return False, f"未找到元素或取坐标失败: {err}"
        try:
            box = json.loads(val)
        except Exception as e:
            return False, f"坐标解析失败: {e}"
        if not box or box.get('w', 0) == 0:
            return False, "元素不可见（宽度为0）"
        self.move_and_click(target_id, box['x'], box['y'], box['w'], box['h'])
        return True, None

    def human_scroll(self, target_id, direction='down', total=2400):
        """人类化滚动：协议级 synthesizeScrollGesture + 分段 + 随机停顿。"""
        steps = random.randint(2, 4)
        per = max(300, total // steps)
        for _ in range(steps):
            self.c.scroll(target_id, direction, per)
            poisson_sleep(1.5)
