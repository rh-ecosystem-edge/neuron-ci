"""Constants extracted from eco-gotests params/consts.go and neuronhelpers/deploy.go."""

# Namespaces
NAMESPACE_NFD = "openshift-nfd"
NAMESPACE_KMM = "openshift-kmm"
NAMESPACE_NEURON = "aws-neuron-operator"
NAMESPACE_MONITORING = "openshift-monitoring"
NAMESPACE_USER_WORKLOAD_MONITORING = "openshift-user-workload-monitoring"

# NFD operator
NFD_PACKAGE = "nfd"
NFD_CATALOG = "redhat-operators"
NFD_CHANNEL = "stable"
NFD_OPERATOR_GROUP = "nfd-operator-group"
NFD_SUBSCRIPTION = "nfd-subscription"
NFD_INSTANCE_NAME = "nfd-instance"

# KMM operator
KMM_PACKAGE = "kernel-module-management"
KMM_CATALOG = "redhat-operators"
KMM_CHANNEL = "stable"
KMM_OPERATOR_GROUP = "kmm-operator-group"
KMM_SUBSCRIPTION = "kmm-subscription"

# Neuron operator
NEURON_PACKAGE = "aws-neuron-operator"
NEURON_CATALOG = "community-operators"
NEURON_CHANNEL = "Fast"
NEURON_OPERATOR_GROUP = "neuron-operator-group"
NEURON_SUBSCRIPTION = "neuron-subscription"

# NFD rule for Neuron PCI device detection
NFD_RULE_NAME = "neuron-nfd-rule"
NFD_LABEL_KEY = "feature.node.kubernetes.io/aws-neuron"
NFD_LABEL_VALUE = "true"
PCI_VENDOR_ID = "1d0f"
DEVICE_IDS = ["7064", "7065", "7066", "7067", "7164", "7264", "7364"]

# DeviceConfig
DEVICE_CONFIG_NAME = "neuron"
DEVICE_CONFIG_API_VERSION = "k8s.aws/v1beta1"

# Kubernetes resource names
NEURON_CAPACITY_ID = "aws.amazon.com/neuron"
DEVICE_PLUGIN_PREFIX = "neuron-device-plugin"

# OLM
CATALOG_NAMESPACE = "openshift-marketplace"
