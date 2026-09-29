"""Classification of console failures into operator-facing categories.

The equipment areas raise their own error types with machine-oriented codes.
The console translates every failure into one of three answers the operator
can act on:

* :data:`CATEGORY_INPUT`   – the values entered were missing or out of range;
* :data:`CATEGORY_DENIED`  – the values were acceptable but the line state or
  an interlock forbids the action right now;
* :data:`CATEGORY_ERROR`   – something unexpected failed server-side.

Each category carries a short Chinese title and a hint telling the operator
what to do, plus a code that lets maintenance look the exact gate up.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

#: Category identifiers echoed in the JSON ``errorType`` field.
CATEGORY_INPUT = "input"
CATEGORY_DENIED = "denied"
CATEGORY_ERROR = "error"


class ErrorCategory(str, Enum):
    INPUT = CATEGORY_INPUT
    DENIED = CATEGORY_DENIED
    ERROR = CATEGORY_ERROR


@dataclass(frozen=True, slots=True)
class ErrorView:
    """Everything the browser needs to render a classified failure."""

    category: str
    title: str
    hint: str
    code: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "errorType": self.category,
            "title": self.title,
            "hint": self.hint,
            "code": self.code,
            "detail": self.detail,
        }


#: Short title and next-step hint for each category.
CATEGORY_TEXT = {
    CATEGORY_INPUT: ("参数填错", "请核对输入数值后重试，设备未执行任何动作。"),
    CATEGORY_DENIED: ("设备不允许", "输入本身有效，但当前设备状态或联锁不满足，请先处理现场条件。"),
    CATEGORY_ERROR: ("系统故障", "服务端处理出错，请联系维护人员并提供错误码。"),
}

#: Codes that mean the request values themselves were invalid.  Every other
#: domain code is a state/interlock refusal.
INPUT_CODES = frozenset(
    {
        "power-invalid",
        "invalid-gain",
        "invalid-speed",
        "no-speed",
        "offset-invalid",
        "tank-volume",
        "dew-high",
        "temp-range",
    }
)

#: Chinese explanation per equipment error code, keyed by the wire value.
CODE_TEXT: dict[str, str] = {
    # weld
    "align-pending": "焊接前对中尚未确认",
    "arc-blocked": "焊接电弧门未建立（或当前无电弧）",
    "latch-held": "焊接联锁锁扣仍处于锁定状态",
    "power-invalid": "焊接电压或电流超出允许范围",
    # pump
    "level-low": "酸槽实际液位低于启动下限",
    "strip-run": "带钢仍在运行，不允许该操作",
    "no-replenish": "当前浓度已达到目标值，无需补酸",
    # tension
    "invalid-gain": "张力增益必须为正数",
    "invalid-speed": "目标速度必须为正数",
    "not-persisted": "焊接张力尚未落盘，不能以此张力运行",
    "ramp-unready": "张力辊尚未具备提速条件",
    # pickle
    "tank-volume": "槽体容积必须为正数",
    "offset-invalid": "浓度标定偏移超出允许范围",
    # dryer
    "no-exhaust": "排风尚未建立，不允许升温",
    "dew-high": "露点高于升温允许上限",
    "temp-range": "目标炉温超出允许温度区间",
    # entry
    "no-coil": "当前没有已上卷的钢卷",
    "interlock-held": "入口联锁未释放",
    "alarm-active": "过流告警尚未复位",
    # exit
    "rinse-active": "喷淋仍在进行，不允许该操作",
    "track-stale": "焊缝跟踪数据已过期，请先刷新跟踪点",
    # strip
    "tail-unflushed": "带尾残酸尚未冲净",
}


def describe_domain_error(error: Exception) -> ErrorView:
    """Build the classified view for a subsystem ``RuntimeError``."""

    describe = getattr(error, "to_dict", None)
    code = ""
    if callable(describe):
        try:
            info = describe()
        except Exception:  # pragma: no cover - defensive only
            info = {}
        if isinstance(info, dict):
            code = str(info.get("code", ""))
    category = CATEGORY_INPUT if code in INPUT_CODES else CATEGORY_DENIED
    title, generic_hint = CATEGORY_TEXT[category]
    explanation = CODE_TEXT.get(code, "")
    hint = f"{explanation}。{generic_hint}" if explanation else generic_hint
    return ErrorView(
        category=category,
        title=title,
        hint=hint,
        code=code,
        detail=str(error),
    )


def describe_param_error(name: str = "", raw: str = "") -> ErrorView:
    """Build the view for a missing or malformed query parameter."""

    shown = name or "参数"
    detail = f"参数 {shown} 缺失或不是数字：{raw!r}" if raw else f"参数 {shown} 缺失"
    return ErrorView(
        category=CATEGORY_INPUT,
        title=CATEGORY_TEXT[CATEGORY_INPUT][0],
        hint=f"请核对「{shown}」后重试，设备未执行任何动作。",
        code="bad-param",
        detail=detail,
    )


def describe_internal_error(error: Exception) -> ErrorView:
    """Build the view for an unexpected server-side failure."""

    title, hint = CATEGORY_TEXT[CATEGORY_ERROR]
    return ErrorView(
        category=CATEGORY_ERROR,
        title=title,
        hint=hint,
        code=type(error).__name__,
        detail=str(error),
    )
