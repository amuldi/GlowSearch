__all__ = ["IngestionSummary", "OliveYoungIngestionPipeline"]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    from app.ingestion.oliveyoung_pipeline import IngestionSummary, OliveYoungIngestionPipeline

    exports = {
        "IngestionSummary": IngestionSummary,
        "OliveYoungIngestionPipeline": OliveYoungIngestionPipeline,
    }
    return exports[name]
