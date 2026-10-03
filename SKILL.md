---
name: music-release-audit
description: 音乐发行前合规体检器。只做确定性政策/元数据/清单检查——AI 标识合规（双标识、视频提示≥5%且≥2秒）、发行商 AI 政策二元判定（CD Baby/TuneCore/网易云/Spotify）、著作权元数据五层清单、AI 使用说明四要素、歌词抄袭客观特征提取。当用户要检查歌曲能否发行、AI 音乐合规、发行商政策冲突、歌词抄袭风险、ISRC/UPC/分成/母带权利人检查时使用。绝不下侵权判定结论。
---

# music-release-audit · 音乐发行前合规体检器

## 定位（先读这段，再决定用不用）

**只做能写成 `if` 的确定性检查。** 不碰音频信号，不下法律结论。

| 做 | 不做（红线，不可越） |
|---|---|
| AI 标识合规（政策原文阈值） | ❌ 音频 AI 生成检测 / 人声克隆识别（厂商数字虚高 15-23 个百分点） |
| 发行商 AI 政策二元判定 | ❌ 歌词「实质性相似」判定（无量化法定阈值，**必须人判**） |
| 著作权元数据清单核对 | ❌ 文案是否夸大宣传（隐含承诺无法穷举） |
| 歌词**客观特征**提取 | ❌ 合同条款商业合理性（黑盒，且是 Harvey 的价值所在） |
| 混音/响度等技术体检（另属音频工程，已有成熟免费工具） | |

**判据只有一条：能不能写成 if。写不成就不做。**

## 快速开始

```bash
P=<managed python>
S=~/.workbuddy/skills/music-release-audit

"$P" $S/scripts/audit.py <track.json>            # 用默认政策表
"$P" $S/scripts/audit.py <track.json> --policy <policy.json>

# 退出码：0=通过  1=有 BLOCK（先修再发行）  2=只有 WARN（需人眼确认）
```

夹具回归（三档退出码各一）：
```bash
"$P" $S/scripts/audit.py $S/fixtures/track_fail.json           # → exit 1（9 BLOCK）
"$P" $S/scripts/audit.py $S/fixtures/track_pass.json           # → exit 0（0 问题）
"$P" $S/scripts/audit.py $S/fixtures/track_lyrics_similar.json # → exit 2（E-001 触发）
```

## track.json 结构

```jsonc
{
  "title": "曲名",
  "type": "audio" | "video",
  "lyrics": "可选，E-001 需要",
  "video": { "overlay_height_ratio": 0.06, "overlay_seconds": 3.0 },  // video 规则用
  "metadata": {
    "explicit_ai_label": true,        // A-001 显式标识
    "implicit_ai_flag": true,         // A-002 隐式标识（双标识）
    "eu_ai_disclosed": true,          // A-005 欧盟 Art.50(2)
    "composer": "", "lyricist": "", "performer": "", "producer": "",   // C-001 实名
    "isrc": "CNA231600001", "upc": "695123456789",                    // C-002 格式
    "splits": [{"name": "x", "percent": 100}],                        // C-003 归一
    "master_rights": "自录",            // C-004 母带权利人
    "uses_samples": false, "uses_voice_clone": false,                // C-005
    "licenses": { "sample": "", "voice": "" },
    "ai_credits": {                    // Spotify 分四项
      "vocal": "", "lyrics": "", "instrumental": "", "post_production": ""
    },
    "ai_usage": {                      // D-001 四要素（差异点）
      "tool": "", "version": "", "stage": "", "input_source": ""
    }
  },
  "_context": {
    "ai_generated": true,
    "distributor": "spotify" | "cdbaby" | "tunecore" | "netease_cloud",
    "target_regions": ["CN", "EU", "US"],
    "reference_lyrics": "可选，E-001 对照文本"
  }
}
```

## 规则分组（v1.0.0，13 条）

| 组 | ID | 内容 |
|---|---|---|
| **AI 标识** | A-001~005 | 中国《人工智能生成合成内容标识办法》：显式+隐式**双**标识；视频文字提示 ≥ 画面最短边 5% 且持续 ≥ 2 秒；欧盟 AI Act Art.50(2) 主动披露 |
| **发行商政策** | B-001 | CD Baby **不接收** AI / TuneCore **需完全获许可数据集** / 网易云 **需主动声明** / Spotify **需分项 AI Credits**（人声/歌词/乐器/后期） |
| **著作权元数据** | C-001~005 | 词曲/演唱/制作人实名 · ISRC/UPC 格式 · 分成归一 100% · 母带权利人 · 采样与声线授权 |
| **AI 使用说明** | D-001 | 四要素：工具名/版本/参与环节/输入来源——**多数人只写「AI 生成」，这层是本工具差异点** |
| **歌词客观特征** | E-001 | 字级重合率 · 句长序列 · 段落句数结构 · 押韵表 · 4-gram 片段 · 起句。**输出必附「是否侵权需人工判断」** |

## 扩展方式（关键：政策不写在代码里）

**加规则 = 改 `data/policy_*.json`，不改 `audit.py`。**
每条规则须有 `check`（指向 CHECKERS 注册名）、`source`（可复核出处）、`severity`、`enabled`。
政策**会过期**（Amazon 给 14 天合规窗口、欧盟 Art.50 有延期传闻、抖音公约 2025-01-23 更新）——**这张持续维护的版本化表本身就是护城河**，比规则本身值钱。

新检查器才需要改代码：在 `audit.py` 里写函数 → 加进 `CHECKERS` 字典。

## 版本变更记录

- **v1.0.1**：修 2 个 bug（均由夹具抓出）——①句长序列相似度原把列表 `str()` 后比对，度量的是字面量，得到假值 12.2%，改为直接序列比对后为真实 73.3% ②E-001 告警方向写反（把「重合率低」当风险，实为「重合率高」才是风险），改用 `warn_char_ratio_high` / `warn_char_ratio_low` 双阈值。

## 诚实边界

- 规则依据为**政策原文与公开条款**，非法律意见；跨法域（尤其欧盟 Art.50 时效与例外）**须人工复核**。
- E-001 输出的客观特征**只是给人看的证据**，不构成侵权认定。
- `policy_version` 决定结果；升级政策表时**必须重跑三个夹具**确认回归。
