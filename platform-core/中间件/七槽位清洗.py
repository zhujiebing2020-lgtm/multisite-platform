"""platform-core/中间件/七槽位清洗.py

CLAUDE.md 合约一 · 输入端清洗

所有外部数据进入系统,必须用 7 槽位清洗。
ZJB 用业务语言给数据,本模块负责把业务语言映射到 7 槽位结构化字段。

7 槽位定义(合约一 L79-87):
  date         数据是哪天的             YYYY-MM-DD                  必填
  channel      哪个渠道                FB/Google/TikTok/X/其他    必填
  metric       哪个业务指标             花费/HVU/CPHQ/注册/购买/...必填
  provided_by  谁提供的                ZJB/CHJ/HNN/HZM/...        必填
  source       从哪来                  csv/口头/日报/AdClaw 导出   必填
  subject      跟谁/哪组关联            HNN-组54-樱花 / FB平台      选填
  note         备注                    任意文字                    选填

必填字段缺失:标 "unknown" 接收 + 主动追问 ZJB,不脑补、不拒收(L91)
env_flag 场景:metric=env_flag / subject=<平台名> / note=<异常描述>(L89)

依赖反向硬约束:本模块属于中间件,不许 import 上下文层/事件层/引擎层/执行层。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ─── 合约一 L82 渠道枚举 ─────────────────────
class Channel(str, Enum):
    FB = "FB"
    GOOGLE = "Google"
    TIKTOK = "TikTok"
    X = "X"
    OTHER = "其他"

    @classmethod
    def normalize(cls, raw: str) -> Optional["Channel"]:
        """业务语言 → 枚举,容忍大小写和别名"""
        s = (raw or "").strip()
        if not s:
            return None
        alias = {
            "fb": cls.FB, "facebook": cls.FB, "Facebook": cls.FB, "FB": cls.FB,
            "google": cls.GOOGLE, "Google": cls.GOOGLE, "Google Ads": cls.GOOGLE,
            "tiktok": cls.TIKTOK, "TikTok": cls.TIKTOK, "抖音": cls.TIKTOK,
            "x": cls.X, "X": cls.X, "twitter": cls.X, "Twitter": cls.X,
            "其他": cls.OTHER, "other": cls.OTHER,
        }
        if s in alias:
            return alias[s]
        for c in cls:
            if c.value == s:
                return c
        return None


# ─── 合约一 L83 指标枚举(开放,允许"其他")─────
KNOWN_METRICS = {
    "花费", "HVU", "CPHQ", "注册", "购买", "停留时长",
    "env_flag",  # L89 env_flag 场景
    "其他",
}


# ─── 合约一 L84 + 附录 G 团队成员 ─────────────
KNOWN_PROVIDERS = {
    "ZJB", "CHJ", "HNN", "HZM", "ZXR", "LZL", "PLZ",
    "郭刚", "曾凡立",
    "吴玲", "田棒棒", "吴慧妍", "陆佳炜", "柴碧如",
    "AdClaw", "Qwen-ingest",
    "其他",
}


# ─── 7 槽位数据结构 ────────────────────────
@dataclass
class CleanedInput:
    """合约一输出 · 7 槽位标准结构"""
    date: str           # 必填(缺则 unknown)
    channel: str        # 必填
    metric: str         # 必填
    provided_by: str    # 必填
    source: str         # 必填
    subject: Optional[str] = None     # 选填
    note: Optional[str] = None        # 选填

    # 清洗过程信息(不属于 7 槽位,但调用方需要)
    missing_required: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_env_flag: bool = False         # L89 env_flag 场景标记

    def has_unknown_required(self) -> bool:
        return len(self.missing_required) > 0

    def prompt_for_missing(self) -> str:
        """L91 追问话术 — 必填缺失时主动追问 ZJB"""
        if not self.missing_required:
            return ""
        templates = {
            "date":        "这份数据是哪天的?",
            "channel":     "这份数据是哪个渠道的(FB / Google / TikTok / X / 其他)?",
            "metric":      "这份数据的业务指标是什么(花费 / HVU / CPHQ / 注册 / 购买 / 停留时长 / 其他)?",
            "provided_by": "这份数据是谁给的?我先按 provided_by=unknown 入库,你补一下我再回填。",
            "source":      "这份数据从哪来(csv / 日报 / 口头 / AdClaw 导出 / ...)?",
        }
        lines = ["⚠️ 七槽位清洗 · 必填字段缺失,已按 unknown 暂存,请补充:"]
        for k in self.missing_required:
            lines.append(f"  · {k}: {templates.get(k, '请补充 ' + k)}")
        return "\n".join(lines)


# ─── 主清洗入口 ─────────────────────────────
def clean(
    raw: dict,
    default_provided_by: Optional[str] = None,
) -> CleanedInput:
    """
    业务语言 dict → CleanedInput

    raw 是用户原始输入(可能 key 名是中文也可能英文),
    本函数把它归一到 7 槽位标准结构。

    缺必填 → 字面值标 "unknown" + 入 missing_required 等追问
    """
    # 字段别名表(中英文双写都接受)
    alias = {
        "date":        ["date", "日期", "数据日期", "data_date"],
        "channel":     ["channel", "渠道", "平台", "platform"],
        "metric":      ["metric", "指标", "业务指标"],
        "provided_by": ["provided_by", "提供人", "谁给的", "provider"],
        "source":      ["source", "来源", "从哪来"],
        "subject":     ["subject", "关联", "广告组", "组", "subject_ref"],
        "note":        ["note", "备注", "comment"],
    }

    def pick(logical: str) -> Optional[str]:
        for k in alias[logical]:
            if k in raw and raw[k] not in (None, ""):
                return str(raw[k]).strip()
        return None

    missing: list[str] = []
    warnings: list[str] = []

    # date
    date = pick("date")
    if date is None:
        missing.append("date")
        date = "unknown"
    else:
        if not _looks_like_date(date):
            warnings.append(f"date={date!r} 不像 YYYY-MM-DD")

    # channel
    raw_channel = pick("channel")
    if raw_channel is None:
        missing.append("channel")
        channel = "unknown"
    else:
        c = Channel.normalize(raw_channel)
        if c is None:
            warnings.append(f"channel={raw_channel!r} 不在枚举内,按字面入库")
            channel = raw_channel
        else:
            channel = c.value

    # metric
    metric = pick("metric")
    if metric is None:
        missing.append("metric")
        metric = "unknown"
    elif metric not in KNOWN_METRICS:
        warnings.append(f"metric={metric!r} 不在已知集合,接收但提醒")

    is_env_flag = (metric == "env_flag")  # L89

    # provided_by
    provided_by = pick("provided_by") or default_provided_by
    if provided_by is None or provided_by == "":
        missing.append("provided_by")
        provided_by = "unknown"
    elif provided_by not in KNOWN_PROVIDERS:
        warnings.append(f"provided_by={provided_by!r} 不在已知成员名单,接收但提醒")

    # source
    source = pick("source")
    if source is None:
        missing.append("source")
        source = "unknown"

    # subject 选填
    subject = pick("subject")
    if is_env_flag and not subject:
        warnings.append("env_flag 场景下 subject 应填平台名(L89)")

    # note 选填
    note = pick("note")

    return CleanedInput(
        date=date,
        channel=channel,
        metric=metric,
        provided_by=provided_by,
        source=source,
        subject=subject,
        note=note,
        missing_required=missing,
        warnings=warnings,
        is_env_flag=is_env_flag,
    )


def _looks_like_date(s: str) -> bool:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# ─── CLI 自测(P0-9.1.b)─────────────────────
if __name__ == "__main__":
    import json

    scenarios = [
        ("场景 1 · 完整输入(吴玲日报)", {
            "date": "2026-05-13",
            "channel": "FB",
            "metric": "HVU",
            "provided_by": "吴玲",
            "source": "吴玲日报 0513.md",
            "subject": "CHJ-组17-18 Sensual",
            "note": "5/13 再添 12 HVU 累计 739",
        }),

        ("场景 2 · 缺 provided_by + 缺 source", {
            "date": "2026-05-13",
            "channel": "Google",
            "metric": "花费",
            "subject": "全平台",
        }),

        ("场景 3 · env_flag 特殊场景(L89)", {
            "date": "2026-05-13",
            "channel": "FB",
            "metric": "env_flag",
            "provided_by": "ZJB",
            "source": "ZJB 口头",
            "subject": "FB平台",
            "note": "FB 算法更新 + 5/12 起 CPHQ 普涨",
        }),

        ("场景 4 · 非法 channel 值(枚举外)", {
            "date": "2026-05-13",
            "channel": "Pinterest",     # 不在 FB/Google/TikTok/X/其他
            "metric": "HVU",
            "provided_by": "ZJB",
            "source": "试投手动记",
        }),

        ("场景 5 · 几乎全空(模拟 ZJB 一句话 attempt)", {
            "note": "今天 HZM 反馈 IG 流量到了但没成交",
        }),
    ]

    for title, raw in scenarios:
        print(f"\n━━━ {title} ━━━")
        print(f"输入: {json.dumps(raw, ensure_ascii=False)}")
        ci = clean(raw, default_provided_by="ZJB" if "ZJB" in title else None)
        print(f"7 槽位:")
        for k in ("date", "channel", "metric", "provided_by", "source", "subject", "note"):
            v = getattr(ci, k)
            tag = " ← unknown" if v == "unknown" else ""
            print(f"  {k:12s} = {v!r}{tag}")
        if ci.is_env_flag:
            print(f"  [env_flag 场景标记]")
        if ci.warnings:
            print(f"warnings:")
            for w in ci.warnings:
                print(f"  ⚠ {w}")
        if ci.has_unknown_required():
            print()
            print(ci.prompt_for_missing())
