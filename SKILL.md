---
name: agent-output-audit
description: AI 产出通用体检规则引擎（agent-output-audit）。四个可插拔规则集共 46 条规则：(1) ai-output 通用体检——检查 AI 自己写出来的东西：占位符残留、无源数字、绝对化表述、凭据泄漏、PII、结构过浅、篇幅异常；(2) music 音乐发行前合规——AI 标识合规（中国《标识办法》+GB 45438-2025 / EU AI Act Art.50）、发行商 AI 政策（CD Baby/TuneCore/网易云/Spotify）、著作权元数据（ISRC/UPC/署名/母带/采样/声线）；(3) ecommerce 跨境电商 listing——标题长度、五点索引字节阈值、广告误导表述；(4) shortvideo 短视频口播——广告法红线、医疗宣称、字数↔语速↔字幕行宽时间轴交叉对齐。当用户要检查 AI 产出能不能交付/发布、HTML 日报或交付件有没有占位符和未核实的数字、歌曲能否发行、跨境电商 listing 是否符合亚马逊规则、口播稿时长与字幕宽度是否匹配时使用。只做能写成 if 的确定性检查，不下法律结论、不下侵权判定。绝不用 WARN 冒充 BLOCK。
---

# agent-output-audit · AI 产出体检引擎

> 一个**引擎 + 四个可插拔规则集**。换个垂类只需放一个目录，引擎不为垂类让步。

## 定位（先读这段，再决定用不用）

**只做能写成 `if` 的确定性检查。** 不碰音频信号，不下法律结论，不做实质性侵权判定。

| 做 | 不做（红线，不可越） |
|---|---|
| 按政策原文阈值核验 | ❌ 音频 AI 生成检测 / 人声克隆识别（厂商数字虚高 15-23 个百分点） |
| 发行商 AI 政策判定 | ❌ 歌词「实质性相似」判定（无量化法定阈值，**必须人判**） |
| 著作权元数据清单核对 | ❌ 文案是否夸大宣传（隐含承诺无法穷举） |
| 歌词**客观特征**提取 | ❌ 合同条款商业合理性（黑盒） |
| 混音/响度等技术体检（另属音频工程，已有成熟免费工具） | |

**判据只有一条：能不能写成 if。写不成就不做。**

---

## 快速开始（统一入口是 `aoa.py`，不是 `scripts/audit.py`）

```bash
P=<managed python>
S=~/.workbuddy/skills/music-release-audit

"$P" $S/aoa.py list                                    # 列出规则集与条数
"$P" $S/aoa.py run ai-output <交付件.html>              # 体检任意 AI 产出
"$P" $S/aoa.py run music    <track.json>               # 音乐发行前合规
"$P" $S/aoa.py run ecommerce <listing.json>             # 跨境电商 listing
"$P" $S/aoa.py run shortvideo<script.json>             # 口播稿 / 短视频
"$P" $S/aoa.py run ai-output <file> --format sarif     # GitHub Code Scanning
"$P" $S/aoa.py run ai-output <file> --format json      # 机读
"$P" $S/aoa.py run ai-output <file> --format junit     # CI 通用
```

被检文件可以是 `.json`（已适配结构），也可以直接是 `.md` / `.html` / `.py` / `.js` / `.ts`。

**退出码**：`0` 通过 · `1` 有 BLOCK（必须修） · `2` 只有 WARN（需人判断） · **`3` 规则集/引擎故障**

> 退出码 **3 必须与 1/2 严格区分**。「规则坏了」和「内容有问题」是两回事；
> 混同的后果是调用方把 bug 当提示忽略。

---

## 规则集（46 条）

| 规则集 | 条数 | 检查什么 | 典型输入 |
|---|---:|---|---|
| **`ai-output`** | 9 | **产出本身**：占位符残留 / 无源数字 / 绝对化表述 / 凭据泄漏 / PII / 结构完整性 / 篇幅异常 | 任意 AI 产出 |
| `music` | 20 | 音乐发行前：AI 标识合规 / 发行商政策 / 著作权链 / 歌词客观特征 | track.json |
| `ecommerce` | 10 | 跨境电商 listing：标题长度 / 五点索引字节阈值 / 广告误导表述 | listing.json |
| `shortvideo` | 7 | 短视频口播：广告法红线 / 医疗宣称 / 时间轴交叉对齐 | script.json |

**分级原则（四个规则集通用）**：
> BLOCK 只给「机器能 100% 判定一定错」的硬伤；WARN 只给「需要人判断」的。
> **绝不用 WARN 冒充 BLOCK** —— 一次就会让人对整个工具失去信任。

