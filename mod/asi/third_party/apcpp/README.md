# APCpp

Upstream: https://github.com/N00byKing/APCpp
Revision: `172f683d4306b4fa209949419993198f87d881ed`.
Imported: Archipelago.cpp, Archipelago.h, Archipelago_DataStorageSim.cpp,
Archipelago_Gifting.cpp and LICENSE. This is the C++ library, built directly
into the ASI, using IXWebSocket and JsonCpp.

License: LGPL-2.1-only; see LICENSE. Upstream work by N00byKing and contributors.
Local modifications by randomcodegen, 2026-09-08, under the same license:

- Optional complete packet/transport callbacks and packet send function, so the
  integration can preserve ReceivedItems indices and full slot data. This mode
  delegates protocol handling to NativeSession; it does not also run the stock
  APCpp protocol handler or send a second Connect packet.
- Explicit ws:// and wss:// URLs, with TLS as the default. Removed automatic
  downgrade after TLS errors. IXWebSocket validates TLS using Windows trust roots.
- Fixed invalidating iteration when clearing outstanding data requests.
- Packet mode skips the unused on-disk data cache, so initialization does not
  attempt to create a cache in the game's working directory.

Callbacks are configured before AP_Init/AP_Start and cleared after AP_Shutdown
joins the IXWebSocket thread. Callbacks enqueue bounded events; NativeSession
and all protocol state run on one ASI worker. Game memory stays on the game thread.

Build: scripts/build_native_client.ps1. The host project supplies dependencies
rather than upstream's submodule CMake build. Root NOTICE and README.md describe
source and relinking materials required for distribution of the static ASI.
