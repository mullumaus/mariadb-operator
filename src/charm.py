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
    BlockedStatus,
    WaitingStatus,
    MaintenanceStatus,
    ModelError
)
from ops.pebble import ServiceStatus, Layer
from oci_image import OCIImageResource, OCIImageResourceError
from mariadbserver import MariaDB, ROOT_USER, PORT
from charmhelpers.core import host
from charmhelpers.core.hookenv import (
    leader_set,
    leader_get,
)
# from charms.osm.k8s import is_pod_up, get_service_ip
# from charms.nginx_ingress_integrator.v0.ingress import IngressRequires

logger = logging.getLogger(__name__)

SERVICE = "mariadb"
COMMAND = "/usr/local/bin/docker-entrypoint.sh mysqld"

class MariadbCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()
    def __init__(self, *args):
        super().__init__(*args)

        self.image = OCIImageResource(self, "mariadb-image")

        self.framework.observe(self.on.mariadb_pebble_ready, self._on_mariadb_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.restart_action, self._on_restart_action)
        self.framework.observe(self.on["database"].relation_changed,
                               self._on_database_relation_changed)
            
        # self.ingress = IngressRequires(
        #     self,
        #     {
        #         "service-hostname": self.model.config["external_hostname"],
        #         "service-name": self.app.name,
        #         "service-port": PORT,
        #     },
        # )
    

        self._stored.set_default(database={})

    def _on_mariadb_pebble_ready(self, event):
        """Define and start a workload using the Pebble API.

        TEMPLATE-TODO: change this example to suit your needs.
        You'll need to specify the right entrypoint and environment
        configuration for your specific workload. Tip: you can see the
        standard entrypoint of an existing container using docker inspect

        Learn more about Pebble layers at https://github.com/canonical/pebble
        """
        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        root_password = self._gen_root_password()
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
                            "MYSQL_ROOT_PASSWORD": root_password,
                        },
                }
            },
        }
        
        leader_set({'root-password': root_password})
        # Add intial Pebble config layer using the Pebble API
        container.add_layer("mariadb", pebble_layer, combine=True)
        # Autostart any services that were defined with startup: enabled
        container.autostart()
        # Learn more about statuses in the SDK docs:
        # https://juju.is/docs/sdk/constructs#heading--statuses
        self.unit.status = ActiveStatus()

    def _on_config_changed(self, event):
        """Just an example to show how to deal with changed configuration.

        TEMPLATE-TODO: change this example to suit your needs.
        If you don't need to handle config, you can remove this method,
        the hook created in __init__.py for it, the corresponding test,
        and the config.py file.

        Learn more about config at https://juju.is/docs/sdk/config
        """
        # Continue only if the unit is the leader
        if not self.unit.is_leader():
            self._on_update_status(event)
            return

        pod_spec = self._make_pod_spec()
        self.model.pod.set_spec(pod_spec)
        self._on_update_status(event)

    def _on_database_relation_changed(self,event):
        event.relation.data[self.unit]['root-password'] = leader_get("root-password")

    def _gen_root_password(self):
        return host.pwgen(40)

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
        
    def _make_pod_spec(self):
        try:
            image_details = self.image.fetch()
            logger.info("using imageDetails: %s", image_details)
        except OCIImageResourceError:
            logger.exception("An error occurred while fetching the image info")
            self.unit.status = BlockedStatus("Error fetching image information")
            return {}
        
        ports = [
            {"name": "mariadb", "containerPort": self.model.config['port'], "protocol": "TCP"},
        ]

        service_account = self._make_service_account()

        return {
            "version": 3,
            "serviceAccount": service_account,
            "containers": [
                {
                    "name": self.model.app.name,
                    "imageDetails": image_details,
                    "imagePullPolicy": "Always",
                    "command": [COMMAND],
                    "ports": ports,
                }
            ],
            "kubernetesResources": {},
        }

    def _make_service_account(self):
        return {
            "roles": [
                {
                    "rules": [
                        {
                            "apiGroups": [""],
                            "resources": ["pods"],
                            "verbs": ["list"],
                        }
                    ]
                }
            ]
        }

    def _is_ready(self):
        try:
            container = self.unit.get_container(SERVICE)
            status = container.get_service(SERVICE)
            if status.current == ServiceStatus.ACTIVE:
                return True
        except ModelError:
            return False

    def _restart_mariadb(self):
        logger.info("Restarting mariadb ...")

        container = self.unit.get_container(SERVICE)

        # container.get_plan().to_yaml()
        status = container.get_service(SERVICE)
        if status.current == ServiceStatus.ACTIVE:
            container.stop(SERVICE)

        self.unit.status = MaintenanceStatus("mariadb maintenance")
        container.start(SERVICE)
        self.unit.status = ActiveStatus("mariadb restarted")

    ##############################################
    #               Actions                      #
    ##############################################

    def _on_restart_action(self, event):
        """Just an example to show how to receive actions.

        TEMPLATE-TODO: change this example to suit your needs.
        If you don't need to handle actions, you can remove this method,
        the hook created in __init__.py for it, the corresponding test,
        and the actions.py file.

        Learn more about actions at https://juju.is/docs/sdk/actions
        """
        self._restart_mariadb()
    ##############################################
    #               PROPERTIES                   #
    ##############################################

if __name__ == "__main__":
    main(MariadbCharm)
