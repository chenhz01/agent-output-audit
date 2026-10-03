# agent-output-audit

**给 AI 产出做体检的规则引擎** · MIT License · Python 3.8+ · 零依赖

> 检查 AI 写出来的东西：日报、HTML 交付件、代码、口播稿、商品 listing、音乐元数据……
> 换个垂类只需放一个目录，**引擎一行不改**。

---

## 为什么做这个

现在几乎所有「AI 内容质检」都押在**模型判断**上——用一个模型点评另一个模型的输出。
问题是：**判断不可复现、不可审计、阈值靠感觉**。

所以本项目只做**能写成 `if` 的确定性检查**，并且严守一条：

> **BLOCK 只给「机器能 100% 判定一定错」的硬伤；
> WARN 只给「需要人判断」的。绝不用 WARN 冒充 BLOCK。**

用 WARN 冒充 BLOCK，一次就会让人对整个工具失去信任。

---

## 快速开始

```bash
python aoa.py list                                    # 列出规则集
python aoa.py run <ruleset> <file>                    # 终端报告
python aoa.py run <ruleset> <file> --format sarif     # GitHub Code Scanning
python aoa.py run <ruleset> <file> --format json      # 机读
python aoa.py run <ruleset> <file> --format junit     # CI 通用
```

被检文件可以是 `.json`（已适配结构），也可以直接是 `.md` / `.html` / `.py`。

**退出码**：`0` 通过 · `1` 有 BLOCK · `2` 只有 WARN · **`3` 规则集/引擎故障**

> 退出码 3 必须与 1/2 严格区分：「规则坏了」和「内容有问题」是两回事。
> 混同的后果是调用方把 bug 当提示忽略。

---

## 规则集（46 条）

| 规则集 | 条数 | 领域 |
|---|---:|---|
| **`ai-output`** | 9 | **通用体检 —— 项目本体** |
| `music` | 20 | 音乐发行前合规（AI 标识 / 发行商政策 / 著作权链 / 歌词客观特征） |
| `ecommerce` | 10 | 跨境电商 listing（标题长度 / 五点索引阈值 / 广告误导表述） |
| `shortvideo` | 7 | 短视频口播（广告法红线 / 医疗宣称 / 时间轴交叉对齐） |

`ai-output` 检查的是**产出本身**：
占位符残留 · 无源数字 · 绝对化表述 · 凭据泄漏 · PII · 结构完整性 · 篇幅异常。

---

## 架构：四层

```
aoa.py                    统一入口
engine/
  engine.py               ① 引擎 —— 不认识任何业务
  adapters.py             ③ 适配器 —— md/html/code → 统一结构
  schema.py               ③ 统一中间结构 agent_output/1.0
  report.py               ④ 报告 —— text/json/sarif/junit
rulesets/
  ai-output/ music/ ecommerce/ shortvideo/     ② 规则集（可插拔）
```

| 加什么 | 改哪里 | 碰引擎吗 |
|---|---|---|
| 新垂类 | `rulesets/x/ruleset.py` | 不碰 |
| 新产出形态（PDF/邮件/diff） | `engine/adapters.py` 加 `@register` | 不碰 |

**为什么这样分**：规则一周能抄，框架抄不动。
所以把「可抄的」和「难抄的」物理隔开。详见 `docs/ARCHITECTURE.md`。

---

## 引擎的四道护栏（全部实测有效）

| 护栏 | 触发时 | 退出码 |
|---|---|---|
| 零规则守卫 | 规则集产出 0 条规则 | 3 |
| `validate()` | policy 的 check 字段对不上 | 3（点名规则 ID） |
| ERROR 单列 | 检查器抛异常 | 3 |
| `confidence_floor` | 指标覆盖率不足 | FAIL→WARN 降权 |

> 这四道都是被真实 bug 逼出来的：它们分别拦下过
> 「0 条规则报通过」「键名不匹配静默失效」「异常被降级成提示掩盖规则失效」
> 「覆盖率 27% 却照样告警」。

---

## 质量：假阳性实测

对一份真实 HTML 交付件跑「无源数字」检查：

| 版本 | 命中数 | 根因 |
|---|---:|---|
| 初版（整页去标签） | 67 | UI 数值卡片、页头元信息被当成论断 |
| + 噪声剥离 | 60 | 日期 / commit sha / 版本号被当统计数字 |
| + 语义标签提取 | **8** | 只取 `p/li/td/th/blockquote` 正文 |

**假阳性率 41% → 11%**，残留 8 条经人工核对全为真问题。

---

## 扩展：写一个规则集

```python
# rulesets/<你的>/ruleset.py
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from engine.engine import Rule

POLICY = {'version': '1.0.0', 'display': '我的垂类',
          'rules': {
              'MY-001': {'desc': '我的检查', 'severity': 'BLOCK',
                         'enforce_type': 'platform_technical',
                         'check': 'my_check', 'source': '出处链接'}}}

def my_check(target, rule, ctx):
    return ('PASS', '没问题')     # 或 FAIL / WARN / INFO / SKIP

CHECKERS = {'my_check': my_check}  # ⚠ 键名必须与 check 字段【字面一致】

class RuleSet:
    name, display, version = 'mine', POLICY['display'], POLICY['version']
    @classmethod
    def load(cls):
        return [Rule(rid, r['desc'], r.get('severity', 'WARN'),
                     CHECKERS[r['check']],
                     **{k: v for k, v in r.items()
                        if k not in ('check', 'severity', 'desc')})
                for rid, r in POLICY['rules'].items()]
    @classmethod
    def validate(cls):
        return [rid for rid, r in POLICY['rules'].items()
                if r['check'] not in CHECKERS]
```

> ⚠ 那个「字面一致」的坑踩过 4 次，每次都表现为「0 条规则」。
> `validate()` 会替你抓住，但写的时候请别剥/加前缀。

---

## 诚实边界

- 只做**形式与可追溯性**检查，**不判断内容对错**。
- 「无源数字」不等于「数据是假的」，只等于「**读者无法验证**」。
- 规则依据为政策原文与司法文书，**非法律意见**。
- 部分阈值（语速、无源比例、篇幅）**未在真实语料上标定**，已在各规则集的
  `needs_pro_review` 中标出，需按实际语料重新标定。
- 建议正式商用前由专业人士复核一次规则集。

## 安全

```bash
python scripts/scan_secrets.py .    # push 前敏感字段扫描
```
