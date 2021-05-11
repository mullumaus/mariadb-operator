# mariadb

## Description

MariaDB-k8s charm deploying and managing MariaDB on Kubernetes.

## Usage

### Deploying
    $git clone https://github.com/mullumaus/mariadb-operator
    $cd mariadb-operator
    $ charmcraft pack
    Created 'mariadb.charm'.
    $juju deploy ./mariadb.charm --resource mariadb-image=mariadb

    $  juju status
    Model        Controller  Cloud/Region        Version  SLA          Timestamp
    development  micro       microk8s/localhost  2.9.0    unsupported  20:52:16+10:00

    App      Version  Status  Scale  Charm    Store  Channel  Rev  OS          Address  Message
    mariadb  mariadb  active      1  mariadb  local            31  kubernetes           

    Unit        Workload  Agent  Address     Ports  Message
    mariadb/0*  active    idle   10.1.49.14        

## Developing

Create and activate a virtualenv with the development requirements:

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

## Debugging
To check the logs generated by MariaDB

    # The juju model in which MariaDB is installed corresponds to the k8s namespace
    $ kubectl  get pods --namespace development
    NAME                             READY   STATUS    RESTARTS   AGE
    modeloperator-77b996d87b-hkj2t   1/1     Running   0          5h26m
    mariadb-0                        2/2     Running   0          21m

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

    ./run_tests
# mariadb-operator
