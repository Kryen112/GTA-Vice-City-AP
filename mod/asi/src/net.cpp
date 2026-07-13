#include "net.hpp"

#include <winsock2.h>
#include <ws2tcpip.h>

#include <string>

#pragma comment(lib, "ws2_32.lib")

namespace gtavc {

TcpClient::TcpClient() {
  WSADATA data;
  winsock_started_ = WSAStartup(MAKEWORD(2, 2), &data) == 0;
  socket_ = INVALID_SOCKET;
}

TcpClient::~TcpClient() {
  Close();
  if (winsock_started_) WSACleanup();
}

bool TcpClient::Connect(const std::string& host, int port) {
  Close();
  if (!winsock_started_) return false;
  addrinfo hints{};
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  hints.ai_protocol = IPPROTO_TCP;
  addrinfo* result = nullptr;
  if (getaddrinfo(host.c_str(), std::to_string(port).c_str(), &hints, &result) != 0) {
    return false;
  }
  SOCKET handle = INVALID_SOCKET;
  for (addrinfo* entry = result; entry != nullptr; entry = entry->ai_next) {
    handle = socket(entry->ai_family, entry->ai_socktype, entry->ai_protocol);
    if (handle == INVALID_SOCKET) continue;
    if (connect(handle, entry->ai_addr, static_cast<int>(entry->ai_addrlen)) == 0) break;
    closesocket(handle);
    handle = INVALID_SOCKET;
  }
  freeaddrinfo(result);
  socket_ = handle;
  return handle != INVALID_SOCKET;
}

bool TcpClient::SendAll(const std::string& data) {
  if (socket_ == INVALID_SOCKET) return false;
  std::size_t sent = 0;
  while (sent < data.size()) {
    const int chunk = send(static_cast<SOCKET>(socket_), data.data() + sent,
                           static_cast<int>(data.size() - sent), 0);
    if (chunk <= 0) return false;
    sent += static_cast<std::size_t>(chunk);
  }
  return true;
}

int TcpClient::RecvSome(char* buffer, int length, int timeout_ms) {
  if (socket_ == INVALID_SOCKET) return -1;
  fd_set read_set;
  FD_ZERO(&read_set);
  FD_SET(static_cast<SOCKET>(socket_), &read_set);
  timeval timeout;
  timeout.tv_sec = timeout_ms / 1000;
  timeout.tv_usec = (timeout_ms % 1000) * 1000;
  const int ready = select(0, &read_set, nullptr, nullptr, &timeout);
  if (ready == 0) return 0;
  if (ready < 0) return -1;
  const int received = recv(static_cast<SOCKET>(socket_), buffer, length, 0);
  if (received <= 0) return -1;
  return received;
}

void TcpClient::Close() {
  if (socket_ != INVALID_SOCKET) {
    closesocket(static_cast<SOCKET>(socket_));
    socket_ = INVALID_SOCKET;
  }
}

bool TcpClient::Connected() const { return socket_ != INVALID_SOCKET; }

}  // namespace gtavc
