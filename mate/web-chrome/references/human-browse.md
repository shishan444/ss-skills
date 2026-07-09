# 拟人化操作手册：GUI 交互 vs 程序化操作

> 加载时机：需要拟人交互（点击/滚动/翻页/表单）时（SKILL.md 端到端流程的"拟人浏览"阶段）

## 核心铁律：isTrusted=true

**所有"必须像人"的交互，走 CDP `Input` 协议（isTrusted=true），绝不走 JS `dispatchEvent`/`el.click()`（isTrusted=false）。**

这是反爬的硬规则（第一档规则5）。原因：
- CDP `Input.dispatchMouseEvent` 产生的事件 `isTrusted=true`，与真实用户手势无异
- JS `el.click()` / `dispatchEvent` 产生的事件 `isTrusted=false`，反爬一查即穿

web-chrome 的所有拟人操作通过 `human_behavior.py` → `cdp_client.py` → proxy `/input/*` 端点，全部走 CDP Input 协议。**永远不要用 `/click`（JS el.click）做需要像人的操作，用 `/input/click` 或 HumanBehavior。**

## 两种操作方式对比

| 维度 | 程序化方式 | GUI 拟人方式 |
|------|-----------|-------------|
| **实现** | 构造 URL 直接 navigate + eval 操作 DOM | HumanBehavior 鼠标轨迹 + 点击 + 滚动 |
| **速度** | 快 | 慢（贝塞尔曲线 + 泊松停顿） |
| **拟人度** | 低，像机器人 | 高，与人无异 |
| **反爬风险** | 高，易触发 | 低，确定性最高 |
| **适用** | 普通站点、公开内容、API 类页面 | 反爬平台、登录态操作、需翻页/展开 |

## 决策：何时用哪种

```
目标站点是否已知反爬？（查 site-patterns 经验）
   │
   ├─ 是（小红书/微信/推特/知乎等）→ 直接 GUI 拟人
   │
   └─ 否 / 未知 → 先程序化探测
         │
         ├─ 成功 → 继续程序化（高效）
         │
         └─ 受阻（拦截/空结果/验证码）→ 降级 GUI 拟人
               │
               ├─ 成功 → 记录经验："此站点需 GUI"
               └─ 仍失败 → 换 locale/UA 或告知用户需登录
```

**判断要点**：
- 程序化是**首选探测手段**（快），受阻时 GUI 是**可靠兜底**（稳）
- 一次真实 GUI 交互能观察站点实际行为（URL 模式、必需参数、跳转逻辑），为后续程序化操作提供依据
- 已知反爬平台不要浪费时间程序化试探，直接 GUI

## 程序化操作（高效探测）

适合：公开内容、API 类页面、无反爬的普通站点。

```bash
# 直接构造 URL 导航
curl -s "http://localhost:3457/navigate?target=ID&url=URL"

# eval 提取 DOM（纯读取，不触发交互）
curl -s -X POST "http://localhost:3457/eval?target=ID" -d 'document.querySelector("article").innerText'

# eval 提取链接
curl -s -X POST "http://localhost:3457/eval?target=ID" -d '[...document.querySelectorAll("a")].map(a=>a.href).filter(h=>h.includes("xxx"))'
```

**程序化的局限**：
- `el.click()` 是 JS 点击，isTrusted=false，反爬站点会识别
- 构造的 URL 可能缺失会话参数（token、上下文），被拦截或返回错误页
- 短时间密集程序化操作易触发频率风控

## GUI 拟人操作（可靠兜底）

适合：反爬平台、登录态操作、需翻页/展开/加载更多。

### 鼠标移动 + 点击（HumanBehavior.move_and_click）

```python
from human_behavior import HumanBehavior
from cdp_client import CdpClient

client = CdpClient()
human = HumanBehavior(client)

# 对 CSS 选择器元素做人类点击（自动取包围盒 + 贝塞尔轨迹 + 随机落点）
success, err = human.click_selector(target_id, 'button.load-more')

# 或直接指定坐标（已有包围盒时）
human.move_and_click(target_id, x=400, y=300, w=120, h=36)
```

**拟人技术细节**（来自 deep-research-search 实战验证）：
- `bezier_points`：三次贝塞尔曲线，10-20 个轨迹点，非直线
- `random_landing`：落点在目标中心 60% 区域随机，非精确点击
- `poisson_sleep`：指数分布间隔（0.25-4s），节奏自然
- 随机起点：每次从不同位置开始移动

### 人类化滚动（HumanBehavior.human_scroll）

```python
# 分 2-4 段滚动 + 随机停顿，触发懒加载
human.human_scroll(target_id, direction='down', total=2400)
```

### 翻页 / 加载更多

```python
# 模拟人类点击"下一页"/"加载更多"
human.click_selector(target_id, 'a.next-page')
# 或
human.click_selector(target_id, 'button.load-more')
```

## 拟人节奏的要点

- **不要过快**：每个操作间留泊松停顿（HumanBehavior 内置），避免固定节奏
- **不要过整齐**：滚动分段数随机（2-4），鼠标轨迹点数随机（10-20）
- **避免精确重复**：落点随机化，不要每次点同一像素
- **观察反馈再行动**：点击后等页面响应（waitForLoad / poisson_sleep），不要立即下一步

## 多语言/locale 模拟

部分站点根据 locale/UA 返回不同内容或触发不同反爬策略：

```python
client.set_locale(target_id, locale='zh-CN', accept_language='zh-CN,zh;q=0.9',
                  user_agent='Mozilla/5.0 ...')
# 或英文环境
client.set_locale(target_id, locale='en-US', accept_language='en-US,en;q=0.9')
```

切换 locale/UA 是拦截时的降级策略之一（见 experience.md）。

## 何时该停下（拦截信号）

操作过程中若 `intercept_detector.py` 检测到拦截信号（CAPTCHA/LOGIN_WALL/CONTENT_GONE/EMPTY_SERP/FINGERPRINT），**立即停止**，不要在同一方式上反复重试。按 experience.md 的拦截强制流程处理。
