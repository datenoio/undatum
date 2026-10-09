"""`db load` routes MongoDB and Elasticsearch/OpenSearch URIs to the ingesters."""

from unittest.mock import MagicMock

import pytest

from undatum.cmds.db_load import DatabaseLoader, search_endpoint
from undatum.common.errors import ValidationError


@pytest.fixture
def loader():
    instance = DatabaseLoader()
    instance.ingester = MagicMock()
    return instance


def test_mongodb_uri_uses_path_as_database(loader):
    loader.load("data.jsonl", "mongodb://localhost:27017/shop", "orders", mode="replace")
    args = loader.ingester.ingest_single.call_args[0]
    assert args[:4] == ("data.jsonl", "mongodb://localhost:27017/shop", "shop", "orders")
    assert args[4]["dbtype"] == "mongodb"
    assert args[4]["drop"] is True


def test_mongodb_uri_without_database(loader):
    with pytest.raises(ValidationError, match="database name"):
        loader.load("data.jsonl", "mongodb://localhost:27017", "orders")


@pytest.mark.parametrize(
    "uri,endpoint",
    [
        ("elasticsearch://localhost:9200", "https://localhost:9200"),
        ("elasticsearch+http://localhost:9200/ignored?x=1", "http://localhost:9200"),
        ("opensearch://user:pw@search:9200", "https://user:pw@search:9200"),
    ],
)
def test_search_endpoint(uri, endpoint):
    assert search_endpoint(uri) == endpoint


def test_elasticsearch_uri_routes_to_ingester(loader):
    loader.load(
        "data.jsonl", "elasticsearch://localhost:9200", "logs", api_key="k", es_pipeline="p"
    )
    args = loader.ingester.ingest_single.call_args[0]
    assert args[1] == "https://localhost:9200"
    assert args[3] == "logs"
    assert args[4]["dbtype"] == "elasticsearch"
    assert args[4]["api_key"] == "k"
    assert args[4]["es_pipeline"] == "p"
    assert args[4]["drop"] is False


@pytest.mark.parametrize("mode", ["replace", "upsert"])
def test_elasticsearch_rejects_unsupported_modes(loader, mode):
    with pytest.raises(ValidationError, match="not supported"):
        loader.load("data.jsonl", "elasticsearch://localhost:9200", "logs", mode=mode)
    loader.ingester.ingest_single.assert_not_called()


def test_upsert_key_rejected_for_mongodb(loader):
    with pytest.raises(ValidationError, match="upsert-key"):
        loader.load("d.jsonl", "mongodb://h/db", "c", upsert_key="id")
