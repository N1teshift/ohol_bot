# Protocol Reuse Decision

For now, this project keeps a native Python implementation.

## References

- `marius851000/plannerbot` is used as protocol and planning reference material.
  It does not currently expose a repository license, so we do not copy its code
  directly.
- `webmsgr/oholbotframework` is LGPL-2.1 and can be reused deliberately later,
  but the current codebase only uses its packet naming and MITM shape as a guide.

## Current Decision

Keep implementing the protocol client, message parser, and game-data loader in
`src/ohol_bot`. This avoids dependency/licensing friction while preserving the
option to integrate external code later.

## Revisit When

- The Python protocol client fails on map/chunk parsing in a way that the LGPL
  parser already solves cleanly.
- `plannerbot` gets an explicit license and its Rust client is substantially
  ahead of the Python implementation.
- A Rust sidecar becomes worthwhile for performance or correctness.
