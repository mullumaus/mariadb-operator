#!/usr/bin/env python3
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
import subprocess
from datetime import datetime
import glob
import os

logger = logging.getLogger(__name__)

SERVICE = "mariadb"
COMMAND = "/usr/local/bin/docker-entrypoint.sh mysqld"
DB_BACKUP_PATH = "/data/db"


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
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.restart_action, self._on_restart_action)
        self.framework.observe(self.on.backup_action, self._on_backup_action)
        self.framework.observe(self.on.listbackup_action, self._on_list_backup)
        self.framework.observe(self.on.restore_action, self._on_restore_action)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on["peer"].relation_joined, self._on_config_changed)
        self.framework.observe(self.on["peer"].relation_departed, self._on_config_changed)
        self.framework.observe(self.on["database"].relation_changed,
                               self._on_database_relation_changed)

        self._stored.set_default(database={})
        self._stored.set_default(ports=[self.model.config['port']])
        self._stored.set_default(root_password=self._gen_root_password())

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

    def _on_install(self, event):
        subprocess.check_call(['apt-get', 'update'])
        subprocess.check_call(["apt-get", "install", "-y", "mysql-client"])

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
        """check if service is running
        """
        try:
            container = self.unit.get_container(SERVICE)
            return container.get_service(SERVICE).is_running()
        except ModelError:
            return False

    def _get_ip(self):
        """Get unit IP address
        """
        try:
            # addr = str(self.model.get_binding(event.relation).network.bind_address)
            addr = subprocess.check_output(["unit-get",
                                           "private-address"]).decode().strip()
            return addr
        except ModelError:
            return None

    def _set_fail_message(self, event, msg):
        if event.params['fail'] is None:
            event.params['fail'] = msg
        event.fail(event.params['fail'])
        event.set_results(event.params)

    ##############################################
    #               Actions                      #
    ##############################################
    def _on_restart_action(self, event):
        """restart mariadb service
        """
        logger.info("Restarting mariadb ...")
        try:
            container = self.unit.get_container(SERVICE)
            status = container.get_service(SERVICE)
            if status.current == ServiceStatus.ACTIVE:
                container.stop(SERVICE)

            self.unit.status = MaintenanceStatus("mariadb maintenance")
            container.start(SERVICE)
            self.unit.status = ActiveStatus("mariadb restarted")
            event.set_results(event.params)
        except ModelError as e:
            self._set_fail_message(event, str(e))

    def _on_backup_action(self, event):
        """ Backup database
        """
        date_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = "{}/{}-backup.sql.gz".format(DB_BACKUP_PATH, date_str)
        password = self._stored.root_password
        subprocess.check_output("mkdir -p {}".format(DB_BACKUP_PATH),
                                stderr=subprocess.STDOUT, shell=True)
        ip = self._get_ip()

        backup_cmd = """mysqldump -uroot -p{} -h{} --single-transaction \
                    --all-databases | gzip - > {}
                    """.format(password, ip, backup_name)
        try:
            subprocess.check_output(backup_cmd,
                                    stderr=subprocess.STDOUT, shell=True)
            message = {"message": "backup {}".format(backup_name)}
            event.set_results(message)
        except subprocess.CalledProcessError as e:
            self._set_fail_message(event, e.output)
            logger.error(e.output)

    def _on_list_backup(self, event):
        """ List backup files
        """
        try:
            output = subprocess.check_output("ls {}".format(DB_BACKUP_PATH),
                                             stderr=subprocess.STDOUT, shell=True)
            output = output.decode().strip().split("\n")
            message = {"message": "backup files: {}".format(output)}
            event.set_results(message)
        except subprocess.CalledProcessError as e:
            self._set_fail_message(event, e.output)

    def _on_restore_action(self, event):
        """Restore database
        """
        try:
            file = subprocess.check_output(["action-get",
                                            "path"]).decode().strip()
            if file is None or len(file) == 0:
                list_of_files = glob.glob('{}/*'.format(DB_BACKUP_PATH))
                restore_file = max(list_of_files, key=os.path.getctime)
            else:
                restore_file = "{}/{}".format(DB_BACKUP_PATH, file)
            ip = self._get_ip()
            password = self._stored.root_password
            command = "gunzip -c {}| mysql -uroot -p{} -h{}".format(restore_file, password, ip)
            subprocess.check_output(command,
                                    stderr=subprocess.STDOUT, shell=True)
            message = {"message": "restored {}".format(restore_file)}
            event.set_results(message)
        except subprocess.CalledProcessError as e:
            self._set_fail_message(event, e.output)
            logger.error(e.output)


if __name__ == "__main__":
    main(MariadbCharm, use_juju_for_storage=True)
