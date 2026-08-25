// The pause menu's ARCHIPELAGO entry and the status panel it opens.
//
// The panel does not get a menu page of its own. The frontend indexes one table
// by page id with no bound check anywhere, so a page past the vanilla last looks
// free; it is not. This build gives page 34 to the controls screen's
// empty-binding error, whose input handler ignores every key (0x4990E6) and
// whose draw puts a full-screen message over the page (0x4A3302), and no page
// number the game has no opinion about can be proven free from the outside. So
// the panel borrows a page the game uses for real and covers it while it shows.
// Everything that page DOES stays the game's own: its navigation, its back entry,
// its input. The one thing written is where that entry stands, lowered to the foot
// of the screen so the part of the page the panel covers is one tall band rather
// than two, and the menu's own hit test follows the position. The worst a broken
// mod can do there is show the page it borrowed, with its back button lower than
// the game put it.
//
// The pause menu is drawn without a game frame, so nothing here may depend on
// the frame handlers having run: it is called from the menu's own draw hook and
// reads a snapshot handed to it.
#pragma once

#include <functional>
#include <string>
#include <vector>

#include "scm_status_panel.hpp"

namespace gtavc {

using Logger = std::function<void(const std::string&)>;

class StatusPage {
 public:
  explicit StatusPage(Logger logger);

  // Puts an ARCHIPELAGO entry on the pause menu, once, on the game thread. The
  // executable must be the classic 1.0 build and the pause page must still be
  // vanilla; anything else and the entry is never added, which leaves the menu
  // exactly as the game built it.
  void Install();

  // Follows the menu: remembers which pause-menu row the player is standing on,
  // so the borrowed page knows whether the panel's own entry opened it, and so
  // going back lands on the row they came from. Called every menu frame, and
  // hands back what this frame calls for, including whether the panel draws.
  PanelFrame Follow();

  // Draws the panel over the borrowed page. Called from the menu draw hook,
  // after the menu itself has drawn, so this paints over it.
  void Draw(const std::vector<StatusSection>& sections) const;

 private:
  // Whether the pause menu's entry went in, so the panel has a way to be
  // reached and a row to return to.
  bool ClaimEntry();
  // Stands the borrowed page's own back entry at the foot of the screen, so the
  // panel's rows get one tall band instead of stopping halfway down the page.
  // Whether the move took, which is false where that entry is not the one the
  // vanilla table stands up; the panel then keeps the band it always had.
  bool LowerBackEntry();
  // Where the borrowed page's back entry stands, read from the menu's own table so
  // the cover cannot disagree with it.
  float BackEntryY() const;
  // Where the cover stops and where it starts again: above that entry's own
  // highlight bar and below it. The first of the two is also the bottom of the band
  // the rows are laid out in.
  float CoverBottom() const;
  float HighlightBarBottom() const;
  // The menu as the panel's own decision reads it. Everything game-facing about
  // that decision is here; what it means lives in PlanPanelFrame, where the
  // console self-test can reach it.
  PanelMenuState ReadMenu() const;

  Logger logger_;
  bool installed_ = false;
  bool owns_entry_ = false;
  // Whether the last pause-menu row the player stood on was the panel's own, so
  // the borrowed page shows the panel instead of its own content.
  bool armed_ = false;
};

}  // namespace gtavc
