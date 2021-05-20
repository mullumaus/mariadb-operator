# Copyright 2021 lihuiguo
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import Mock
from charm import MariadbCharm
from ops.model import ActiveStatus
from ops.testing import Harness
from charm import COMMAND


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MariadbCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_config_changed(self):
        self.assertEqual(list(self.harness.charm._stored.ports), [])
        self.harness.update_config({"port": 4000})
        self.assertEqual(list(self.harness.charm._stored.ports), [4000])

    # def test_action(self):
    #     # the harness doesn't (yet!) help much with actions themselves
    #     action_event = Mock(params={"fail": ""})
    #     self.harness.charm._on_restart_action(action_event)

    #     self.assertTrue(action_event.set_results.called)

    # def test_action_fail(self):
    #     action_event = Mock(params={"fail": "fail this"})
    #     self.harness.charm._on_restart_action(action_event)

    #     self.assertEqual(action_event.fail.call_args, [("fail this",)])

    def test_mariadb_pebble_ready(self):
        # Check the initial Pebble plan is empty
        initial_plan = self.harness.get_container_pebble_plan("mariadb")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")
        # Expected plan after Pebble ready with default config
        expected_plan = {
            "services": {
                "mariadb": {
                    "override": "replace",
                    "summary": "mariadb",
                    "command": COMMAND,
                    "startup": "enabled",
                    "environment": {
                        "MYSQL_ROOT_PASSWORD": self.harness.charm._stored.root_password,
                    },
                }
            },
        }
        # Get the mariadb container from the model
        container = self.harness.model.unit.get_container("mariadb")
        # Emit the PebbleReadyEvent carrying the mariadb container
        self.harness.charm.on.mariadb_pebble_ready.emit(container)
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("mariadb").to_dict()
        # Check we've got the plan we expected
        print("\nupdated_plan={}".format(updated_plan))
        print("\nexpected_plan={}".format(expected_plan))
        self.assertEqual(expected_plan, updated_plan)
        # Check the service was started
        service = self.harness.model.unit.get_container("mariadb").get_service("mariadb")
        self.assertTrue(service.is_running())
        # Ensure we set an ActiveStatus with no message
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_action(self):
        # the harness doesn't (yet!) help much with actions themselves
        action_event = Mock(params={"fail": ""})
        self.harness.charm._on_restart_action(action_event)

        self.assertTrue(action_event.set_results.called)

    def test_action_fail(self):
        action_event = Mock(params={"fail": "fail this"})
        self.harness.charm._on_restart_action(action_event)

        self.assertEqual(action_event.fail.call_args, [("fail this",)])
