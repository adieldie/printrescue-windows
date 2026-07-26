import unittest

from printrescue.models import PrinterProfile


class PublicDefaultsTests(unittest.TestCase):
    def test_defaults_are_generic_examples(self):
        profile = PrinterProfile()
        self.assertEqual(profile.server_name, "PRINT-SERVER")
        self.assertEqual(profile.server_ip, "192.168.1.50")
        self.assertEqual(profile.share_name, "SharedPrinter")
        self.assertEqual(profile.network_user, "PrinterUser")

    def test_no_password_field_exists(self):
        fields = set(PrinterProfile.__dataclass_fields__)
        self.assertNotIn("password", fields)
        self.assertNotIn("senha", fields)


if __name__ == "__main__":
    unittest.main()
