#!/usr/bin/env python3
# Copyright 2021 lihuiguo
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    WaitingStatus,
    MaintenanceStatus,
    ModelError
)
from ops.pebble import ServiceStatus
import secrets
import string

# from charms.osm.k8s import is_pod_up, get_service_ip

logger = logging.getLogger(__name__)

SERVICE = "mariadb"
COMMAND = "/usr/local/bin/docker-entrypoint.sh mysqld"


class MariadbCharm(CharmBase):
    """A Juju Charm to deploy MariaDB on Kubernetes

    This charm has the following features:
    - Add one more MariaDB units
    - Config port of MariaDB
    - Provides a database relation for any MariaDB client
    """

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.mariadb_pebble_ready,
                               self._on_mariadb_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.restart_action, self._on_restart_action)
        self.framework.observe(self.on.backup_action, self._on_backup_action)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on["peer"].relation_joined, self._on_config_changed)
        self.framework.observe(self.on["peer"].relation_departed, self._on_config_changed)
        self.framework.observe(self.on["database"].relation_changed,
                               self._on_database_relation_changed)

        self._stored.set_default(database={})
        self._stored.set_default(root_password=self._gen_root_password())
        self._stored.set_default(ports=[self.model.config['port']])

    def _on_mariadb_pebble_ready(self, event):
        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        # Define an initial Pebble layer configuration
        pebble_layer = {
            "summary": "mariadb layer",
            "description": "pebble config layer for mariadb",
            "services": {
                "mariadb": {
                    "override": "replace",
                    "summary": "mariadb",
                    "command": COMMAND,
                    "startup": "enabled",
                    "environment": {
                        "MYSQL_ROOT_PASSWORD": self._stored.root_password,
                    },
                }
            },
        }

        # Add Pebble config layer using the Pebble API
        container.add_layer("mariadb", pebble_layer, combine=True)
        # Autostart any services that were defined with startup: enabled
        container.autostart()
        self.unit.status = ActiveStatus()

    def _on_config_changed(self, event):
        """Configure MariaDB Pod specification

        A new MariaDB pod specification is set only if it is different
        from the current specification.
        """
        self._stored.ports = [self.model.config['port']]
        self._on_update_status(event)

    def _on_database_relation_changed(self, event):
        event.relation.data[self.unit]['root-password'] = self._stored.root_password

    def _gen_root_password(self):
        """generate mariadb root password
        """
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for i in range(16))
        return password

    def _on_update_status(self, event):
        """Set status for all units
        """
        if not self.unit.is_leader():
            self.unit.status = ActiveStatus()
            return

        if not self._is_ready():
            status_message = "service not ready yet"
            self.unit.status = WaitingStatus(status_message)
            return
        self.unit.status = ActiveStatus()

    def _is_ready(self):
        """check service is running
        """
        container = self.unit.get_container(SERVICE)
        return container.get_service(SERVICE).is_running()

    ##############################################
    #               Actions                      #
    ##############################################
    def _on_restart_action(self, event):
        """restart mariadb service
        """
        logger.info("Restarting mariadb ...")
        print("event{}".format(event))
        try:
            container = self.unit.get_container(SERVICE)
            status = container.get_service(SERVICE)
            if status.current == ServiceStatus.ACTIVE:
                container.stop(SERVICE)

            self.unit.status = MaintenanceStatus("mariadb maintenance")
            container.start(SERVICE)
            self.unit.status = ActiveStatus("mariadb restarted")
            event.set_results(event.params)
        except ModelError:
            event.fail(event.params['fail'])
            event.set_results(event.params)
            return False

    def _on_backup_action(self, event):
        pass
    #     """ Backup database
    #     """
    #     backup_path = "/var/lib/mysql"
    #     password = self._stored.root_password
        # backup_cmd = "mysqldump -u root -p$ROOT_PASSWORD --single-transaction
        # --all-databases | gzip > $DB_BACKUP_PATH/backup.sql.gz || action-fail "Backup failed""


if __name__ == "__main__":
    main(MariadbCharm, use_juju_for_storage=True)
