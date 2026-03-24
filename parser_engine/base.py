from abc import ABC, abstractmethod
from typing import List, Dict

class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> List[Dict]:
        """统一返回标准格式：[{"markdown_content": "...", "images": {"id": "b64"}, "page_num": 1}]"""
        pass