---

## 音乐规则集：`enforce_type` 分级（⭐ v2.0.0 核心设计）

**每条规则标注 `enforce_type`**，输出带图例：

| 图例 | 类型 | 含义 | 举例 |
|---|---|---|---|
| ⚖ | `legal_mandatory` | **法律强制**，违反即违法 | ISRC（著作权法实施条例）、采样授权、母带许可 |
| § | `legal_standard` / `case_law` | 司法标准 / 判例要旨 | 「接触+实质性相似」、(2014)穗中法知民终字第289号 |
| ◆ | `platform_technical` | 平台技术要求，违反被拒收 | CD Baby 拒收 AI、TuneCore 需全链路许可数据集 |
| ◇ | `commercial_practice` / `platform_statement` | **商业惯例/平台表态，非法律义务** | UPC、分成归一 100%、网易云声明（无官方条款页） |
| ★ | `project_custom` | 本项目自定义，**不可称"合规要求"** | D-001 AI 使用说明四要素 |

> **为什么这是核心**：v1 曾把商业惯例（UPC / 分成 100%）写成"法律要求"，把平台自愿项（Spotify AI Credits）写成"要求"。v2 全部纠正——**夸大义务强度会误导创作者做无用的合规动作，也可能让使用者误以为有法律兜底。**

### track.json 结构（v2 字段名）

```jsonc
{
  "title": "曲名",
  "type": "audio" | "video",
  "lyrics": "可选，E-001c 需要",
  "video": { "overlay_height_ratio": 0.06, "overlay_seconds": 3.0 },
  "metadata": {
    "user_ai_declaration": true,      // A-001《标识办法》第十条：用户主动声明
    "label_tampering": false,         // A-002：是否恶意删除/篡改标识（true=违规）
    "eu_machine_readable_marking": true,  // A-005a Art.50(2)（提供者义务）
    "is_deepfake": false,             // A-005b Art.50(4)：仅 deepfake 需部署者披露
    "is_artistic_work": true,         // A-005b：艺术品可退化披露
    "eu_ai_disclosed_by_appropriate_means": true,
    "eu_ai_deployer_disclosed": true,
    "composer": "", "lyricist": "",   // C-001a ⚖法律强制：法定署名
    "performer": "", "producer": "",  // C-001b ◇惯例：平台要求实名
    "isrc": "CNA231600001",           // C-002a ⚖法律强制
    "upc": "695123456789",            // C-002b ◇惯例（DSP 交付必填，无法律依据）
    "splits": [{"name": "x", "percent": 100}],   // C-003 ◇惯例
    "master_rights": "自录",           // C-004a ⚖法律强制（权利法定）
    "uses_samples": true,             // C-005a ⚖法律强制：须著作权人许可+报酬
    "licenses": { "sample": "", "voice": "" },
    "uses_voice_clone": true,         // C-005b ⚖法律强制·人格权：民法典
    "ai_credits": { "vocal": "", "lyrics": "", "instrumental": "", "post_production": "" },
    "ai_usage": { "tool": "", "version": "", "stage": "", "input_source": "" }  // D-001 ★自定义
  },
  "_context": {
    "ai_generated": true,
    "distributor": "spotify" | "cdbaby" | "tunecore" | "netease_cloud",
    "target_regions": ["CN", "EU", "US"],
    "reference_lyrics": "可选，E-001c 对照文本"
  }
}
```

### 发行商政策一览（v2 已按核证结果纠正）

| 发行商 | 判定 | 强度 | 关键点 |
|---|---|---|---|
| **CD Baby** | **拒收** | 🔴 BLOCK | 官方页原文「You will not be able to distribute A.I.-generated content」；**部分 AI 亦拒**；违规可下架 + 终止合作 |
| **TuneCore** | 需条件 | 🔴 BLOCK | 官方原文要求**任何环节**用 AI 都须依赖 fully licensed datasets —— **无「纯 AI 才受限」豁免** |
| **网易云音乐** | 建议声明 | 🟡 WARN | ⚠️ **无可引用官方条款页**，依据为客服对媒体口头表态（2026-04，小范围测试阶段） |
| **Spotify** | **自愿**披露 | ⚪ INFO | 官方原文「AI credits are **optional**」且「absence of AI credits doesn't mean AI wasn't used」——**未标注不违规** |

---

## 扩展方式（关键：政策不写在代码里）

