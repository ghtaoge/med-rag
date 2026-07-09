from pymilvus import DataType

from app.retrieval.milvus_store import MilvusStore


def test_delete_chunks_skips_missing_collection():
    """First sync should not fail when the Milvus collection has not been created yet."""

    class MissingCollectionClient:
        def has_collection(self, collection_name):
            return False

        def delete(self, **kwargs):
            raise AssertionError("delete should not be called for a missing collection")

    store = MilvusStore()
    store._client = MissingCollectionClient()

    store.delete_chunks("new-file.txt")

def test_embed_texts_falls_back_when_model_is_unavailable(monkeypatch):
    """Sync should keep working when the embedding model is not cached locally."""

    store = MilvusStore()

    def fail_to_load_model():
        raise RuntimeError("offline")

    monkeypatch.setattr(store, "_get_embedding_model", fail_to_load_model)

    vectors = store.embed_texts(["同一段文本", "另一段文本"])
    repeat = store.embed_texts(["同一段文本"])[0]

    assert len(vectors) == 2
    assert len(vectors[0]) == store.embedding_dim
    assert vectors[0] == repeat
    assert vectors[0] != vectors[1]

def test_ensure_collection_creates_string_id_schema():
    """Milvus collection should accept the string chunk ids used by DocumentChunk."""

    class FakeSchema:
        def __init__(self, auto_id, enable_dynamic_field):
            self.auto_id = auto_id
            self.enable_dynamic_field = enable_dynamic_field
            self.fields = []

        def add_field(self, **kwargs):
            self.fields.append(kwargs)

    class FakeIndexParams(list):
        def add_index(self, **kwargs):
            self.append(kwargs)

    class SchemaClient:
        def __init__(self):
            self.created_schema = None
            self.created_index_params = None

        def has_collection(self, collection_name):
            return False

        def create_schema(self, auto_id, enable_dynamic_field):
            return FakeSchema(auto_id, enable_dynamic_field)

        def prepare_index_params(self):
            return FakeIndexParams()

        def create_collection(self, **kwargs):
            self.created_schema = kwargs["schema"]
            self.created_index_params = kwargs["index_params"]

    store = MilvusStore()
    store._client = SchemaClient()

    store._ensure_collection()

    id_field = next(field for field in store._client.created_schema.fields if field["field_name"] == "id")
    assert id_field["datatype"] == DataType.VARCHAR

def test_ensure_collection_recreates_empty_legacy_int_id_schema():
    """Empty legacy collections with int64 ids should be recreated before inserting chunks."""

    class FakeSchema:
        def __init__(self, auto_id, enable_dynamic_field):
            self.fields = []

        def add_field(self, **kwargs):
            self.fields.append(kwargs)

    class FakeIndexParams(list):
        def add_index(self, **kwargs):
            self.append(kwargs)

    class LegacySchemaClient:
        def __init__(self):
            self.dropped = False
            self.created_schema = None

        def has_collection(self, collection_name):
            return True and not self.dropped

        def describe_collection(self, collection_name):
            return {"fields": [{"name": "id", "type": DataType.INT64}]}

        def query(self, **kwargs):
            return [{"count(*)": 0}]

        def drop_collection(self, collection_name):
            self.dropped = True

        def create_schema(self, auto_id, enable_dynamic_field):
            return FakeSchema(auto_id, enable_dynamic_field)

        def prepare_index_params(self):
            return FakeIndexParams()

        def create_collection(self, **kwargs):
            self.created_schema = kwargs["schema"]

    store = MilvusStore()
    store._client = LegacySchemaClient()

    store._ensure_collection()

    assert store._client.dropped is True
    assert store._client.created_schema is not None
