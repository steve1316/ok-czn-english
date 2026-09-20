<div align="center">
  <h1 align="center">
    <img src="icons/icon.png" width="200" alt="ok-czn logo"/>
    <br/>
    ok-czn
  </h1>

  <p>
    An image-recognition-based automation tool for Chaos Zero Nightmare, with background mode support, developed with <a href="https://github.com/ok-oldking/ok-script">ok-script</a>.
  </p>

  <p><i>Operates by simulating the Windows user interface, with no memory reading or file modification.</i></p>
</div>

<!-- Badges -->
<div align="center">

![Platform](https://img.shields.io/badge/platform-Windows-blue)
[![GitHub release](https://img.shields.io/github/v/release/steve1316/ok-czn-english)](https://github.com/steve1316/ok-czn-english/releases)

</div>

> [!NOTE]
> A fork of [baoxin1100/ok-kes](https://github.com/baoxin1100/ok-kes) targeting the **Global (English)** client.
> Simplified and Traditional Chinese still ship and keep working, Android emulators included. The original work
> is baoxin1100's and ok-oldking's.

> [!IMPORTANT]
> Chaos and Sortie complete full runs in English. The game-text catalog still grows as new screens turn up, so
> an unfamiliar screen can stall a run.

> [!CAUTION]
> An external tool for personal learning, free and open source. It interacts with the game only by simulating
> standard user interface actions, and never modifies game files or data. Any issues arising from its use are
> not the responsibility of this project or its developers.

---

## Quick Start

1. **Download the installer** from [Releases](https://github.com/steve1316/ok-czn-english/releases), install
   and run. The program updates itself on launch.
2. **Run as Administrator.** The game is elevated, so without this Windows blocks every simulated click and
   the app reports no error.
3. **In the game's own settings**, turn on shortcut key display, and turn on auto-battle and auto-story for
   Chaos Manifestation.
4. **Connect the game window**, then press **Start** on a mode under **Tasks**.

On a Chinese client, set **Game Language** in the mode you use. On Global there is nothing to set.

## What It Does

<img src="docs/images/tasks.png" alt="The Tasks tab, with a Start button on each of the three modes" />

### Sortie Mode
- **Auto Battle**: plays cards by key recognition, in your Play Priority order
- **Smart Card Play**: picks the cards your list does not name on cost, kind and effect text
- **Auto Card Management**: obtain, remove, copy and flash cards
- **Member Selection**: picks by your priority list, and drafts by role when you have not set one
- **Route Selection**: recognises node types and advances by priority
- **Shop Handling**: enters the Dellang Shop to remove cards
- **Ether Supply Detection**: detects low stamina and exits

### Chaos Mode
- **Auto Card Management**: remove, copy, flash, grant flash and convert cards
- **Route Selection**: identifies rest, event, elite and normal enemy nodes
- **Event Choices**: ranks Epiphany, then Desire card, reward, credits, fight, then ending the event
- **Desire Cards (Season 4)**: builds the faction you pick under **Desire Faction**
- **Dice Rolls**: rerolls a failed roll while it can afford to
- **Mental Breakdown Treatment**: visits the trauma center automatically
- **Save Data Handling**: deletes save data, with a configurable retention count
- **Zero System Support**: handles Codex search

### Story Mode (Semi-Auto)
- **Auto Dialogue**: skips story dialogue
- **Manual Mode Switching**: start Sortie by hand for battle stages, Chaos for chaos stages
- **Battle teams**: configured by hand in this mode

### Cards and Equipment
- **An empty priority list is filled in** from the screen, taking only Unique and Legend
- **Build preset pins are honoured** wherever a card screen offers something your preset marked
- **A Mythic piece is never passed over**, and only goes to a combatant with room for one
- **An unlisted piece goes to the combatant the client marks "Recommended"**
- **Generated equipment is bought only on a spree**, and only for a slot standing empty

### Everywhere
- **Narration Screens**: advances the Global client's cutscenes in Chaos and Sortie
- **Notifications**: a Windows toast when a run starts, finishes, or sticks on one screen for a minute
- **Config Export & Import**: share a mode's settings as a text code (upstream's config upload is removed)
- **Resolutions**: 1920x1080, 1600x900, 1280x720 and other 16:9 sizes
- **Background Mode**: runs while the game window is minimized or obscured

### Settings

<img src="docs/images/settings.png" alt="Chaos Mode expanded, showing its settings with English names and descriptions" />

Every setting is named and described in English, and each season's settings fold behind their own header.

- **Names are picked from a list, not typed**, so a typo cannot silently stop a setting matching
- **Hover an option** for its in-game effect and base values
- **Switching to this build re-seeds the defaults once**, since upstream's are Chinese names OCR cannot match

<img src="docs/images/option_picker.png" alt="The card picker, searching a list of options with one card's effect shown on hover" />

## Troubleshooting

1. **Clicks do nothing**: run as Administrator.
2. **Antivirus**: add the install directory to your exceptions, Windows Defender included.
3. **Display**: turn off graphics card filters and sharpening, use the game's default brightness, and disable
   overlays that draw on the game window.
4. **Resolution**: run the game at a 16:9 aspect ratio.
5. **Version**: check you are on the latest release.

---

## Developer Zone

### Running from source

```bash
pip install -r requirements.txt --upgrade

python main.py          # release mode
python main_debug.py    # debug mode, which adds the Debug and Run Code tabs
```

```powershell
.\run_tests.ps1         # every tests\Test*.py, sharing one process bar the manifest reader
```

### Translations

Two catalogs live under `i18n/`, and they run in **opposite directions**:

| Catalog | Direction | Holds |
| --- | --- | --- |
| `ok.po` | Chinese msgid to English msgstr | App UI labels, task names, setting descriptions |
| `ocr.po` | English msgid to Chinese msgstr | Game text read off the screen |

`ocr.po` is what makes the Chinese task code work against an English client: it rewrites English game text into
the Chinese literal the handler compares against, before any handler sees the text box. That is why `ok_tasks/`
needs no changes for the Global client.

> [!CAUTION]
> **Never put UI strings in `ocr.po`.** It rewrites game text, so a stray entry there corrupts recognition.

The app only ever reads the compiled `.mo`, so recompile after editing a `.po`:

```bash
python scripts/compile_i18n.py                 # write the .mo files
python scripts/compile_i18n.py --check         # verify only, as CI does
python scripts/ocr_dump.py <image> --missing   # find the English text for a new entry
```

### Staying in sync with upstream

Upstream is `baoxin1100/ok-kes`. Changes here are kept additive so merges stay clean: `ok_tasks/` is left
byte-identical to upstream, and everything this fork changes lives in `src/en/` as a runtime patch.

```bash
git remote add upstream https://github.com/baoxin1100/ok-kes.git
git config merge.ours.driver true   # once per clone, for the README merge=ours rule
git fetch upstream && git merge upstream/master
```

## Credits

* [baoxin1100/ok-kes](https://github.com/baoxin1100/ok-kes) - the original project this fork is built on
* [ok-script](https://github.com/ok-oldking/ok-script)
* [OnnxOCR](https://github.com/ok-oldking/OnnxOCR)
* [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
