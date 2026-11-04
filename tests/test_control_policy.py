import importlib.util
import itertools
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("control_policy", Path(__file__).parents[1] / "components/keyframe/control_policy.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class RoutingTests(unittest.TestCase):
    def test_every_toggle_configuration_requires_an_explicit_route_when_ambiguous(self):
        for values in itertools.product([False, True], repeat=4):
            enabled = dict(zip(policy.MODES, values))
            active = [name for name, value in enabled.items() if value]
            auto = policy.choose_route(enabled)
            self.assertEqual(bool(auto["error"]), len(active) > 1)
            for chosen in policy.MODES:
                result = policy.choose_route(enabled, chosen)
                self.assertEqual(bool(result["error"]), chosen not in active)
                if chosen in active:
                    self.assertEqual(result["route"], chosen)
                    if len(active) > 1:
                        self.assertIn("previews only", result["status"])


if __name__ == "__main__":
    unittest.main()
