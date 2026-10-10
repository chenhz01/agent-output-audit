# agent-output-audit

**给 AI 产出做体检的规则引擎** · MIT License · Python 3.8+ · 零依赖

> 检查 AI 写出来的东西：日报、HTML 交付件、代码、口播稿、商品 listing、音乐元数据……
> 换个垂类只需放一个目录，**引擎不用为垂类让步**（引擎会自己演进，但那不是垂类逼的）。

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

**JSON 输出带 `verdicts` 三态档位**（对标
[cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill)
的机读语义）：`confirmed`（BLOCK，机器确定）/ `needs_validation`（WARN 与
NEEDS_VALIDATION）/ `pass`（查过没查出）/ `not_covered`（SKIP，未覆盖）。
判定与档位解耦——同一份结果，人类读 text，CI 读 sarif/junit，程序读 json。

**v2.0.0 三态判定 + 两大可信机制**（均已实现并带测试夹具）：

1. **`NEEDS_VALIDATION` 独立判定档** —— 规则「无法完成判定但知道卡在哪」时
   返回此档：有确切的未决事实、不带 severity。与 WARN 的区别：WARN 是
   「判定完成、需人确认」，NV 是「根本没判」。实例：listing 未声明
   `marketplace` 时，标题上限（美国 75 / 欧洲 200）判不了——工具不再默认按
   美国站猜（旧默认双向出错：误杀欧洲卖家的合法长标题 / 放过美国站超限标题）。
   退出码契约 0/1/2/3 不变，NV 归 2 档但计数单列。
2. **独立复核闸（发现者≠验证者）** —— 规则判 FAIL 时可附证据
   `[(行号, 片段), …]`，引擎拿原文**独立核实**每条；行号越界或片段不在该行
   → 整个 FAIL 降为 NEEDS_VALIDATION。夹具：`tests/verify_gate/`
   （LIAR 假证据被降档 / HONEST 真证据保持 FAIL）。
3. **coverage ledger** —— `aoa.py run <rs> <file> --ledger <json>`：
   记录每次运行的逐规则判定，下次自动对比「新增 FAIL N 条 / 已解决 N 条」，
   CI 增量降噪。原子写。

> 对标诚实边界：本项目的「独立复核」是**单进程内用原文独立验证证据**，
> 与 Cloudflare 的多 agent 物理隔离复核仍有代差；多 agent 通道在实现前不宣称。

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

**降噪效果：无源断言 67 → 8 条，残留率 12%（8/67）。**
这 8 条人工逐条核对，**8 条全为真问题** —— 所以降噪后**假阳性 0 条**。

> ⚠ 口径更正（v1.0.1）：早期版本这里写的是「假阳性率 41% → 11%」，**两个数不是同一口径，且 41% 无法复算**。
> `11%` 是**残留无源率（8/67）**，`假阳性率` 在末期为 **0（8 条全真）**。
> 把「残留率」写成「假阳性率」会让人误以为还剩 8 条误报 —— 事实是 0 条。

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

## 配套工具：`tools/real_defect_scanner.py`

体检引擎查的是「**你的产出**有没有形式缺陷」。这个工具查的是另一头：
**上游 issue / PR 描述里的缺陷长什么样**——用来反推规则集该抓什么。

它按六类「静默失效」判据扫文本，每类都是从真实上游缺陷反推的（非凭空设计）：

| 类 | 缺陷 | 真实例（2026-10 核验） |
|---|---|---|
| S1 | 静默降级 | [SOCKS5 认证失败静默回退直连](https://github.com/CloakHQ/CloakBrowser/issues/157) |
| S2 | 归因缺口 | 状态变更无head/sequence 锚，重试或并发下错算 |
| S3 | 假成功 | 自报 done/success，实际未生效（[分词器漏非 ASCII](https://github.com/trailhq/Graft/issues/432)） |
| S4 | 无界增长 | 资源无上界（[ledger 涨到锁超时](https://github.com/ruvnet/ruflo/issues/3164)） |
| S5 | 假过滤 | 策略实际未生效（[deny 策略热重载期被绕过](https://github.com/anomalyco/opencode/issues/52333)） |
| S6 | 量纲错配 | 同名量不同单位（ms 与 s 混用） |

```bash
python tools/real_defect_scanner.py <路径> [--json] [--include-docs]
python tools/real_defect_scanner.py . --selftest    # 守门人自检（6 正样本 + 7 负样本）
```

- 退出码：`0` 干净 / `1` 有命中 / `2` 用法错。
- **主战场是 issue/PR 描述文本**：实测 218 份真实 issue 标题 → 12 行独立命中，
  人工逐条核对为真缺陷。
- **对源码召回接近于零**（实测 472 与 3118 个文件 → 0~2 命中，且都落在测试字符串里）。
  所以它不是静态分析器，别拿它当 lint 用。
- 判据是英文关键词形态，换文风（「悄悄失败」）会漏；判据非恒真已用严格版反证过
  （删 2 条 S4 模式 → 命中 13→12，方向正确翻）。
- 守卫有v1.1→v1.4 四次迭代史（三类误报形态：否定语义 / 文档字面量 / docstring 内部）。
  CHANGELOG 视为过时线索默认排除——命中≠缺陷仍存在，对外指控前必须回原仓核实。

---

## 与 [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) 的关系

同处 AI Agent 质量赛道，但**互补不重叠**：它管「agent **怎么干活**」（25 个流程技能，
DEFINE→SHIP 生命周期组织，`npx skills add` 分发），本项目管「agent **干完的产出能不能出门**」
（出口闸 + 机读报告）。`doubt-driven-development` 等同名技能是社区通用概念名（对抗审查、TDD），
两边各自独立实现，语义见各自文档。

| | addyosmani/agent-skills | 本项目 |
|---|---|---|
| 拦截点 | 过程中（写代码/做计划时介入） | 出口处（产出交付/上架/发布前拦截） |
| 检查对象 | 代码变更、架构、测试有效性 | AI 生成的交付物：listing/歌词/日报/HTML/短视频脚本 |
| 判定依据 | 工程最佳实践（Google 工程文化） | 政策原文逐条对标（Amazon/Google Ads/发行商/欧盟 AI Act），每条带 `source` 与 `enforce_type` 强度分级 |
| 退出码 | Approve / Request changes（评审结论） | `0/1/2/3` 严格四分：内容问题与工具故障绝不混同 |
| 机读出口 | — | SARIF（GitHub Code Scanning）/ JUnit / JSON |

**它有而本项目（暂）没有的**：`npx skills add` 统一分发入口、变异测试验证测试有效性、
生命周期完整叙事。**本项目有而它没有的**：可核证的政策 source 表（护城河）、
法规强度分级、全 SKIP 守卫（宁报故障不给假绿）、面向非代码产出的垂类规则集。

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
