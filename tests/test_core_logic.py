from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


# Make the plugin importable when tests are launched from the plugin directory
# and make the sibling AstrBot package available without changing AstrBot.
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_ASTRBOT_ROOT = _PLUGIN_ROOT.parents[2]
for _path in (_PLUGIN_ROOT.parent, _ASTRBOT_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from qq_restapi.adapters.qq_restapi_webhook_server import (  # noqa: E402
    QQRestAPIWebhookServer,
    _build_ed25519_seed,
    _verify_qq_webhook_signature,
)
from qq_restapi.core.qq import token_manager as legacy_token_manager  # noqa: E402
from qq_restapi.core.qq import sender as legacy_sender  # noqa: E402
from qq_restapi.db.database import QQRestAPIDatabase  # noqa: E402
from qq_restapi.db.repository import QQRestAPIRepository  # noqa: E402
from qq_restapi.runtime.context import merge_plugin_config, set_plugin_config  # noqa: E402
from qq_restapi.runtime.dispatch import _TTLSeenCache, _dedup_key  # noqa: E402
from qq_restapi.runtime.full_group_reply import (  # noqa: E402
    FullGroupReplyController,
    _clamp_probability,
    _non_negative_int,
    _parse_judge_json,
    _positive_float,
)
from qq_restapi.runtime.sender import QQRestAPISender, SendResult  # noqa: E402
from qq_restapi.runtime.token_manager import TokenManager, TokenManagerError  # noqa: E402


class ConfigMergeTests(unittest.TestCase):
    def test_private_backend_url_is_merged_into_platform_config(self):
        set_plugin_config(
            {
                "bot_api_base_url": "https://api.example.com",
                "unknown_plugin_key": "ignored",
            }
        )
        try:
            merged = merge_plugin_config({"appid": "app"})
        finally:
            set_plugin_config(None)

        self.assertEqual(merged["appid"], "app")
        self.assertEqual(merged["bot_api_base_url"], "https://api.example.com")
        self.assertNotIn("unknown_plugin_key", merged)


class WebhookSignatureTests(unittest.TestCase):
    def test_seed_is_utf8_secret_repeated_and_truncated_to_32_bytes(self):
        self.assertEqual(_build_ed25519_seed("abc"), (b"abc" * 11)[:32])
        self.assertEqual(len(_build_ed25519_seed("密码")), 32)
        with self.assertRaises(ValueError):
            _build_ed25519_seed("")

    def test_signature_verification_accepts_valid_payload_only(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519

        secret = "unit-test-secret"
        timestamp = "1710000000"
        body = b'{"op":0,"d":{"id":"evt-1"}}'
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
            _build_ed25519_seed(secret)
        )
        signature = private_key.sign(timestamp.encode() + body).hex()

        self.assertTrue(_verify_qq_webhook_signature(secret, timestamp, signature, body))
        self.assertFalse(
            _verify_qq_webhook_signature(secret, timestamp, signature, body + b"x")
        )
        self.assertFalse(_verify_qq_webhook_signature(secret, timestamp, "not-hex", body))
        self.assertFalse(_verify_qq_webhook_signature(secret, None, signature, body))

    def test_validation_response_uses_event_ts_and_plain_token(self):
        server = object.__new__(QQRestAPIWebhookServer)
        server.secret = "unit-test-secret"
        payload = {"event_ts": "1710000000", "plain_token": "plain-token"}

        response = asyncio.run(server.webhook_validation(payload))

        self.assertEqual(response["plain_token"], "plain-token")
        # Validation signs event_ts + plain_token (the QQ handshake format),
        # so verify it directly with the corresponding public key.
        from cryptography.hazmat.primitives.asymmetric import ed25519

        key = ed25519.Ed25519PrivateKey.from_private_bytes(
            _build_ed25519_seed(server.secret)
        )
        key.public_key().verify(
            bytes.fromhex(response["signature"]),
            (payload["event_ts"] + payload["plain_token"]).encode(),
        )

    def test_webhook_module_import_does_not_remove_existing_root_handlers(self):
        root = logging.getLogger()
        handler = logging.NullHandler()
        root.addHandler(handler)
        try:
            # Reloading is important here: the historical implementation
            # removed handlers at module import time.
            import qq_restapi.adapters.qq_restapi_webhook_server as webhook_module

            importlib.reload(webhook_module)
            self.assertIn(handler, root.handlers)
        finally:
            root.removeHandler(handler)


class FullGroupReplyHelperTests(unittest.TestCase):
    def test_judge_json_accepts_boolean_string_and_embedded_json(self):
        self.assertEqual(_parse_judge_json('{"should_reply":true,"reason":"问答"}'), (True, "问答"))
        self.assertEqual(_parse_judge_json('结果：{"should_reply":"no","reason":"闲聊"}'), (False, "闲聊"))
        self.assertEqual(_parse_judge_json("garbage"), (False, "invalid_judge_json"))

    def test_numeric_settings_are_normalized(self):
        self.assertEqual(_clamp_probability(2, 0.2), 1.0)
        self.assertEqual(_clamp_probability(-1, 0.2), 0.0)
        self.assertEqual(_clamp_probability("bad", 0.2), 0.2)
        self.assertEqual(_non_negative_int(-3, 5), 0)
        self.assertEqual(_non_negative_int("bad", 5), 5)
        self.assertEqual(_positive_float(0, 2.5), 2.5)
        self.assertEqual(_positive_float("bad", 2.5), 2.5)

    def test_invalid_mode_falls_back_to_normal(self):
        controller = FullGroupReplyController(
            context=None,
            config={"full_group_reply": {"mode": "bad"}},
        )
        with patch("qq_restapi.runtime.full_group_reply.logger.warning"):
            self.assertEqual(controller._settings().mode, "normal")


class SenderHelperTests(unittest.TestCase):
    def setUp(self):
        self.sender = QQRestAPISender("appid", "secret", token_manager=object())

    def test_markdown_downgrade_only_for_client_payload_errors(self):
        self.assertTrue(
            self.sender.should_downgrade_markdown_to_plain(
                SendResult(False, 400, code=50037)
            )
        )
        self.assertTrue(self.sender.should_downgrade_markdown_to_plain(SendResult(False, 422)))
        self.assertFalse(self.sender.should_downgrade_markdown_to_plain(SendResult(False, 401)))
        self.assertFalse(self.sender.should_downgrade_markdown_to_plain(SendResult(False, 500)))
        self.assertFalse(
            self.sender.should_downgrade_markdown_to_plain(
                SendResult(False, 400, ignored=True)
            )
        )

    def test_endpoint_and_message_helpers(self):
        self.assertEqual(
            self.sender._build_endpoint({"scene": "group", "group_id": "g1"}),
            ("/v2/groups/g1/messages", True),
        )
        self.assertEqual(
            self.sender._build_endpoint({"scene": "channel_dm", "guild_id": "guild"}),
            ("/dms/guild/messages", False),
        )
        self.assertEqual(self.sender._apply_ids({}, "m1", "e1"), {"msg_id": "m1", "event_id": "e1"})
        self.assertEqual(self.sender._process_button_parameter("btn"), {"id": "btn"})


class DispatchCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_ttl_cache_marks_only_second_and_later_calls_duplicate(self):
        cache = _TTLSeenCache(ttl_seconds=30, max_keys=10)
        results = await asyncio.gather(*(cache.mark_duplicate("same") for _ in range(5)))
        self.assertEqual(results.count(False), 1)
        self.assertEqual(results.count(True), 4)
        self.assertFalse(await cache.mark_duplicate(None))

    async def test_ttl_cache_expires_and_bounds_keys(self):
        cache = _TTLSeenCache(ttl_seconds=30, max_keys=2)
        await cache.mark_duplicate("a")
        await cache.mark_duplicate("b")
        await cache.mark_duplicate("c")
        self.assertLessEqual(len(cache._seen), 2)
        cache._seen["expired"] = 0
        self.assertFalse(await cache.mark_duplicate("expired"))

    def test_dedup_key_prefers_event_id_then_message_id(self):
        event = type("Event", (), {"qq_event_type": "GROUP_MESSAGE_CREATE", "qq_event_id": "evt"})()
        self.assertEqual(_dedup_key(event, "app"), "event:app:evt")
        event.qq_event_id = None
        event.message_id = "msg"
        event.session_id = "group"
        self.assertEqual(_dedup_key(event, "app"), "message:app:GROUP_MESSAGE_CREATE:group:msg")


class DatabaseRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().slow_callback_duration = 1.0
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = str(Path(self.temp_dir.name) / "qq_restapi-test.db")
        self.db = QQRestAPIDatabase(db_path=db_path)
        await self.db.initialize()
        self.repository = QQRestAPIRepository(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        self.temp_dir.cleanup()

    async def test_identity_scene_and_event_log_round_trip(self):
        await self.repository.upsert_user_identity(
            union_openid="union-1",
            nickname="first",
            last_seen_at=100,
        )
        updated = await self.repository.upsert_user_identity(
            union_openid="union-1",
            nickname="updated",
            last_seen_at=200,
        )
        self.assertEqual(updated.nickname, "updated")
        self.assertEqual(updated.last_seen_at, 200)

        first_scene = await self.repository.upsert_user_scene(
            scene_type="group",
            raw_openid="raw-1",
            union_openid="union-1",
            group_id="group-1",
            last_event_type="GROUP_MESSAGE_CREATE",
        )
        second_scene = await self.repository.upsert_user_scene(
            scene_type="group",
            raw_openid="raw-1",
            union_openid="union-1",
            group_id="group-1",
            nick="member",
        )
        self.assertEqual(first_scene.scene_id, second_scene.scene_id)
        self.assertEqual(second_scene.nick, "member")

        created = await self.repository.insert_event_log(
            log_level="INFO",
            event_kind="message",
            event_type="GROUP_MESSAGE_CREATE",
            scene_type="group",
            union_openid="union-1",
            group_id="group-1",
            payload_json='{"id":"event-1"}',
            created_at=300,
        )
        logs = await self.repository.list_event_logs(
            event_type="GROUP_MESSAGE_CREATE",
            union_openid="union-1",
        )
        self.assertEqual([item.log_id for item in logs], [created.log_id])


class TokenManagerTests(unittest.IsolatedAsyncioTestCase):
    class _Response:
        def __init__(self, status_code=200, data=None, text=""):
            self.status_code = status_code
            self._data = data
            self.text = text

        def json(self):
            if isinstance(self._data, BaseException):
                raise self._data
            return self._data

    class _Client:
        def __init__(self, response, delay=0):
            self.response = response
            self.delay = delay
            self.calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            if self.delay:
                await asyncio.sleep(self.delay)
            return self.response

    async def test_concurrent_get_token_refreshes_once(self):
        client = self._Client(
            self._Response(data={"access_token": "tok", "expires_in": 3600}),
            delay=0.01,
        )
        manager = TokenManager("app", "secret")
        with patch("qq_restapi.runtime.token_manager.get_async_client", return_value=client):
            tokens = await asyncio.gather(*(manager.get_token() for _ in range(8)))
        self.assertEqual(tokens, ["tok"] * 8)
        self.assertEqual(client.calls, 1)
        self.assertEqual(
            await manager.auth_headers(),
            {
                "Authorization": "QQBot tok",
                "Content-Type": "application/json",
            },
        )

    async def test_http_json_and_missing_token_fail_with_typed_error(self):
        manager = TokenManager("app", "secret")
        for response in (
            self._Response(status_code=500, data={"message": "oops"}, text="oops"),
            self._Response(status_code=200, data=ValueError("bad json")),
            self._Response(status_code=200, data={"message": "denied"}),
        ):
            client = self._Client(response)
            with patch("qq_restapi.runtime.token_manager.get_async_client", return_value=client):
                with self.assertRaises(TokenManagerError):
                    await manager.refresh()

    async def test_missing_credentials_fail_before_network(self):
        manager = TokenManager("", "")
        with self.assertRaises(TokenManagerError):
            await manager.get_token()


class LegacyTokenManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        legacy_token_manager._TOKEN_MANAGERS.clear()

    def test_manager_cache_reuses_runtime_manager_per_credentials(self):
        first = legacy_token_manager.get_token_manager("app-a", "secret-a")
        same = legacy_token_manager.get_token_manager("app-a", "secret-a")
        other = legacy_token_manager.get_token_manager("app-b", "secret-b")

        self.assertIs(legacy_token_manager.TokenManager, TokenManager)
        self.assertIs(first, same)
        self.assertIsNot(first, other)
        self.assertIsInstance(first, TokenManager)

    async def test_get_access_token_delegates_to_runtime_manager(self):
        manager = TokenManager("app", "secret")
        manager.get_token = AsyncMock(return_value="runtime-token")

        with patch.object(
            legacy_token_manager,
            "get_token_manager",
            return_value=manager,
        ) as get_manager:
            token = await legacy_token_manager.get_access_token("app", "secret")

        self.assertEqual(token, "runtime-token")
        get_manager.assert_called_once_with("app", "secret")
        manager.get_token.assert_awaited_once_with()
        self.assertEqual(legacy_token_manager.get_last_error(), "")

    async def test_runtime_token_error_is_converted_to_legacy_empty_result(self):
        manager = TokenManager("app", "secret")
        manager.get_token = AsyncMock(side_effect=TokenManagerError("token denied"))

        with patch.object(
            legacy_token_manager,
            "get_token_manager",
            return_value=manager,
        ):
            token = await legacy_token_manager.get_access_token("app", "secret")

        self.assertEqual(token, "")
        self.assertEqual(legacy_token_manager.get_last_error(), "token denied")


class LegacySenderCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    class _Response:
        def __init__(self, status_code: int, text: str, data):
            self.status_code = status_code
            self.text = text
            self._data = data

        def json(self):
            return self._data

    class _Client:
        def __init__(self, response=None, error: Exception | None = None):
            self.response = response
            self.error = error
            self.calls = []

        async def post(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            if self.error:
                raise self.error
            return self.response

    class _TokenManager:
        async def auth_headers(self):
            return {
                "Authorization": "QQBot runtime-token",
                "Content-Type": "application/json",
            }

        async def refresh(self):
            return "runtime-token"

    def test_public_signature_and_export_are_unchanged(self):
        from qq_restapi import public_api

        signature = inspect.signature(legacy_sender.send_markdown_template)
        parameters = list(signature.parameters.values())

        self.assertIs(public_api.send_markdown_template, legacy_sender.send_markdown_template)
        self.assertTrue(inspect.iscoroutinefunction(public_api.send_markdown_template))
        self.assertEqual(
            [parameter.name for parameter in parameters],
            [
                "api_url",
                "appid",
                "secret",
                "template_id",
                "param_keys",
                "param_values",
                "msg_id",
                "keyboard_id",
            ],
        )
        self.assertEqual(parameters[6].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(parameters[7].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(parameters[6].default)
        self.assertIsNone(parameters[7].default)

    async def test_full_url_payload_and_success_tuple_are_preserved(self):
        response = self._Response(200, '{"id":"message-1"}', {"id": "message-1"})
        client = self._Client(response=response)
        manager = self._TokenManager()

        with (
            patch.object(legacy_sender, "get_access_token", return_value="runtime-token"),
            patch.object(legacy_sender, "get_token_manager", return_value=manager),
            patch("qq_restapi.runtime.sender.get_async_client", return_value=client),
            patch("qq_restapi.runtime.sender._msg_seq", return_value=12345),
        ):
            result = await legacy_sender.send_markdown_template(
                "https://api.example.com/v2/groups/group-1/messages",
                "app",
                "secret",
                "template-1",
                ["first", "second", "third", "unused"],
                ["value", [1, None, 2], None],
                msg_id="message-source",
                keyboard_id="keyboard-1",
            )

        self.assertEqual(result, (200, '{"id":"message-1"}'))
        self.assertEqual(len(client.calls), 1)
        args, kwargs = client.calls[0]
        self.assertEqual(
            args,
            ("https://api.example.com/v2/groups/group-1/messages",),
        )
        self.assertEqual(
            kwargs["headers"],
            {
                "Authorization": "QQBot runtime-token",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(
            kwargs["json"],
            {
                "msg_type": 2,
                "msg_seq": 12345,
                "markdown": {
                    "custom_template_id": "template-1",
                    "params": [
                        {"key": "first", "values": ["value"]},
                        {"key": "second", "values": ["1", "2"]},
                    ],
                },
                "msg_id": "message-source",
                "keyboard": {"id": "keyboard-1"},
            },
        )

    async def test_http_error_still_returns_status_and_raw_text_tuple(self):
        response = self._Response(
            400,
            '{"code":50037,"message":"bad markdown"}',
            {"code": 50037, "message": "bad markdown"},
        )
        client = self._Client(response=response)

        with (
            patch.object(legacy_sender, "get_access_token", return_value="runtime-token"),
            patch.object(
                legacy_sender,
                "get_token_manager",
                return_value=self._TokenManager(),
            ),
            patch("qq_restapi.runtime.sender.get_async_client", return_value=client),
            patch("qq_restapi.runtime.sender.logger.warning"),
        ):
            result = await legacy_sender.send_markdown_template(
                "https://api.example.com/messages",
                "app",
                "secret",
                "template",
                [],
                [],
            )

        self.assertEqual(
            result,
            (400, '{"code":50037,"message":"bad markdown"}'),
        )

    async def test_http_200_business_error_still_returns_raw_legacy_tuple(self):
        raw = '{"code":50037,"message":"bad markdown"}'
        client = self._Client(
            response=self._Response(
                200,
                raw,
                {"code": 50037, "message": "bad markdown"},
            )
        )

        with (
            patch.object(legacy_sender, "get_access_token", return_value="runtime-token"),
            patch.object(
                legacy_sender,
                "get_token_manager",
                return_value=self._TokenManager(),
            ),
            patch("qq_restapi.runtime.sender.get_async_client", return_value=client),
            patch("qq_restapi.runtime.sender.logger.warning"),
        ):
            result = await legacy_sender.send_markdown_template(
                "https://api.example.com/messages",
                "app",
                "secret",
                "template",
                [],
                [],
            )

        self.assertEqual(result, (200, raw))

    async def test_expired_token_refreshes_and_retries_the_same_full_url(self):
        expired_raw = '{"code":11244,"message":"token expired"}'
        success_raw = '{"id":"message-after-refresh"}'

        class SequenceClient:
            def __init__(self, responses):
                self.responses = list(responses)
                self.calls = []

            async def post(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return self.responses.pop(0)

        class RefreshingTokenManager(self._TokenManager):
            def __init__(self):
                self.refresh_calls = 0

            async def refresh(self):
                self.refresh_calls += 1
                return "refreshed-token"

        client = SequenceClient(
            [
                self._Response(
                    200,
                    expired_raw,
                    {"code": 11244, "message": "token expired"},
                ),
                self._Response(200, success_raw, {"id": "message-after-refresh"}),
            ]
        )
        manager = RefreshingTokenManager()
        api_url = "https://api.example.com/v2/groups/group-1/messages"

        with (
            patch.object(legacy_sender, "get_access_token", return_value="runtime-token"),
            patch.object(legacy_sender, "get_token_manager", return_value=manager),
            patch("qq_restapi.runtime.sender.get_async_client", return_value=client),
        ):
            result = await legacy_sender.send_markdown_template(
                api_url,
                "app",
                "secret",
                "template",
                [],
                [],
            )

        self.assertEqual(result, (200, success_raw))
        self.assertEqual(manager.refresh_calls, 1)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual([call[0] for call in client.calls], [(api_url,), (api_url,)])
        self.assertEqual(client.calls[0][1]["json"], client.calls[1][1]["json"])

    async def test_token_and_transport_errors_keep_legacy_tuple_shape(self):
        with (
            patch.object(legacy_sender, "get_access_token", return_value=""),
            patch.object(legacy_sender, "get_last_error", return_value="token denied"),
        ):
            token_result = await legacy_sender.send_markdown_template(
                "https://api.example.com/messages",
                "app",
                "secret",
                "template",
                [],
                [],
            )

        client = self._Client(error=RuntimeError("network down"))
        with (
            patch.object(legacy_sender, "get_access_token", return_value="runtime-token"),
            patch.object(
                legacy_sender,
                "get_token_manager",
                return_value=self._TokenManager(),
            ),
            patch("qq_restapi.runtime.sender.get_async_client", return_value=client),
            patch("qq_restapi.runtime.sender.logger.warning"),
        ):
            transport_result = await legacy_sender.send_markdown_template(
                "https://api.example.com/messages",
                "app",
                "secret",
                "template",
                [],
                [],
            )

        self.assertEqual(token_result, (0, "token denied"))
        self.assertEqual(transport_result, (0, "发送失败: network down"))


if __name__ == "__main__":
    unittest.main()
