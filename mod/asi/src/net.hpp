// A minimal blocking Winsock TCP client for the ASI to reach the client's
// localhost listener. No game dependency, so the harness links it directly.
#pragma once

#include <string>

namespace gtavc {

class TcpClient {
 public:
  TcpClient();
  ~TcpClient();
  TcpClient(const TcpClient&) = delete;
  TcpClient& operator=(const TcpClient&) = delete;

  bool Connect(const std::string& host, int port);
  bool SendAll(const std::string& data);
  // Waits up to timeout_ms for data. Returns bytes read (> 0), 0 on timeout,
  // or -1 on close or error.
  int RecvSome(char* buffer, int length, int timeout_ms);
  void Close();
  bool Connected() const;

 private:
  bool winsock_started_ = false;
  // INVALID_SOCKET (0xFFFFFFFF) zero-extended, without pulling in the header.
  // The constructor sets the real value.
  unsigned long long socket_ = 0xFFFFFFFFull;
};

}  // namespace gtavc
