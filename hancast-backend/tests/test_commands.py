"""
测试所有命令
"""

import unittest
from hancast_sidecar.commands import CommandHandler


class TestCommands(unittest.TestCase):
    """测试命令"""

    def setUp(self):
        self.handler = CommandHandler()

    def tearDown(self):
        self.handler.cleanup()

    def test_get_devices(self):
        """测试获取设备列表"""
        result = self.handler.execute("get_devices", {})
        self.assertIsInstance(result, list)

    def test_refresh_devices(self):
        """测试刷新设备"""
        result = self.handler.execute("refresh_devices", {})
        self.assertIsInstance(result, list)

    def test_set_default_device(self):
        """测试设置默认设备"""
        result = self.handler.execute("set_default_device", {"id": "test-id"})
        self.assertIsNone(result)

    def test_rename_device(self):
        """测试重命名设备"""
        result = self.handler.execute("rename_device", {"id": "test-id", "name": "New Name"})
        self.assertIsNone(result)

    def test_remove_device(self):
        """测试移除设备"""
        result = self.handler.execute("remove_device", {"id": "test-id"})
        self.assertIsNone(result)

    def test_get_cast_state(self):
        """测试获取投屏状态"""
        result = self.handler.execute("get_cast_state", {})
        self.assertIn("status", result)
        self.assertIn("volume", result)
        self.assertIn("is_muted", result)

    def test_set_volume(self):
        """测试设置音量"""
        result = self.handler.execute("set_volume", {"volume": 50})
        self.assertIsNone(result)

        # 验证音量已更改
        state = self.handler.execute("get_cast_state", {})
        self.assertEqual(state["volume"], 50)

    def test_set_mute(self):
        """测试设置静音"""
        result = self.handler.execute("set_mute", {"muted": True})
        self.assertIsNone(result)

        # 验证静音已更改
        state = self.handler.execute("get_cast_state", {})
        self.assertTrue(state["is_muted"])

    def test_get_settings(self):
        """测试获取设置"""
        result = self.handler.execute("get_settings", {})
        self.assertIn("usn", result)
        self.assertIn("friendly_name", result)
        self.assertIn("version", result)

    def test_save_settings(self):
        """测试保存设置"""
        result = self.handler.execute("save_settings", {
            "settings": {"test_key": "test_value"}
        })
        self.assertIsNone(result)

        # 验证设置已保存
        settings = self.handler.execute("get_settings", {})
        self.assertEqual(settings["settings"]["test_key"], "test_value")

    def test_parse_media_file_not_found(self):
        """测试解析不存在的文件"""
        with self.assertRaises(Exception) as context:
            self.handler.execute("parse_media", {
                "type": "file",
                "path": "/nonexistent/file.mp4"
            })
        self.assertIn("File not found", str(context.exception))

    def test_parse_media_url_invalid(self):
        """测试解析无效 URL"""
        with self.assertRaises(Exception) as context:
            self.handler.execute("parse_media", {
                "type": "url",
                "url": "not-a-url"
            })
        self.assertIn("Invalid URL", str(context.exception))

    def test_unknown_command(self):
        """测试未知命令"""
        with self.assertRaises(ValueError) as context:
            self.handler.execute("unknown_cmd", {})
        self.assertIn("Unknown command", str(context.exception))


if __name__ == '__main__':
    unittest.main()