**加规则 = 改 `rulesets/<垂类>/policy.json`（音乐）或规则集内的 `POLICY` 字典，不改引擎。**
每条规则须有：`check`（指向 CHECKERS 注册名）、`source`（可复核出处，**不接受二手博客**）、`enforce_type`、`severity`、`enabled`。

> ⚠ `CHECKERS` 的键名必须与 policy 的 `check` 字段**字面一致** —— 不加/不剥前缀。
> 这个坑踩过 4 次（music / ecommerce / ai-output / shortvideo 各一次），
> 每次都表现为「0 条规则」。引擎的 `validate()` 会替你抓住，
> 且已接入 `aoa.py list`，错误在**列目录时**暴露，不等到 run。

**政策会过期**——Amazon 标题政策给 14 天窗口、欧盟 Art.50 有延期（Omnibus Regulation (EU) 2026/1744 将 50(2) 对已投入使用的系统宽限至 2026-12-02）、中国国标会换版。

新**检查器**才需要改代码：写函数 → 加进 `CHECKERS` 字典。

---

## 引擎的四道护栏（全部实测有效）

| 护栏 | 触发时 | 退出码 |
|---|---|---|
| 零规则守卫 | 规则集产出 0 条规则 | 3 |
| `validate()` | policy 的 check 字段对不上 | 3（点名规则 ID） |
| ERROR 单列 | 检查器抛异常 | 3 |
| `confidence_floor` | 指标覆盖率不足 | FAIL→WARN 降权 |

> 这四道都是被真实 bug 逼出来的：分别拦下过「0 条规则报通过」
> 「键名不匹配静默失效」「异常被降级成提示掩盖规则失效」「覆盖率 27% 却照样告警」。

---

## 版本变更记录

- **v2.1.0 / 平台化**（2026-10-04）：抽引擎层（`engine/` 四模块）+ 适配器层（`md/html/code` → 统一结构 `agent_output/1.0`），从「一个工具」变成「一个平台」。
- **音乐 v2.0.0**（2026-10-04）：经 13 条逐条原文核证后重建。纠正 6 处硬伤——
  ①`E-001c` 比对对象与裁判要旨双错（实为《新套马杆》vs《套马杆》，判词从未提"美国儿歌"；"歌曲不侵权"实为权利人未主张曲权利）
  ②`A-005` 条款号与定性双错（50(2) 是**提供者**机器可读标记，非"主动披露"；部署者披露在 50(4) 且**仅限 deepfake**）
  ③`A-002`「双标识缺一即违规」系**杜撰**（第九条明文允许无显式标识的合法情形；隐式标识属鼓励项）
  ④`C-003` 分成归一 100% 无法律依据（著作权法第十四条仅要求"合理分配"）
  ⑤`C-002` UPC 无中国法律强制依据
  ⑥`B-001d` Spotify AI Credits 由"要求"纠正为"自愿"
  规则 13→20 条，新增 `enforce_type` 分级。
- **v1.0.1**：修 2 个 bug（均由夹具抓出）——①句长序列相似度原把列表 `str()` 后比对，度量的是字面量，得到假值 12.2%，改为直接序列比对后为真实 73.3% ②E 组告警方向写反（把"重合率低"当风险，实为"高"才是）。

---

## 诚实边界

- 只做**形式与可追溯性**检查，**不判断内容对错**。「无源数字」不等于「数据是假的」，只等于「**读者无法验证**」。
- 规则依据为**政策原文与司法文书**，**非法律意见**；跨法域（尤其欧盟 Art.50 时效与例外）**须人工复核**。
- **法律强制项的判定也非法律意见**——本工具做的是"该填的填了吗、格式对吗"，不判断实质侵权。
- E-001c 输出的客观特征**只是给人看的证据**，不构成侵权认定。
- 部分阈值（语速 220-280 字/分、无源数字比例 15%、篇幅 20/4000 行）**未在真实语料上标定**，已在各规则集 `needs_pro_review` 中标出。
- 建议正式商用前由**法律专业人士**复核一次规则集。

---

## 遗留（已知，未修，勿当已完成）

- 本地目录名仍是 `music-release-audit`，与仓库名 `agent-output-audit` 不一致；统一入口 `aoa.py` 已就位，目录名改动待定。
- `scripts/audit.py` 是音乐规则的**遗留单文件实现**，仍保留作回归基线；新用法一律走 `aoa.py run music`。
- 政策表有两份拷贝：`data/policy_2026-10-04.json`（legacy 脚本用）与 `rulesets/music/policy.json`（新规则集用），当前 md5 一致，但**改一处需同步另一处**，待合并为单一来源。
