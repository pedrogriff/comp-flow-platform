"""Unit tests for CLI commands and Argument Parser."""

import unittest

from comp_flow.cli.main import build_parser


class TestCLI(unittest.TestCase):
    """Test suite for CLI command dispatch."""

    def setUp(self) -> None:
        self.parser = build_parser()

    def test_serve_command_args(self) -> None:
        """Verifies parsing of serve arguments."""
        args = self.parser.parse_args(
            ["serve", "--host", "127.0.0.1", "--port", "8080", "--reload"]
        )
        self.assertEqual(args.command, "serve")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8080)
        self.assertTrue(args.reload)

    def test_seed_command_args(self) -> None:
        """Verifies parsing of seed command."""
        args = self.parser.parse_args(["seed"])
        self.assertEqual(args.command, "seed")

    def test_init_db_command_args(self) -> None:
        """Verifies parsing of init-db command."""
        args = self.parser.parse_args(["init-db"])
        self.assertEqual(args.command, "init-db")


if __name__ == "__main__":
    unittest.main()
