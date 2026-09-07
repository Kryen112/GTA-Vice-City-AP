# APCc

Vendored from https://github.com/randomcodegen/APCc at commit
`3081b4b53b6096252e587cb524d788ab918d96a2`.

This is the user's C fork of APCpp. Its Jansson, GLib and libwebsockets
dependencies are built using vcpkg, with their copyright files in the installed
`share` directories.

Local changes:

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

The upstream repository does not include a separate license file. Its source
has been retained with the upstream notices; no new license is claimed here.
