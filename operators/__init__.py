"""AWS Neuron Operator installation orchestration for OpenShift.

Provides `make cluster-operators` functionality: installs NFD, KMM, and the
AWS Neuron Operator via OLM, creates required CRs (NodeFeatureDiscovery,
NodeFeatureRule, DeviceConfig), and waits for Neuron device resources to
become available on worker nodes.
"""
