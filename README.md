# COMP5123M CW2 – NGINX Load Balancer VNF on Kubernetes

**VNF:** NGINX Load Balancer (Layer-7 HTTP proxy)  
**Cloud:** Minikube (full Kubernetes)  
**Edge:** k3d / K3s (lightweight Kubernetes)

## Structure
```
CW2/
├── cloud/
│   ├── setup.sh     # start Minikube + deploy everything
│   └── k8s.yaml     # all Kubernetes manifests (cloud)
├── edge/
│   ├── setup.sh     # start k3d + deploy everything
│   └── k8s.yaml     # all Kubernetes manifests (edge)
├── test.py          # traffic generator + metrics + charts
├── report.md        # answers to all assessment questions
└── GenAI_troubleshooting.md
```

## Prerequisites
```bash
# Install (Mac)
brew install minikube k3d kubectl
pip3 install matplotlib requests

# Install (Windows – PowerShell as Admin)
winget install Kubernetes.minikube k3d.k3d Kubernetes.kubectl
pip install matplotlib requests
```
Docker Desktop must be running before any commands below.

## Quickstart
```bash
# 1. Cloud environment
cd cloud && bash setup.sh

# 2. Edge environment (new terminal)
cd edge && bash setup.sh

# 3. Hello-World test
curl $(minikube service nginx-lb-svc -n vnf-cloud --profile=cloud-vnf --url)
curl http://localhost:31080

# 4. Run all performance tests
python3 test.py --cloud $(minikube service nginx-lb-svc -n vnf-cloud --profile=cloud-vnf --url) \
                --edge http://localhost:31080

# Charts saved to results/
```

## Teardown
```bash
minikube delete --profile=cloud-vnf
k3d cluster delete edge-vnf
```
