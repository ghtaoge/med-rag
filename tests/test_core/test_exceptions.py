"""异常体系测试。"""

from app.core.exceptions import (
    MedRagError,
    ValidationError,
    RetrievalError,
    GenerationError,
    DocumentError,
    ConfigurationError,
)


def test_med_rag_error_has_code_and_message():
    """基础异常包含 code 和 message。"""

    err = MedRagError("test error")
    assert err.message == "test error"
    assert err.code == "MED_RAG_ERROR"


def test_subclass_errors_have_specific_codes():
    """子类异常有各自专属 code。"""

    assert ValidationError("v").code == "VALIDATION_ERROR"
    assert RetrievalError("r").code == "RETRIEVAL_ERROR"
    assert GenerationError("g").code == "GENERATION_ERROR"
    assert DocumentError("d").code == "DOCUMENT_ERROR"
    assert ConfigurationError("c").code == "CONFIGURATION_ERROR"


def test_all_errors_are_med_rag_error_subclass():
    """所有异常都是 MedRagError 子类。"""

    assert isinstance(ValidationError("v"), MedRagError)
    assert isinstance(RetrievalError("r"), MedRagError)
    assert isinstance(GenerationError("g"), MedRagError)
