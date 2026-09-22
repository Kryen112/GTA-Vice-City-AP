#pragma once

#include <cstdio>
#include <string>
#include <vector>
#include <windows.h>
#include <tlhelp32.h>
#include <intrin.h>
#include <plugin.h>
#include <CPools.h>
#include <CTimer.h>
#include <cBuoyancy.h>
#include "game_addresses.hpp"
#include "ped_physics_sample.hpp"

namespace gtavc::ped_diagnostics {

struct Observation {
  int reference = -1;
  PedPhysicsSample sample;
  const char* phase = "none";
  unsigned int frame = 0;
};

inline FILE* output = nullptr;
inline bool captured = false;
inline std::vector<Observation> observations;

// Preserve the game's x87/SSE state across diagnostic allocation and logging.
struct FloatingPointState {
  alignas(16) unsigned char bytes[512];
  FloatingPointState() { _fxsave(bytes); }
  ~FloatingPointState() { _fxrstor(bytes); }
};

inline void PrintSample(const char* label, const PedPhysicsSample& sample) {
  // Raw bits retain NaN payloads without evaluating invalid floats.
  std::fprintf(output, "%s positionXYZ/velocityXYZ bits=", label);
  for (const float& value : sample.values) {
    std::uint32_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    std::fprintf(output, "%08X ", bits);
  }
  std::fputc('\n', output);
}

inline PedPhysicsSample Sample(CPhysical* physical) {
  PedPhysicsSample result;
  std::memcpy(result.values.data(), &physical->GetPosition(), sizeof(float) * 3);
  std::memcpy(result.values.data() + 3, &physical->m_vecMoveSpeed, sizeof(float) * 3);
  return result;
}

inline void Observe(CPhysical* physical, const char* phase, void* caller = nullptr, CPhysical* partner = nullptr) {
  if (output == nullptr || captured || physical == nullptr || physical->m_nType != ENTITY_TYPE_PED) return;
  FloatingPointState floating_point;
  auto* pool = CPools::ms_pPedPool;
  auto* ped = static_cast<CPed*>(physical);
  if (pool == nullptr || !pool->IsObjectValid(ped)) return;
  if (observations.size() != static_cast<std::size_t>(pool->m_nSize)) observations.resize(pool->m_nSize);
  auto& previous = observations[pool->GetIndex(ped)];
  const int reference = pool->GetRef(ped);
  const auto current = Sample(ped);
  if (current.IsFinite()) {
    previous = {reference, current, phase, CTimer::m_FrameCounter};
    return;
  }
  // Capture once per process; retain the original physics and exception behavior.
  captured = true;
  unsigned short control, status;
  unsigned int mxcsr;
  std::memcpy(&control, floating_point.bytes, sizeof(control));
  std::memcpy(&status, floating_point.bytes + 2, sizeof(status));
  std::memcpy(&mxcsr, floating_point.bytes + 24, sizeof(mxcsr));
  std::fprintf(output, "FP control=%04X status=%04X mxcsr=%08X\n", control, status, mxcsr);
  std::fprintf(output, "FIRST INVALID frame=%u phase=%s caller=%p ped=%p ref=%d model=%d type=%d state=%d\n",
      CTimer::m_FrameCounter, phase, caller, ped, reference, ped->m_nModelIndex,
      static_cast<int>(ped->m_nPedType), static_cast<int>(ped->m_ePedState));
  if (previous.reference == reference) {
    std::fprintf(output, "LAST FINITE frame=%u phase=%s\n", previous.frame, previous.phase);
    PrintSample("previous", previous.sample);
  } else {
    std::fprintf(output, "No earlier finite observation for this pool reference.\n");
  }
  PrintSample("current", current);
  if (partner) {
    std::fprintf(output, "collision partner=%p model=%d entity-type=%u\n",
        partner, partner->m_nModelIndex, static_cast<unsigned int>(partner->m_nType));
    PrintSample("partner", Sample(partner));
  }
  void* frames[32];
  const auto count = CaptureStackBackTrace(0, 32, frames, nullptr);
  std::fprintf(output, "stack:");
  for (unsigned int i = 0; i < count; ++i) std::fprintf(output, " %p", frames[i]);
  std::fprintf(output, "\nEND CAPTURE\n");
  std::fflush(output);
}

// These boundaries identify the first observed invalid state, not every write.
struct Probe {
  CPhysical* first;
  CPhysical* second;
  const char* after;
  void* caller;
  Probe(CPhysical* first, CPhysical* second, const char* before, const char* after, void* caller)
      : first(first), second(second), after(after), caller(caller) {
    Observe(first, before, caller, second);
    Observe(second, before, caller, first);
  }
  ~Probe() { Observe(first, after, caller, second); Observe(second, after, caller, first); }
};

inline void __fastcall Move(CPhysical* self, void*) {
  Probe probe(self, nullptr, "move/before", "move/after", _ReturnAddress());
  self->ApplyMoveSpeed();
}
inline bool __fastcall CollisionPair(CPhysical* self, void*, CPhysical* other, CColPoint& point, float& a, float& b) {
  Probe probe(self, other, "collision-pair/before", "collision-pair/after", _ReturnAddress());
  return self->ApplyCollision(other, point, a, b);
}
inline bool __fastcall CollisionWorld(CPhysical* self, void*, CColPoint& point, float& a) {
  Probe probe(self, nullptr, "collision-world/before", "collision-world/after", _ReturnAddress());
  return self->ApplyCollision(point, a);
}
inline bool __fastcall CollisionAlternate(CPhysical* self, void*, CEntity* other, CColPoint& point,
                                         float& a, CVector& b, CVector& c) {
  Probe probe(self, other && other->m_nType == ENTITY_TYPE_PED ? static_cast<CPhysical*>(other) : nullptr,
      "collision-alternate/before", "collision-alternate/after", _ReturnAddress());
  return self->ApplyCollisionAlt(other, point, a, b, c);
}
inline bool __fastcall FrictionPair(CPhysical* self, void*, CPhysical* other, float a, CColPoint& point) {
  Probe probe(self, other, "friction-pair/before", "friction-pair/after", _ReturnAddress());
  return self->ApplyFriction(other, a, point);
}
inline bool __fastcall FrictionWorld(CPhysical* self, void*, float a, CColPoint& point) {
  Probe probe(self, nullptr, "friction-world/before", "friction-world/after", _ReturnAddress());
  return self->ApplyFriction(a, point);
}
inline bool __fastcall Buoyancy(cBuoyancy* self, void*, CPhysical* ped, float force, CVector* point, CVector* impulse) {
  Probe probe(ped, nullptr, "buoyancy/before", "buoyancy/after", _ReturnAddress());
  return self->ProcessBuoyancy(ped, force, point, impulse);
}

template<typename Function, std::size_t Count>
void Hook(const unsigned int (&sites)[Count], unsigned int target, Function function) {
  for (const auto site : sites) {
    if (*reinterpret_cast<const unsigned char*>(site) != 0xE8 ||
        site + 5 + *reinterpret_cast<const int*>(site + 1) != target) {
      std::fprintf(output, "SKIPPED call=%08X target=%08X (modified call site)\n", site, target);
      continue;
    }
    injector::MakeCALL(site, function, true);
    std::fprintf(output, "hook call=%08X target=%08X\n", site, target);
  }
}

inline void Install(const std::string& directory) {
  if (output || plugin::GetGameVersion() != GAME_10EN ||
      GetFileAttributesA((directory + "gtavc_ap_ped_diagnostics.enabled").c_str()) == INVALID_FILE_ATTRIBUTES) return;
  if (fopen_s(&output, (directory + "gtavc_ap_ped_diagnostics.log").c_str(), "a") != 0) return;
  std::fprintf(output, "\nPED DIAGNOSTICS pid=%lu (observational, no recovery)\n", GetCurrentProcessId());
  const auto snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId());
  MODULEENTRY32 module{};
  module.dwSize = sizeof(module);
  if (snapshot != INVALID_HANDLE_VALUE) {
    if (Module32First(snapshot, &module)) do {
      std::fprintf(output, "module base=%p size=%lu name=%s\n", module.modBaseAddr, module.modBaseSize, module.szModule);
    } while (Module32Next(snapshot, &module));
    CloseHandle(snapshot);
  }
  const unsigned int buoyancy[] = {kPedBuoyancyCall10};
  Hook(buoyancy, kBuoyancyTarget10, &Buoyancy);
  Hook(kPhysicalMoveCalls10, kPhysicalMoveTarget10, &Move);
  Hook(kCollisionPairCalls10, kCollisionPairTarget10, &CollisionPair);
  Hook(kCollisionWorldCalls10, kCollisionWorldTarget10, &CollisionWorld);
  Hook(kCollisionAlternateCalls10, kCollisionAlternateTarget10, &CollisionAlternate);
  Hook(kFrictionPairCalls10, kFrictionPairTarget10, &FrictionPair);
  Hook(kFrictionWorldCalls10, kFrictionWorldTarget10, &FrictionWorld);
  std::fflush(output);
}

inline void BeforeWorld() {
  if (!output || captured || !CPools::ms_pPedPool) return;
  auto* pool = CPools::ms_pPedPool;
  for (int index = 0; index < pool->m_nSize; ++index) Observe(pool->GetAt(index), "before-world");
}

inline void Reset() { observations.clear(); }

} // namespace gtavc::ped_diagnostics
