"""Elasticsearch ingester client construction and bulk options."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("elasticsearch")

from undatum.cmds.ingester.elastic import ElasticIngester  # noqa: E402


def test_client_accepts_timeout_with_installed_major_version():
    ingester = ElasticIngester("http://localhost:9200", api_key=None, search_index="idx", timeout=5)
    assert ingester.client is not None


def test_tls_verification_is_on_by_default():
    ingester = ElasticIngester("https://localhost:9200", api_key=None, search_index="idx")
    node = next(iter(ingester.client.transport.node_pool.all()))
    assert node.config.verify_certs is True


def test_insecure_disables_verification_with_warning(caplog):
    with caplog.at_level("WARNING"):
        ingester = ElasticIngester(
            "https://localhost:9200", api_key=None, search_index="idx", verify_certs=False
        )
    node = next(iter(ingester.client.transport.node_pool.all()))
    assert node.config.verify_certs is False
    assert "verification is disabled" in caplog.text


@pytest.mark.parametrize("pipeline", [None, "my-pipeline"])
def test_bulk_pipeline_is_optional(pipeline):
    ingester = ElasticIngester(
        "http://localhost:9200", api_key=None, search_index="idx", pipeline=pipeline
    )
    ingester.client = MagicMock()
    ingester.client.bulk.return_value = {"errors": False}
    ingester.ingest([{"id": 1, "name": "a"}])
    kwargs = ingester.client.bulk.call_args.kwargs
    assert kwargs.get("pipeline") == pipeline
