set -euo pipefail

echo "Starting Minikube (cloud-like, 2 CPU / 4 GB)..."
minikube start --profile=cloud-vnf --driver=docker --cpus=2 --memory=4096
minikube addons enable metrics-server --profile=cloud-vnf
kubectl config use-context cloud-vnf

echo "Deploying NGINX LB VNF + Prometheus + Grafana..."
kubectl apply -f "$(dirname "$0")/k8s.yaml"

echo "Waiting for pods to be ready..."
kubectl rollout status deployment/nginx-lb   -n vnf-cloud --timeout=120s
kubectl rollout status deployment/backend    -n vnf-cloud --timeout=120s
kubectl rollout status deployment/prometheus -n vnf-cloud --timeout=120s
kubectl rollout status deployment/grafana    -n vnf-cloud --timeout=120s

echo ""
echo "Done! Access URLs:"
NGINX_URL=$(minikube service nginx-lb-svc  -n vnf-cloud --profile=cloud-vnf --url 2>/dev/null)
PROM_URL=$(minikube service prometheus-svc -n vnf-cloud --profile=cloud-vnf --url 2>/dev/null)
GRAF_URL=$(minikube service grafana-svc    -n vnf-cloud --profile=cloud-vnf --url 2>/dev/null)
echo "  NGINX LB  : $NGINX_URL"
echo "  Prometheus: $PROM_URL"
echo "  Grafana   : $GRAF_URL   (login: admin / admin)"
echo ""
echo "Hello-World test:"
curl -s "$NGINX_URL" | head -2
