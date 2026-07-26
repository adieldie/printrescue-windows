import unittest

from printrescue.models import CheckResult, PrinterProfile


class PrinterProfileTests(unittest.TestCase):
    def test_round_trip(self):
        profile = PrinterProfile(
            name="Lab",
            server_name="PRINT-SERVER",
            server_ip="192.168.1.50",
            share_name="SharedPrinter",
            network_user="PrinterUser",
            local_printer_name="Office Printer",
            expected_driver="Printer Driver",
            client_queue_name="Office Printer (PRINT-SERVER)",
        )

        restored = PrinterProfile.from_dict(profile.to_dict())
        self.assertEqual(restored, profile)

    def test_ignores_unknown_fields(self):
        profile = PrinterProfile.from_dict(
            {
                "name": "Example",
                "server_name": "SERVER",
                "unknown": "ignored",
            }
        )
        self.assertEqual(profile.name, "Example")
        self.assertEqual(profile.server_name, "SERVER")

    def test_check_result_serialization(self):
        result = CheckResult(
            key="network",
            title="Network",
            status="ok",
            detail="Available",
        )
        self.assertEqual(result.to_dict()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
