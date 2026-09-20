import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

boto3_module = types.ModuleType("boto3")
boto3_module.resource = MagicMock()
sys.modules.setdefault("boto3", boto3_module)

from utils.dynamodb_utils import (  # noqa: E402
    GoogleTokenWriteConflictError,
    get_google_token_by_uuid,
    get_mapping_domain_settings,
    list_mapping_domain_calendar_mappings,
    list_mapping_domain_calendar_mappings_for_owner,
    list_mapping_domain_task_sources,
    update_google_token_by_uuid,
)
from utils.token_crypto import TokenCryptoError  # noqa: E402


class DynamoDbGoogleTokenTests(unittest.TestCase):
    def test_get_google_token_returns_raw_stored_fields(self):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {
                "uuid": "u-1",
                "accessToken": "enc:v1:encrypted-access",
                "refreshToken": "enc:v1:encrypted-refresh",
            }
        }
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            item = get_google_token_by_uuid("u-1")
        self.assertEqual(item["accessToken"], "enc:v1:encrypted-access")
        self.assertEqual(item["refreshToken"], "enc:v1:encrypted-refresh")
        table.get_item.assert_called_once_with(Key={"uuid": "u-1"}, ConsistentRead=False)

    def test_get_google_token_returns_plaintext_fields_unchanged(self):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {
                "uuid": "u-1",
                "accessToken": "plain-access",
                "refreshToken": "plain-refresh",
            }
        }
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            item = get_google_token_by_uuid("u-1")
        self.assertEqual(item["accessToken"], "plain-access")
        self.assertEqual(item["refreshToken"], "plain-refresh")

    def test_get_google_token_supports_consistent_read(self):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {
                "uuid": "u-1",
                "accessToken": "plain-access",
                "refreshToken": "plain-refresh",
            }
        }
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            item = get_google_token_by_uuid("u-1", consistent_read=True)
        self.assertEqual(item["accessToken"], "plain-access")
        self.assertEqual(item["refreshToken"], "plain-refresh")
        table.get_item.assert_called_once_with(Key={"uuid": "u-1"}, ConsistentRead=True)

    def test_update_google_token_encrypts_plaintext_fields(self):
        table = MagicMock()
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            with patch(
                "utils.dynamodb_utils.encrypt_token_if_plaintext",
                side_effect=["enc:v1:access", "enc:v1:refresh"],
            ) as mock_encrypt:
                update_google_token_by_uuid("u-1", "plain-access", "plain-refresh", "111", "222", "123")

        self.assertEqual(mock_encrypt.call_args_list[0].args[0], "plain-access")
        self.assertEqual(mock_encrypt.call_args_list[1].args[0], "plain-refresh")

        kwargs = table.update_item.call_args.kwargs
        self.assertEqual(kwargs["Key"], {"uuid": "u-1"})
        self.assertEqual(kwargs["ExpressionAttributeValues"][":at"], "enc:v1:access")
        self.assertEqual(kwargs["ExpressionAttributeValues"][":rt"], "enc:v1:refresh")
        self.assertEqual(kwargs["ExpressionAttributeValues"][":expiry"], "111")
        self.assertEqual(kwargs["ExpressionAttributeValues"][":updated"], "222")
        self.assertEqual(kwargs["ExpressionAttributeValues"][":expected_updated"], "123")
        self.assertEqual(
            kwargs["ConditionExpression"],
            "attribute_not_exists(updatedAt) OR updatedAt = :expected_updated",
        )

    def test_update_google_token_does_not_double_encrypt_prefixed_values(self):
        table = MagicMock()
        access = "enc:v1:access"
        refresh = "enc:v1:refresh"
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            with patch(
                "utils.dynamodb_utils.encrypt_token_if_plaintext",
                side_effect=[access, refresh],
            ):
                update_google_token_by_uuid("u-1", access, refresh, "111", "222", "123")

        values = table.update_item.call_args.kwargs["ExpressionAttributeValues"]
        self.assertEqual(values[":at"], access)
        self.assertEqual(values[":rt"], refresh)

    def test_update_google_token_raises_for_malformed_prefixed_value(self):
        table = MagicMock()
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            with patch(
                "utils.dynamodb_utils.encrypt_token_if_plaintext",
                side_effect=TokenCryptoError("Malformed encrypted token payload."),
            ):
                with self.assertRaises(TokenCryptoError):
                    update_google_token_by_uuid("u-1", "enc:v1:broken", "plain-refresh", "111", "222", "123")
        table.update_item.assert_not_called()


