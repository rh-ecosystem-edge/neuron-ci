# AWS Neuron Operator CI - Cluster Lifecycle Management
#
# Mirrors the amd-ci pattern: separate Makefile targets for operator
# installation and cleanup, invoked by step-registry scripts.

# Install NFD, KMM, Neuron operator, create NFD instance/rule, DeviceConfig,
# and wait for Neuron device resources.  Reads image versions from env vars
# (ECO_HWACCEL_NEURON_DRIVERS_IMAGE, etc.).
cluster-operators:
	python3 -m operators install

# Reverse of cluster-operators: remove DeviceConfig, NFD rule, operators.
cluster-cleanup:
	python3 -m operators cleanup

.PHONY: cluster-operators cluster-cleanup
