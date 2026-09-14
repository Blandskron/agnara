# Agnara Container

PyPI remains the canonical distribution for Agnara's Python libraries. The
GHCR image is one executable reference runtime for evaluation and examples;
Docker is not required to use Agnara.

## Pull and run

Published images use the release version without the leading `v`:

```bash
docker pull ghcr.io/blandskron/agnara:1.0.0
docker run --rm -p 8000:8000 ghcr.io/blandskron/agnara:1.0.0
```

The verified reference service exposes `GET /health`, `GET /orders/{order_id}`
and the generated `GET /openapi.json` document on port `8000`. The image runs
as the unprivileged `agnara` user.

For reproducibility, pin the digest recorded by the release workflow:

```bash
docker pull ghcr.io/blandskron/agnara:1.0.0@sha256:<digest>
```

Version tags are immutable release identities. Alpha or development commits do
not receive `latest`; an `edge` tag, if enabled later, will mean unstable
development output and will never represent a release.

The release workflow builds the image from the same verified commit as the
Python release, publishes it to `ghcr.io/blandskron/agnara`, and attaches
BuildKit SBOM and provenance attestations. The package source label points to
the public repository so GitHub can associate the package with `Blandskron/agnara`.