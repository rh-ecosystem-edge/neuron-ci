# neuron-ci

CI tests for AWS Neuron operators on OpenShift.


This repository contains CI configuration for running Neuron operator tests
using the eco-gotests framework on ROSA HCP clusters with Inferentia/Trainium types of nodes.

## DRA installation mode

Set `ECO_HWACCEL_NEURON_DRA_DRIVER_IMAGE` to install the DRA-capable OLM
versions of KMM and the Neuron operator. The Prow install step downloads
`deviceconfig-sample.yaml` from the latest Neuron operator release and uses it
for the kernel driver and metrics images. It derives the driver version for
the DRA in-cluster-build test without adding that removed field to the initial
prebuilt-image DeviceConfig. The installer replaces the
device-plugin and scheduler fields with `draDriverImage`, then waits for the
DRA DaemonSet, DeviceClass, and ResourceSlices.

```bash
export ECO_HWACCEL_NEURON_DRA_DRIVER_IMAGE=public.ecr.aws/neuron/neuron-dra-driver:1.0.1
export ECO_HWACCEL_NEURON_DRA_UPGRADE_DRIVER_IMAGE=public.ecr.aws/neuron/neuron-dra-driver:1.2.0
make cluster-operators
```

For local runs, also export the kernel driver, driver version, and metrics
values from the desired release's `deviceconfig-sample.yaml` before invoking
`make cluster-operators`.
