# Agnara Container

PyPI remains the canonical distribution for Agnara's Python libraries. The
GHCR image is one executable reference runtime for evaluation and examples;
Docker is not required to use Agnara.

## Pull and run

Published images use the release version without the leading `v` and are pushed
to both GHCR and Docker Hub:

```bash
docker pull ghcr.io/blandskron/agnara:1.0.3
docker pull docker.io/blandskron/agnara:1.0.3
docker run --rm -p 8000:8000 ghcr.io/blandskron/agnara:1.0.3
```

The verified reference service exposes `GET /health`, `GET /orders/{order_id}`
and the generated `GET /openapi.json` document on port `8000`. The image runs
as the unprivileged `agnara` user.

For reproducibility, pin the digest recorded by the release workflow:

```bash
docker pull ghcr.io/blandskron/agnara:1.0.3@sha256:<digest>
```

These commands apply after the 1.0.3 image is published. Version tags are
immutable release identities. Development commits do not receive `latest`.

## Development edge

`edge` is a mutable development image built only from `develop`; it is not a
PyPI publication, GitHub Release, version tag or promise of compatibility.
It is useful for evaluating the current reference runtime, never for a
production deployment:

```bash
docker pull ghcr.io/blandskron/agnara:edge
docker pull docker.io/blandskron/agnara:edge
docker run --rm -p 8000:8000 ghcr.io/blandskron/agnara:edge
```

The `Publish Container Edge` workflow rejects any ref other than
`refs/heads/develop`, reuses the full CI quality gate, builds and smoke-tests a
credential-free local image, then publishes one Linux `amd64`/`arm64` Buildx
manifest to both registries. It records the immutable digest and verifies the
published Docker Hub image through the same smoke test. BuildKit attaches SBOM
and maximum-mode provenance to that publication.

Repository configuration must provide `DOCKERHUB_USERNAME` and
`DOCKERHUB_TOKEN` Actions secrets. The GHCR package must also be public for
the unauthenticated pull commands above to work.

The release workflow builds the image from the same verified commit as the
Python release, publishes it to both `ghcr.io/blandskron/agnara` and
`docker.io/blandskron/agnara`, and attaches BuildKit SBOM and provenance
attestations. The package source label points to the public repository so
GitHub can associate the package with `Blandskron/agnara`.
