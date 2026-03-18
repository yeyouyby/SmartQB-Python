import os
import pytest
from document_service import DocumentService

def test_document_service_methods():
    assert hasattr(DocumentService, 'process_doc_with_layout')
    assert hasattr(DocumentService, 'extract_from_word')

def test_document_service_extract_word_stub(tmp_path):
    # expect exception when not a real word doc
    dummy_path = tmp_path / "dummy.docx"
    dummy_path.write_text("dummy")

    with pytest.raises(Exception):
        DocumentService.extract_from_word(str(dummy_path))
