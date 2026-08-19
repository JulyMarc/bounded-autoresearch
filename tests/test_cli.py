from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from bounded_autoresearch.cli import main


class CliTests(unittest.TestCase):
    def test_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "demo"
            self.assertEqual(main(["init", str(run), "--objective", "Test", "--metric", "score", "--direction", "maximize"]), 0)
            self.assertEqual(main(["validate", str(run)]), 0)
            json_output = StringIO()
            with redirect_stdout(json_output):
                self.assertEqual(main(["validate", str(run), "--json"]), 0)
            self.assertIn('"ok": true', json_output.getvalue())
            output = StringIO()
            with redirect_stdout(output):
                code = main(["resume", str(run)])
            self.assertEqual(code, 0)
            self.assertIn("Status: initialized", output.getvalue())
            self.assertEqual(main(["checkpoint", str(run), "--status", "running", "--next-action", "Run E00"]), 0)
            self.assertEqual(main(["record-experiment", str(run), "--id", "E00", "--outcome", "success", "--metric-value", "1.0", "--verified", "--prediction", "baseline", "--gate", "deterministic"]), 0)
            self.assertEqual(main(["finish", str(run), "--status", "stopped", "--note", "Budget closed"]), 0)
            self.assertEqual(main(["checkpoint", str(run), "--status", "running", "--next-action", "Unsafe"]), 2)


if __name__ == "__main__":
    unittest.main()
