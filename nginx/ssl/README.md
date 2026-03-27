# TLS Certificates

This directory holds TLS certificates for the nginx reverse proxy. These files are **not** committed to the repository.

## Generate self-signed certificates for local development

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem \
  -subj "/CN=localhost"
```

For production, use certificates from a trusted CA or a tool like [cert-manager](https://cert-manager.io/).
