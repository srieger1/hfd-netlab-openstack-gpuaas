#!/usr/bin/python3

# example to start an instance that offers NVIDIA cards using direct pci passthrough in the OpenStack environment of NetLab - Hochschule Fulda
#
# The script uses standard OpenStack Python API:
# - https://docs.openstack.org/openstacksdk/latest/user/guides/intro.html
# Alternatives that can be also be used to start instances are:
# - OpenStack Web Interface (Horizon): https://private-cloud.informatik.hs-fulda.de/
# - OpenStack CLI client (use, e.g. "pip install openstack"): https://docs.openstack.org/newton/user-guide/common/cli-install-openstack-command-line-clients.html
# - terraform OpenStack provider: https://registry.terraform.io/providers/terraform-provider-openstack/openstack/latest/docs
# - pulumi OpenStack provider: https://www.pulumi.com/registry/packages/openstack/
# - Apache libcloud: https://libcloud.apache.org/
# - ... ;)
#
# The script expects a "clouds.yaml" file in the working directory containing credentials and API endpoints for OpenStack.
# Be sure to use the "05)_AI-NetLab-Pro" VPN profile if you are using a network outside of Hochschule Fulda to be able to access our OpenStack env.
# https://private-cloud.informatik.hs-fulda.de/project/api_access/clouds.yaml
# You can add the password to clouds.yaml. See https://docs.openstack.org/python-openstackclient/latest/configuration/index.html
#
# After running the script you will get SSH access to an instance that offers direct PCI access (passthrough) to one of our NVIDIA RTX GPUs.
# nvidia drivers and cuda are automatically installed (see cloud-init definition in the USERDATA var below). You can change the var content
# to execute further tasks/install packages/fetch data/run experiments/submit results etc.
#
# Using SSH to login to the instance after stating it you will see the installation process defined in USERDATA running. As soon as you are able
# to run "nvidia-smi" the process is finished. You can also snapshot the instance at this point and use the snapshot for subsequent runs, to speed
# up the instance start.
#
# Currently only flavor g1.medium is offered, but further flavors with other CPU, memory, storage resources etc. are possible. Also multiple GPUs
# are possible in a single instance.
#
# Instances are currently limited to run max. for one week to allow others to also use the GPUs. Instances are automatically "shelved" after one
# week, effectively snapshotting/suspending their disk state. You can use the "unshelve" operation to get them running again if nobody else reserved
# GPUs meanwhile.


import openstack
import os
import sys


###########################
#
# Config
#
###########################

if len(sys.argv) < 3:
    print("usage: %s <openstack-username> <instance-name>" % sys.argv[0])
    exit(-1)

INSTANCE_NAME = sys.argv[2]

IMAGE_NAME = "Ubuntu 20.04 - Focal Fossa - 64-bit - Cloud Based Image"
# You can also use/upload other images for recent Linux distros (see, e.g., https://cloud-images.ubuntu.com/)
#
# To use a prepared image that already has nvidia drivers and cuda installed, use the image here.
# You can create a new image by creating a snapshot of the instance that was started by this script
# Snapshot can be created using CLI/API or web interface of OpenStack
# IMAGE_NAME="my-snapshot-with-nvidia-stuff-installed"

FLAVOR_NAME = "g1.medium"

NETWORK_NAME = sys.argv[1] + "-net"

KEYPAIR_NAME = "gpuaas-keypair"
PRIVATE_KEYPAIR_FILE = "nvidia-test-keypair.key"
# To use an existing keypair uncomment the following line and change it appropriately:
# IMPORT_EXISTING_PUBKEY_FILE = "~/.ssh/id_rsa.pub"
IMPORT_EXISTING_PUBKEY_FILE = ""

# initial installation using cloud-init
#
# to use other nvidia dirver/cuda versions etc., see nvidia documentation for ubuntu setup:
#   - https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html
#   - https://developer.nvidia.com/cuda-downloads?target_os=Linux&target_arch=x86_64&Distribution=Ubuntu&target_version=20.04&target_type=runfile_local
USERDATA = "#!/bin/bash\n" \
           "sudo apt update\n" \
           "sudo apt install -y build-essential\n" \
           "wget https://developer.download.nvidia.com/compute/cuda/11.7.0/local_installers/cuda_11.7.0_515.43.04_linux.run\n" \
           "sudo sh /cuda_11.7.0_515.43.04_linux.run --silent --driver --toolkit --samples\n" \
           "nvidia-smi\n" \


###########################
#
# Code
#
###########################

def get_keypair(conn):
    keypair = conn.compute.find_keypair(KEYPAIR_NAME)

    if not keypair:
        if IMPORT_EXISTING_PUBKEY_FILE != "":
            print("Importing public key from %s" % (IMPORT_EXISTING_PUBKEY_FILE))

            with open(os.path.expanduser(IMPORT_EXISTING_PUBKEY_FILE), 'r') as f:
                pubkey = f.read()
                keypair = conn.compute.create_keypair(name=KEYPAIR_NAME, public_key=pubkey)
                ssh_privkey = "<private key corresponding to " + IMPORT_EXISTING_PUBKEY_FILE + ">"

        else:
            print("Create Key Pair:")

            keypair = conn.compute.create_keypair(name=KEYPAIR_NAME)

            print(keypair)

            with open(PRIVATE_KEYPAIR_FILE, 'w') as f:
                f.write("%s" % keypair.private_key)

            os.chmod(PRIVATE_KEYPAIR_FILE, 0o400)
            ssh_privkey = PRIVATE_KEYPAIR_FILE
    else:
        ssh_privkey = "<private key corresponding to existing " + keypair.name + ">"

    return keypair, ssh_privkey

# Initialize and turn on debug logging
# openstack.enable_logging(debug=True)

# Initialize connection
conn = openstack.connect(cloud='openstack')

image = conn.compute.find_image(IMAGE_NAME)
flavor = conn.compute.find_flavor(FLAVOR_NAME)
network = conn.network.find_network(NETWORK_NAME)
keypair, ssh_privkey = get_keypair(conn)

# Boot a server, wait for it to boot, and then do whatever is needed
# to get a public IP address for it.

# delete server if it already exists
conn.delete_server(INSTANCE_NAME)

server = conn.create_server(
  INSTANCE_NAME, image=image, flavor=flavor, network=network, key_name=keypair.name, userdata=USERDATA, wait=True, auto_ip=True)
print("Server instance started:\n\n%s" % server)

print("\n\nLogin using, e.g.:\n\nssh -i {key} ubuntu@{ip}".format(
  key=ssh_privkey,
  ip=server.public_v4))
