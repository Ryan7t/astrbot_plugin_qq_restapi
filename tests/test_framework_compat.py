from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_ASTRBOT_ROOT = _PLUGIN_ROOT.parents[2]
for _path in (_PLUGIN_ROOT.parent, _ASTRBOT_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from qq_restapi.runtime.framework_compat import (  # noqa: E402
    MIN_ASTRBOT_VERSION,
    ensure_supported_astrbot,
)


class FrameworkCompatibilityTests(unittest.TestCase):
    def test_required_framework_features_are_accepted(self):
        modules = {
            "astrbot.core.utils.media_utils": SimpleNamespace(MediaResolver=object()),
            "astrbot.core.platform.webhook_server": SimpleNamespace(
                FastAPIWebhookServer=object()
            ),
        }

        with patch(
            "qq_restapi.runtime.framework_compat.import_module",
            side_effect=modules.__getitem__,
        ) as importer:
            ensure_supported_astrbot()

        self.assertEqual(importer.call_count, 2)

    def test_import_failure_reports_version_and_mixed_framework_files(self):
        original_error = ImportError(
            "cannot import name 'audio_to_tencent_silk_base64'"
        )

        with (
            patch(
                "qq_restapi.runtime.framework_compat.import_module",
                side_effect=original_error,
            ),
            self.assertRaises(RuntimeError) as raised,
        ):
            ensure_supported_astrbot()

        message = str(raised.exception)
        self.assertIn(f"AstrBot >= {MIN_ASTRBOT_VERSION}", message)
        self.assertIn("框架文件发生混装", message)
        self.assertIn("audio_to_tencent_silk_base64", message)
        self.assertIs(raised.exception.__cause__, original_error)

    def test_missing_required_attribute_is_reported(self):
        with (
            patch(
                "qq_restapi.runtime.framework_compat.import_module",
                return_value=SimpleNamespace(),
            ),
            self.assertRaises(RuntimeError) as raised,
        ):
            ensure_supported_astrbot()

        self.assertIn("MediaResolver", str(raised.exception))


class ReleaseMetadataTests(unittest.TestCase):
    def test_release_version_and_minimum_astrbot_version_are_aligned(self):
        metadata = (_PLUGIN_ROOT / "metadata.yaml").read_text(encoding="utf-8")
        main_source = (_PLUGIN_ROOT / "main.py").read_text(encoding="utf-8")

        self.assertRegex(metadata, r"(?m)^version:\s*v0\.1\.1\b")
        self.assertRegex(metadata, r'(?m)^astrbot_version:\s*">=4\.26\.0"')
        self.assertRegex(
            main_source,
            r'@register\([^\n]+"0\.1\.1"\)',
        )

    def test_legacy_audio_helper_is_not_reintroduced(self):
        event_source = (
            _PLUGIN_ROOT / "runtime" / "qq_restapi_event.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("audio_to_tencent_silk_base64", event_source)
        self.assertIn("MediaResolver", event_source)


if __name__ == "__main__":
    unittest.main()
