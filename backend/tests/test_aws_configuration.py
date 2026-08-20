import os
import unittest
from unittest.mock import patch

from app.agents.objective_agent import ObjectiveAgent
from app.api.account_handler import AccountHandler
from app.core.config import Config
from app.db.dynamodb_handler_optimized import (
    DynamoDBHandlerOptimized,
    RAGSchemaHandlerOptimized,
)
from scripts.setup_dynamodb_table import table_definitions


class AWSConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "AWS_REGION": "ap-south-1",
            "BEDROCK_REGION": "us-east-1",
            "BEDROCK_MODEL_ID": "test.inference-profile",
            "DYNAMODB_TABLE_ACCOUNTS": "test-accounts",
            "DYNAMODB_TABLE_POC_DOCUMENTS": "test-documents",
            "DYNAMODB_TABLE_RAG_SCHEMA": "test-rag",
            "S3_BUCKET_NAME": "test-sow-bucket",
        }

    def test_config_reads_environment_specific_resource_names(self):
        with patch.dict(os.environ, self.environment, clear=False):
            config = Config()

        self.assertEqual(config.AWS_REGION, "ap-south-1")
        self.assertEqual(config.BEDROCK_REGION, "us-east-1")
        self.assertEqual(config.MODEL_ID, "test.inference-profile")
        self.assertEqual(config.DYNAMODB_TABLE_ACCOUNTS, "test-accounts")
        self.assertEqual(config.DYNAMODB_TABLE_POC_DOCUMENTS, "test-documents")
        self.assertEqual(config.DYNAMODB_TABLE_RAG_SCHEMA, "test-rag")
        self.assertEqual(config.S3_BUCKET_NAME, "test-sow-bucket")

    @patch("app.db.dynamodb_handler_optimized.boto3.resource")
    def test_document_and_rag_handlers_use_environment(self, resource):
        with patch.dict(os.environ, self.environment, clear=False):
            documents = DynamoDBHandlerOptimized()
            document_call = resource.call_args
            rag = RAGSchemaHandlerOptimized()
            rag_call = resource.call_args

        self.assertEqual(documents.table_name, "test-documents")
        self.assertEqual(document_call.kwargs["region_name"], "ap-south-1")
        self.assertEqual(rag.table_name, "test-rag")
        self.assertEqual(rag_call.kwargs["region_name"], "ap-south-1")
        resource.return_value.Table.assert_any_call("test-documents")
        resource.return_value.Table.assert_any_call("test-rag")

    @patch("app.api.account_handler.boto3.resource")
    def test_account_handler_uses_environment(self, resource):
        with patch.dict(os.environ, self.environment, clear=False):
            handler = AccountHandler()

        self.assertEqual(handler.table_name, "test-accounts")
        self.assertEqual(resource.call_args.kwargs["region_name"], "ap-south-1")
        resource.return_value.Table.assert_called_once_with("test-accounts")

    @patch("app.agents.objective_agent.boto3.client")
    def test_bedrock_uses_its_own_region(self, client):
        with patch.dict(os.environ, self.environment, clear=False):
            config = Config()
            ObjectiveAgent(config)

        self.assertEqual(client.call_args.kwargs["region_name"], "us-east-1")

    def test_setup_defines_every_configured_table_and_required_indexes(self):
        with patch.dict(os.environ, self.environment, clear=False):
            definitions = {
                definition["TableName"]: definition
                for definition in table_definitions()
            }

        self.assertEqual(
            set(definitions), {"test-accounts", "test-documents", "test-rag"}
        )
        document_indexes = {
            index["IndexName"]
            for index in definitions["test-documents"]["GlobalSecondaryIndexes"]
        }
        rag_indexes = {
            index["IndexName"]
            for index in definitions["test-rag"]["GlobalSecondaryIndexes"]
        }
        self.assertEqual(
            document_indexes,
            {
                "customer-index",
                "author-index",
                "project-index",
                "mode-index",
                "task-index",
            },
        )
        self.assertEqual(
            rag_indexes, {"client-project-mode-index", "mode-index"}
        )


if __name__ == "__main__":
    unittest.main()
