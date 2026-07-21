from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from app.safety.models import RiskCategory


class ClassifierUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ClassifierResult:
    label: str
    categories: tuple[RiskCategory, ...]


@dataclass(frozen=True)
class RuleSignals:
    categories: tuple[RiskCategory, ...]
    signals: tuple[str, ...]


_CATEGORY_NAMES = {
    "jailbreak": RiskCategory.JAILBREAK,
    "personally identifiable information": RiskCategory.PII,
    "pii": RiskCategory.PII,
    "privacy": RiskCategory.PII,
    "illegal activity": RiskCategory.HARMFUL_CONTENT,
    "violence": RiskCategory.HARMFUL_CONTENT,
    "self-harm": RiskCategory.HARMFUL_CONTENT,
    "unethical behavior": RiskCategory.HARMFUL_CONTENT,
}


def parse_guard_output(value: str) -> ClassifierResult:
    label_match = re.search(
        r"^Safety:\s*(Safe|Controversial|Unsafe)\s*$",
        value,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if label_match is None:
        raise ClassifierUnavailable("安全分类器返回格式无效")
    label = label_match.group(1).lower()
    categories: list[RiskCategory] = []
    category_match = re.search(r"^Categories:\s*(.+)$", value, re.I | re.M)
    if category_match:
        for raw in category_match.group(1).split(","):
            name = raw.strip().lower()
            if name and name not in {"none", "n/a"}:
                category = _CATEGORY_NAMES.get(name)
                if category is None:
                    raise ClassifierUnavailable("安全分类器类别无效")
                categories.append(category)
    return ClassifierResult(label, tuple(dict.fromkeys(categories)))


def rule_signals(text: str) -> RuleSignals:
    compact = re.sub(r"\s+", "", text).lower()
    matches: list[tuple[RiskCategory, str]] = []

    def add(category: RiskCategory, signal: str) -> None:
        matches.append((category, signal))

    if any(term in compact for term in ("忽略之前", "忽略权限", "绕过权限", "ignoreprevious", "bypass")):
        add(RiskCategory.JAILBREAK, "policy_bypass")
    if any(term in compact for term in ("导出", "泄露", "外传", "发送到外部", "exfiltrate")) and any(
        term in compact for term in ("全部", "所有", "其他部门", "内部", "数据库")
    ):
        add(RiskCategory.DATA_EXFILTRATION, "bulk_export")
    if any(term in compact for term in ("枚举", "列出全部", "列出所有", "遍历全部", "dumpall")):
        add(RiskCategory.BULK_ENUMERATION, "bulk_enumeration")
    if any(term in compact for term in ("rm-rf", "powershell", "cmd.exe", "/etc/", "../", "执行命令", "shell")):
        add(RiskCategory.COMMAND_INJECTION, "command_or_path")
    if any(term in compact for term in ("删除", "禁用", "提权", "修改权限", "创建管理员")) and any(
        term in compact for term in ("知识库", "用户", "账号", "权限", "管理员", "数据库")
    ):
        add(RiskCategory.MANAGEMENT_ACTION, "management_action")
    return RuleSignals(
        tuple(dict.fromkeys(category for category, _ in matches)),
        tuple(dict.fromkeys(signal for _, signal in matches)),
    )


class QwenGuardClassifier:
    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        model: str,
        timeout_seconds: float,
    ):
        self.client = client
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds

    def classify(self, text: str) -> ClassifierResult:
        try:
            response = self.client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": text}],
                    "temperature": 0,
                    "max_tokens": 128,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return parse_guard_output(content)
        except ClassifierUnavailable:
            raise
        except Exception as exc:
            raise ClassifierUnavailable("安全分类器不可用") from exc
