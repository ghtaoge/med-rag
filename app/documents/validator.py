"""文档校验模块。格式检查 + 内容完整性 + 医疗术语校验。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.documents.loader import supported_extensions


@dataclass
class ValidationResult:
    """校验结果。"""

    is_valid: bool
    errors: list[str]
    warnings: list[str]


class DocumentValidator:
    """文档校验器。"""

    # 医疗相关文件名关键词
    MEDICAL_FILENAME_KEYWORDS = [
        "药品", "说明书", "适应症", "临床路径", "处方",
        "检验", "手术", "护理", "病历", "医嘱",
    ]

    def validate(self, file_path: Path) -> ValidationResult:
        """校验文档是否可以正常处理。"""

        errors = []
        warnings = []

        # 格式检查
        ext = file_path.suffix.lower()
        if ext not in supported_extensions():
            errors.append(f"不支持的文件格式: {ext}")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # 文件大小检查（不应超过 50MB）
        file_size = file_path.stat().st_size
        max_size = 50 * 1024 * 1024  # 50MB
        if file_size > max_size:
            errors.append(f"文件过大: {file_size / 1024 / 1024:.1f}MB，最大支持 50MB")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # 内容完整性检查（尝试读取）
        try:
            from app.documents.loader import load_document

            text = load_document(file_path)
            if not text.strip():
                errors.append("文件内容为空")
                return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

            # 内容过短可能是 OCR 失败
            if len(text.strip()) < 50 and ext in {".pdf", ".png", ".jpg"}:
                warnings.append("提取内容过少，可能是扫描件 OCR 未成功识别")

        except Exception as e:
            errors.append(f"文件读取失败: {str(e)}")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # 医疗术语校验（警告级别，不阻断）
        filename = file_path.name.lower()
        is_medical = any(kw in filename for kw in self.MEDICAL_FILENAME_KEYWORDS)
        if not is_medical:
            warnings.append("文件名未包含医疗关键词，可能不属于医疗知识库")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
