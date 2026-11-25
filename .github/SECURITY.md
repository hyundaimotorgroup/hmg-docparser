# Security policy

[한국어](../docs/kor/SECURITY.md)
Hyundai Motor Group takes the security of our software products and services seriously, including all source code repositories within our GitHub organizations.

## Reporting a Vulnerability
Please do not report security vulnerabilities through public GitHub Issues, Discussions, or Pull Requests.
To report a security vulnerability, please email:
- psirt@hyundai.com

Include the repository name, affected commit/version, environment, reproduction
steps, impact, and a minimal proof of concept where possible. Remove credentials
and private document content. Arrange sensitive evidence through the private
channel. Allow investigation and coordination before publishing details.

## Scope and deployment boundaries

This repository provides a local parser CLI and helper services, not a hosted
public parsing service. Router, config editor, Dolphin 1.5, and Paddle tutorial
entrypoints restrict binding to loopback and do not provide multi-user
authentication. Internet-facing use requires a separately reviewed deployment
and access controls.

[HTTP input limits](../docs/http-input-limits.md) bound request bodies, decoded
images, queues, and YAML expansion. They do not guarantee inference time or total
memory usage. Parser document limits are described in
[configuration](../docs/configuration.md).

Use trusted model and pickle assets; untrusted serialized files can execute code
when loaded. Protect `.env`, exported configs, outputs, and logs. Provider calls
may send documents to configured endpoints. The optional Confluence pipeline
can change remote pages and attachments. See
[data handling](../docs/privacy-and-data-handling.md) and
[asset conditions](../docs/model-and-data-assets.md).

## Maintenance

Use the current published source and dependency files, and record the commit
when reporting a problem. No version-specific security support schedule or
response-time guarantee has been published. Dependency scanning and release
verification are tracked in the [release checklist](../docs/release-checklist.md).
