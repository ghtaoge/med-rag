"""Med-Rag 统一异常体系。

所有模块使用这套异常，API 层统一捕获转换为 HTTP 响应。
"""

from __future__ import annotations


class MedRagError(Exception):
    """Med-Rag 基础异常。"""

    def __init__(self, message: str, code: str = "MED_RAG_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ValidationError(MedRagError):
    """输入校验失败。"""

    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR")


class RetrievalError(MedRagError):
    """检索引擎异常。"""

    def __init__(self, message: str):
        super().__init__(message, code="RETRIEVAL_ERROR")


class GenerationError(MedRagError):
    """LLM 生成异常。"""

    def __init__(self, message: str):
        super().__init__(message, code="GENERATION_ERROR")


class DocumentError(MedRagError):
    """文档处理异常。"""

    def __init__(self, message: str):
        super().__init__(message, code="DOCUMENT_ERROR")


class IntentError(MedRagError):
    """意图识别异常。"""

    def __init__(self, message: str):
        super().__init__(message, code="INTENT_ERROR")


class EvaluationError(MedRagError):
    """效果评估异常。"""

    def __init__(self, message: str):
        super().__init__(message, code="EVALUATION_ERROR")


class ConfigurationError(MedRagError):
    """配置异常。"""

    def __init__(self, message: str):
        super().__init__(message, code="CONFIGURATION_ERROR")


class SecurityError(MedRagError):
    """安全策略拒绝。"""

    def __init__(self, message: str, code: str = "SECURITY_ERROR"):
        super().__init__(message, code=code)


class FileSecurityError(SecurityError):
    """上传文件未通过安全检查。"""

    def __init__(self, message: str = "文件未通过安全检查"):
        super().__init__(message, code="FILE_SECURITY_REJECTED")
