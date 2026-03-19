set -euo pipefail

echo "Creating k3d cluster (edge-like, K3s)..."
k3d cluster create edge-vnf \
  --servers 1 \
  --port "31080:31080@server:0" \
  --port "31090:31090@server:0" \
  --port "31300:31300@server:0" \
  --k3s-arg "--disable=traefik@server:0"

kubectl config use-context k3d-edge-vnf

echo "Deploying NGINX LB VNF + Prometheus + Grafana..."
kubectl apply -f "$(dirname "$0")/k8s.yaml"

echo "Waiting for pods to be ready..."
kubectl rollout status deployment/nginx-lb   -n vnf-edge --timeout=180s
kubectl rollout status deployment/backend    -n vnf-edge --timeout=180s
kubectl rollout status deployment/prometheus -n vnf-edge --timeout=180s
kubectl rollout status deployment/grafana    -n vnf-edge --timeout=180s

echo ""
echo "Done! Access URLs:"
echo "  NGINX LB  : http://localhost:31080"
echo "  Prometheus: http://localhost:31090"
echo "  Grafana   : http://localhost:31300   (login: admin / admin)"
echo ""
echo "Hello-World test:"
sleep 2 && curl -s http://localhost:31080 | head -2