class DynamoDbGoogleTokenConcurrencyTests(unittest.TestCase):
    def test_update_google_token_uses_attribute_not_exists_guard_when_row_has_no_updated_at(self):
        table = MagicMock()
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            with patch(
                "utils.dynamodb_utils.encrypt_token_if_plaintext",
                side_effect=["enc:v1:access", "enc:v1:refresh"],
            ):
                update_google_token_by_uuid("u-1", "plain-access", "plain-refresh", "111", "222")

        kwargs = table.update_item.call_args.kwargs
        self.assertEqual(kwargs["ConditionExpression"], "attribute_not_exists(updatedAt)")
        self.assertNotIn(":expected_updated", kwargs["ExpressionAttributeValues"])

    def test_update_google_token_maps_conditional_conflict(self):
        table = MagicMock()

        class _ConditionalFailure(Exception):
            def __init__(self):
                self.response = {"Error": {"Code": "ConditionalCheckFailedException"}}

        table.update_item.side_effect = _ConditionalFailure()

        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            with patch(
                "utils.dynamodb_utils.encrypt_token_if_plaintext",
                side_effect=["enc:v1:access", "enc:v1:refresh"],
            ):
                with self.assertRaises(GoogleTokenWriteConflictError):
                    update_google_token_by_uuid("u-1", "plain-access", "plain-refresh", "111", "222", "123")


class DynamoDbMappingDomainTests(unittest.TestCase):
    def test_gets_settings_with_consistent_read(self):
        table = MagicMock()
        table.get_item.return_value = {"Item": {"ownerUserUuid": "user-1"}}
        with patch("utils.dynamodb_utils._get_mapping_domain_table", return_value=table):
            result = get_mapping_domain_settings("user-1")

        self.assertEqual(result["ownerUserUuid"], "user-1")
        table.get_item.assert_called_once_with(
            Key={"pk": "USER#user-1", "sk": "NOTION_SETTINGS"},
            ConsistentRead=True,
        )

    def test_lists_task_sources_across_query_pages(self):
        table = MagicMock()
        table.query.side_effect = [
            {"Items": [{"id": "source-1"}], "LastEvaluatedKey": {"pk": "next"}},
            {"Items": [{"id": "source-2"}]},
        ]
        with patch("utils.dynamodb_utils._get_mapping_domain_table", return_value=table):
            result = list_mapping_domain_task_sources("user-1")

        self.assertEqual([item["id"] for item in result], ["source-1", "source-2"])
        self.assertTrue(table.query.call_args_list[0].kwargs["ConsistentRead"])
        self.assertEqual(
            table.query.call_args_list[1].kwargs["ExclusiveStartKey"],
            {"pk": "next"},
        )

    def test_lists_calendar_mappings_through_contract_index(self):
        table = MagicMock()
        table.query.return_value = {"Items": [{"id": "mapping-1"}]}
        with patch("utils.dynamodb_utils._get_mapping_domain_table", return_value=table):
            result = list_mapping_domain_calendar_mappings("user-1", "source-1")

        self.assertEqual(result, [{"id": "mapping-1"}])
        kwargs = table.query.call_args.kwargs
        self.assertEqual(kwargs["IndexName"], "SourceMappingsIndex")
        self.assertEqual(
            kwargs["ExpressionAttributeNames"]["#sourceMappingOwnerSourceKey"],
            "sourceMappingOwnerSourceKey",
        )
        self.assertEqual(
            kwargs["ExpressionAttributeValues"][":sourceMappingOwnerSourceKey"],
            "USER#user-1#TASK_SOURCE#source-1",
        )
        self.assertNotIn("ConsistentRead", kwargs)

    def test_lists_calendar_mappings_for_owner_with_consistent_base_query(self):
        table = MagicMock()
        table.query.side_effect = [
            {"Items": [{"id": "mapping-1"}], "LastEvaluatedKey": {"pk": "next"}},
            {"Items": [{"id": "mapping-2"}]},
        ]
        with patch("utils.dynamodb_utils._get_mapping_domain_table", return_value=table):
            result = list_mapping_domain_calendar_mappings_for_owner("user-1")

        self.assertEqual([item["id"] for item in result], ["mapping-1", "mapping-2"])
        first = table.query.call_args_list[0].kwargs
        self.assertTrue(first["ConsistentRead"])
        self.assertNotIn("IndexName", first)
        self.assertEqual(first["ExpressionAttributeValues"][":pk"], "USER#user-1")
        self.assertEqual(first["ExpressionAttributeValues"][":mappingPrefix"], "CALENDAR_MAPPING#")
        self.assertEqual(
            table.query.call_args_list[1].kwargs["ExclusiveStartKey"],
            {"pk": "next"},
        )


if __name__ == "__main__":
    unittest.main()
