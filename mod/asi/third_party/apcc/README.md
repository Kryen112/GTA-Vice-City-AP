# APCc

Vendored from https://github.com/randomcodegen/APCc at commit
`3081b4b53b6096252e587cb524d788ab918d96a2`.

This is randomcodegen's C port of [APCpp](https://github.com/N00byKing/APCpp)
by N00byKing and contributors. Its Jansson, GLib and libwebsockets
dependencies are built using vcpkg, with their copyright files in the installed
`share` directories.

Local integration changes (2026-09-07):

- Optional complete-packet callback and send API. The Vice City session keeps
  AP received-item indices, complete slot data, and durable pending checks;
  APCc owns WebSocket connection, framing, TLS and reconnects. Existing APCc
  callbacks retain their original behavior when this mode is not enabled.
- Process complete WebSocket messages, including fragmented packets, with a
  16 MB incoming-message bound. Send one packet per writable callback, reconnect
  on write failure, and discard old-connection output before authenticating.
- Remove raw packet logging, which exposed room passwords.
- Validate TLS certificates and hostnames, use the actual server as the Host
  header, and support explicit TLS selection without silently downgrading.
- Compile without optional WebSocket compression when the dependency omits it;
  handle failure to initialize the service timer.

## License

APCc, including the C port and local modifications, is licensed under the
GNU Lesser General Public License version 2.1 (`LGPL-2.1-only`). See [LICENSE](LICENSE),
reproduced from APCpp's license. Upstream authorship remains with N00byKing and
the APCpp contributors; the C port and local modifications are by randomcodegen.
The license and source-file notices are restored on 2026-09-08.

The library is provided without warranty, including any implied warranty of
merchantability or fitness for a particular purpose. Dependencies retain their
own licenses. The surrounding project's MIT license does not replace this license.

Binary distribution must include the applicable license notices and provide
corresponding source and relinking materials under LGPL 2.1. See the repository's
NOTICE and README.md for the statically linked ASI distribution requirements.
