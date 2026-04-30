---
title: HEC Configuration
description: Configure the HTTP Event Collector endpoint for audit log ingestion
---

OctoWatch's HEC (HTTP Event Collector) endpoint receives GitHub audit log streams in Splunk HEC format. This guide covers advanced configuration options.

## Endpoint Details

| Property | Value |
|----------|-------|
| **URL** | `https://your-domain/services/collector` |
| **Method** | POST |
| **Auth** | Bearer token via `Authorization` header |
| **Format** | Splunk HEC JSON format |
| **Rate Limit** | 100 requests/second (configurable) |

## Authentication

The HEC endpoint requires a valid token in every request:

```http
POST /services/collector HTTP/1.1
Host: octowatch.yourdomain.com
Authorization: Splunk your-hec-token-here
Content-Type: application/json

{"event": {...}, "sourcetype": "github:audit:log"}
```

:::caution
The HEC token is mandatory. Requests without a valid token receive a `401 Unauthorized` response. Never expose this token publicly.
:::

## Rate Limiting

The HEC endpoint enforces rate limiting to protect against traffic floods:

| Setting | Default | Description |
|---------|---------|-------------|
| Rate limit | 100 req/s | Per-IP request rate |
| Body size | 5MB | Maximum request payload |
| Burst | 200 | Burst allowance above rate |

These are configured via nginx ingress annotations in the Helm chart:

```yaml
# helm/values.yaml
ingress:
  hec:
    rateLimit: "100"
    rateLimitBurst: "200"
    proxyBodySize: "5m"
```

## GitHub Audit Log Streaming Setup

### Step 1: Navigate to Streaming Settings

1. Go to your GitHub Enterprise
2. **Settings** → **Audit log** → **Log streaming**
3. Click **"Set up a stream"**

### Step 2: Configure the Stream

1. Select **"Splunk"** as the provider
2. **Domain**: Your OctoWatch FQDN (e.g., `octowatch.yourdomain.com`)
3. **HEC token**: Your configured HEC token value
4. **SSL verification**: Enabled (ensure valid TLS certificate)

### Step 3: Verify Connection

Click **"Check endpoint"** — GitHub will send a test event. Check your OctoWatch logs:

```bash
kubectl logs -n octowatch deployment/octowatch-backend | grep "HEC"
```

You should see:
```
INFO: HEC event received - sourcetype=github:audit:log events=1
```

## Monitoring HEC Health

OctoWatch provides health metrics for the HEC endpoint:

- **Events received** — Total events ingested (per org, per hour)
- **Ingestion lag** — Time between event creation and ingestion
- **Error rate** — Failed/rejected events
- **Queue depth** — Events pending processing

Access these via **Settings** → **System Health** → **Ingestion**.

## Troubleshooting

### Events not appearing

1. Verify the endpoint is reachable: `curl -I https://your-domain/services/collector`
2. Check token: `curl -H "Authorization: Splunk your-token" -d '{"event":"test"}' https://your-domain/services/collector`
3. Check GitHub streaming status in org settings (should show "Active")
4. Review backend logs for errors

### High latency

1. Check if rate limiting is being hit (429 responses in logs)
2. Verify database performance (slow writes = queue backup)
3. Consider scaling backend replicas in Kubernetes
