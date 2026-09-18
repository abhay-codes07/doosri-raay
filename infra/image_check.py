#!/usr/bin/env python
"""Inspect a locally built recovery-agent image and warn if Lambda would reject it.

Lambda container images must be a single-platform linux/amd64 (or arm64) image manifest. Since
BuildKit 0.11 / buildx 0.10, `docker build` attaches provenance + SBOM *attestations* by default,
which turns the pushed artifact into an OCI image index with extra `unknown/unknown` manifests;
Lambda then fails with "The image manifest, config or layer media type ... is not supported".

Usage: python infra/image_check.py <image:tag>        (run by `make image-check`)
Exit code 1 when the image is missing, not linux/amd64, or looks like a multi-manifest index.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

FIX = (
    "fix: build with attestations disabled so the image is a single manifest:\n"
    "       DOCKER_BUILDKIT=1 docker build --provenance=false --sbom=false --platform linux/amd64 ...\n"
    "     or export BUILDX_NO_DEFAULT_ATTESTATIONS=1 (the Makefile sets it for build/deploy/image-check)\n"
    "     and, if you pushed the image yourself, push again with `docker push` after that rebuild."
)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("usage: python infra/image_check.py <image:tag>")
    image = sys.argv[1]
    docker = shutil.which("docker")
    if not docker:
        sys.exit("docker not found on PATH (start Docker Desktop)")

    proc = run([docker, "image", "inspect", image])
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        sys.exit(f"docker image inspect {image} failed (build it first: make image-check)")
    info = json.loads(proc.stdout)[0]
    arch, os_ = info.get("Architecture"), info.get("Os")
    print(f"image        {image}")
    print(f"Architecture {arch}")
    print(f"Os           {os_}")
    problems: list[str] = []
    if (os_, arch) != ("linux", "amd64"):
        problems.append(f"expected linux/amd64 (template Architectures: x86_64), got {os_}/{arch}")

    # Docker >= 25 with the containerd image store exposes the manifest descriptor and, for an
    # index, the list of manifests (attestations show up as unknown/unknown with a
    # vnd.docker.reference.type=attestation-manifest annotation).
    descriptor = info.get("Descriptor") or {}
    media_type = descriptor.get("mediaType", "")
    manifests = info.get("Manifests") or []
    if media_type:
        print(f"MediaType    {media_type}")
    attestations = [
        m for m in manifests
        if (m.get("Annotations") or {}).get("vnd.docker.reference.type") == "attestation-manifest"
        or ((m.get("Platform") or {}).get("architecture") == "unknown")
    ]
    if attestations or ("index" in media_type and len(manifests) > 1):
        problems.append(
            f"the image is an OCI image index with {len(manifests)} manifests "
            f"({len(attestations)} attestation); Lambda rejects multi-manifest images"
        )
    elif not media_type:
        # Classic image store: attestations are only materialised on push, so also try buildx.
        bx = run([docker, "buildx", "imagetools", "inspect", image])
        if bx.returncode == 0 and "unknown/unknown" in bx.stdout:
            problems.append("`docker buildx imagetools inspect` shows unknown/unknown attestation manifests; Lambda rejects those")
        else:
            print("Manifest     single image manifest as far as the local store can tell "
                  "(attestations are only added on push unless BUILDX_NO_DEFAULT_ATTESTATIONS=1 / --provenance=false)")

    if problems:
        for p in problems:
            print(f"WARN {p}")
        print(FIX)
        return 1
    print("ok   single-manifest linux/amd64 image; Lambda will accept it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
