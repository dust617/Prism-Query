"""SearchBrain 包。使用：from searchbrain import search"""
from .models import SearchMode, SearchRequest, SearchResponse
from .orchestrator import search

__all__ = ["search", "SearchMode", "SearchRequest", "SearchResponse"]
__version__ = "0.1.0"