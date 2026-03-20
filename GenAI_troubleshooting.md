# GenAI Troubleshooting Log

**Tool used:** M365 Microsoft Copilot (enterprise data protection enabled)
**Purpose:** Used only to help fix specific errors — not used to write 
code or complete any part of the coursework.

---

## Issues and fixes

| # | Problem | What I asked Copilot | Solution suggested | Did it work? |
|---|---------|---------------------|--------------------|--------------|
| 1 | After installing minikube, k3d, and kubectl using winget, none of the commands were recognised in PowerShell | "winget install commands not recognised in PowerShell" | Close the current terminal and open a new one — winget updates the PATH but existing terminals don't reload it | ✅ Yes |
| 2 | Running `bash setup.sh` gave a syntax error near `$(` | "bash setup.sh syntax error unexpected token Windows" | Windows saves files with CRLF line endings which break bash scripts — fix with `sed -i 's/\r//' setup.sh` | ✅ Yes |
| 3 | kubectl apply failed with "unrecognized type: string" on the backend deployment | "kubectl apply unrecognized type string YAML args field" | The HTML tags inside the args field were confusing the YAML parser — switching to block scalar format (using `|`) fixed it | ✅ Yes |
| 4 | `k3d cluster create` failed saying the cluster already exists | "k3d cluster create already exists error" | Check existing clusters with `k3d cluster list` — if it exists, either reuse it or delete with `k3d cluster delete edge-vnf` first | ✅ Yes |
| 5 | Could not reach the NGINX service via `curl http://192.168.49.2:30080` on Windows | "minikube NodePort not reachable Windows Docker driver" | The Docker driver on Windows does not expose NodePort addresses directly — use `minikube service nginx-lb-svc --url` to get a working localhost URL instead | ✅ Yes |
| 6 | Grafana login failed with "Invalid username or password" after a pod restart | "Grafana login failed after Kubernetes pod restart" | Suggested adding `securityContext.fsGroup: 65534` to the Grafana pod spec to fix storage permissions | ❌ No — this did not fix the issue for me. The real cause was that emptyDir storage resets on pod restart, wiping credentials entirely. I've fixed it manually by running `kubectl exec deployment/grafana -- grafana-cli admin reset-admin-password admin` |
| 7 | Prometheus datasource was not showing up in Grafana after deployment | "Grafana Prometheus datasource not auto configured Kubernetes environment variables" | Suggested adding specific provisioning environment variables to the Grafana deployment manifest | ❌ No — the environment variables had no effect in this version of Grafana. I have added the datasource manually through the Grafana UI using the internal address `http://prometheus-svc:9090` |
| 8 | The query `nginx_connections_accepted_total` returned no data in Grafana | "Prometheus nginx_connections_accepted_total no data" | This version of the exporter uses `nginx_connections_accepted` without the `_total` suffix — confirmed by checking available metrics at `/api/v1/label/__name__/values` | ✅ Yes |

---

## My thoughts on using GenAI for troubleshooting

For this coursework, Copilot was truly useful and helpful when faced with common, well-known mistakes; it's interesting that the Windows PATH bug and the NodePort tunnel bug existed in this realm. These problems have identifiable and documented solutions, which Copilot could recognize in great speed to economize the time that is spent reading the technical documentation manually.

Copilot's reliability did decline, however, in more idiosyncratic situations for the particular setup. An example here is Grafana datasource discrepancy which required manual exploration of the Grafana user-interface to resolve accurately; Copilot's direction here was correct but only directionally rather than accurate enough for the version in use. Similarly, the metric naming problem (problem 8) required the program to make a direct investigation of the Prometheus API, instead of relying on Copilot's response.
