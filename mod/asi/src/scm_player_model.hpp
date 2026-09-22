#pragma once

#include <array>
#include <cstddef>

namespace gtavc {

inline constexpr std::array<const char*, 74> kPlayerModels = {
    "PLAYER", "PLAYER2", "PLAYER3", "PLAYER4", "PLAYER5", "PLAYER6",
    "PLAYER7", "PLAYER8", "PLAYER9", "PLAY11", "PLAY12", "PLAY10",
    "sam", "s_keep", "bgb", "stripc", "stripa", "stripb", "bga", "burger",
    "sgoona", "sgoonb", "igken", "cgona", "dgoona", "dgoonb", "igmerc2",
    "bounca", "floozyb", "chef", "igbuddy", "spandxa", "spandxb", "iggonz",
    "cgonb", "fsfa", "courier", "igdiaz", "igcolon", "dgoonc", "sgc",
    "igmike", "shootra", "shootrb", "igphil", "ighlary", "igphil3", "igmike2",
    "ighlry2", "igphil2", "cmraman", "mporna", "igcandy", "igmerc", "crewa",
    "crewb", "igalscb", "igbudy2", "floozya", "cdrivra", "cdrivrb", "printra",
    "printrb", "printrc", "mba", "mbb", "igsonny", "mgoona", "mserver",
    "floozyc", "psycho", "igjezz", "igdick", "igpercy",
};

inline const char* PlayerModelName(int index) {
  return index >= 0 && index < static_cast<int>(kPlayerModels.size())
             ? kPlayerModels[static_cast<std::size_t>(index)] : nullptr;
}

inline bool PlayerModelReady(int index, bool pending, bool playable, bool on_foot) {
  return PlayerModelName(index) != nullptr && pending && playable && on_foot;
}

}  // namespace gtavc
