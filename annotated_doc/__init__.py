"""Dummy module to satisfy FastAPI import of annotated_doc.Doc"""

class Doc:
    """Placeholder for FastAPI's annotated_doc.Doc"""
    def __init__(self, *args, **kwargs):
        self.doc = args[0] if args else None

