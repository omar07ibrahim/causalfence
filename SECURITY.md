# Security policy

## Supported versions

Security fixes are provided for the latest released 0.1.x version and the
current `main` branch. The frozen `legacy/dtk-lpr-2025/` snapshot is not a
supported application and must not be deployed.

## Report a vulnerability privately

Use GitHub's **Security → Report a vulnerability** form:

https://github.com/omar07ibrahim/causalfence/security/advisories/new

Do not open a public issue for an undisclosed vulnerability. Include the
affected revision, a minimal reproduction, impact, and any suggested
mitigation. Please remove credentials, production traces, personal data, and
third-party confidential material.

The maintainer aims to acknowledge a complete report within three business
days and provide an initial assessment within seven business days. These are
best-effort response targets, not a service-level agreement.

## Security boundaries

CausalFence parses local JSON and produces local JSON, text, and HTML. The
runtime does not make network requests, connect to databases, load plugins,
execute trace fields, or require credentials. Its receipt establishes
deterministic agreement under the documented bounded trace contract; it does
not authenticate trace producers or certify a database.

Reports concerning accidentally committed secrets or a vulnerability in the
archived legacy snapshot are still welcome through the private channel, even
though that snapshot is unsupported.
