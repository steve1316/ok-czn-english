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

> This is a fork of [baoxin1100/ok-kes](https://github.com/baoxin1100/ok-kes) that targets the **Global (English)** client.
> Upstream's Simplified and Traditional Chinese support still ships and keeps working. All of the original work is
> baoxin1100's and ok-oldking's, and this fork only adds the Global client on top.

> **Status: Global client support is in progress.** The client is detected and the English text pipeline is in place,
> but the game-text catalog is still being built from real captures, so the automation modes do not yet run end to end
> in English. The Chinese clients are unaffected.

---

## Disclaimer

This software is an external auxiliary tool designed to automate parts of the gameplay for Chaos Zero Nightmare. It interacts with the game solely by simulating standard user interface actions. This project aims to simplify repetitive user tasks and does not disrupt game balance or provide an unfair advantage. It will never modify any game files or data.

This software is open-source and free, intended for personal learning purposes only. Any issues arising from the use of this software are not the responsibility of this project or its developers.

**By using this software, you acknowledge that you have read, understood, and agreed to the above statement, and you voluntarily assume all potential risks.**

## Quick Start

1. **Download the installer** from [Releases](https://github.com/steve1316/ok-czn-english/releases).
2. **Install and run.** The program updates itself on launch. Start the game, connect its window, then pick a mode to run.

## Main Features

<img src="docs/images/image_1.png" alt="Feature UI" />

### Sortie Mode (Auto Battle)
- **Auto Battle**: Card play driven by key recognition, with customizable play priority
- **Auto Card Management**: Obtain, remove, copy and flash cards
- **Member Selection**: Picks battle members by your priority configuration
- **Route Selection**: Recognises node types and advances by priority
- **Shop Handling**: Enters the Derang Shop to remove cards
- **Ether Supply Detection**: Detects low stamina and exits

### Chaos Mode
- **Auto Card Management**: Remove, copy, flash, grant flash and convert cards
- **Route Selection**: Identifies rest, event, elite and normal enemy nodes
- **Mental Breakdown Treatment**: Visits the trauma center automatically
- **Save Data Handling**: Deletes save data, with a configurable retention count
- **Zero System Support**: Handles Codex search

### Story Mode (Semi-Auto)
- **Auto Dialogue**: Skips story dialogue
- **Manual Mode Switching**: Hand back to Sortie or Chaos mode for battles and chaos stages

### Config Export & Import
- **Export**: Encodes the current mode's configuration as a text code you can share
- **Import**: Applies a shared configuration code, across versions

### Config Sync & Hot Configs
- **Disabled by default in this fork.** The upload pool is the upstream CN community's, and a Global client's card and
  combatant names do not match anything in it, so uploads would be noise and the downloaded configs unusable here.
  Turn it back on under Config Upload if you play a Chinese client and want to take part.

### Settings
- **Names are picked from a list, not typed.** Cards, equipment and combatants come from the client's own
  localization data, so a typo cannot silently stop a setting matching. The picker gains a search box once the
  list is long, which it is for cards.
- **The picker opens instantly, however long the list.** Chaos Mode's card settings offer nearly 1,500 options,
  which ok-script draws as a grid of that many real buttons. Here the option pane only builds the rows you can
  actually see, so opening it and searching it stay immediate.
- **Hover an option to see what it does.** Cards and equipment carry their in-game effect text and base values,
  taken from the client's own data, so you can build a removal or copy list without looking anything up. The
  tooltip appears as soon as the row is under the cursor rather than after the usual delay. Attack values are
  the card's base coefficient, not the damage a particular Combatant would deal. Search still matches names
  only.
- **Switching to this build re-seeds those settings.** Upstream ships one Chinese player's build as the
  defaults, and those names can never match what the OCR reads on a Global client, so they are cleared on
  first launch. Nothing is lost that would have worked.
- **Route Priority is the exception** and stays on its original values. Those are internal labels rather than
  text read off the screen, so they are only translated for display.

### General
- **Resolutions**: 1920x1080, 1600x900, 1280x720 and other 16:9 sizes
- **Background Mode**: Runs while the game window is minimized or obscured
- **Clients**: Global (English) is the focus of this fork. Simplified and Traditional Chinese still work, including
  Android emulators, via the Game Language setting in each mode

## Usage Guide

1. **Global client**: nothing to set. Game Language already defaults to English, and the game text itself is
   handled by the reverse OCR catalog described below.
2. **Chinese clients**: set Game Language to Simplified or Traditional Chinese in the mode you use.
3. **Auto Battle**: relies on keybind recognition, so enable shortcut key display in the game's settings.
4. **Chaos Manifestation**: turn on the game's own auto-battle and auto-story options.
5. **Story Mode**: enable Sortie Mode by hand for battle stages and Chaos Mode for chaos stages. Battle teams must be
   configured manually.

## Troubleshooting

1. **Antivirus**: add the install directory to your antivirus exceptions, Windows Defender included.
2. **Display settings**: turn off graphics card filters and sharpening, use the game's default brightness, and disable
   overlays that draw on the game window.
3. **Resolution**: make sure the game is running at a 16:9 aspect ratio.
4. **Version**: check you are on the latest release.

---

## Developer Zone

### Running from source

```bash
pip install -r requirements.txt --upgrade

python main.py          # release mode
python main_debug.py    # debug mode
```

```powershell
.\run_tests.ps1         # every tests\Test*.py, each in its own process
```

### Translations

Two catalogs live under `i18n/`, and they run in **opposite directions**:

| Catalog | Direction | Holds |
| --- | --- | --- |
| `ok.po` | Chinese msgid to English msgstr | App UI labels, task names, setting descriptions |
| `ocr.po` | English msgid to Chinese msgstr | Game text read off the screen |

`ocr.po` is what makes the Chinese task code work against an English client. The framework applies it in
`Task.fix_texts()` before any handler sees a text box, rewriting English game text into the Chinese literal the
handler compares against. That is why `ok_tasks/` needs no changes for the Global client.

**Never put UI strings in `ocr.po`.** It rewrites game text, so a stray entry there corrupts recognition.

Every `ocr.po` entry carries a `# From <handler>: <literal>` comment naming the call site it serves. That provenance is
what keeps merging from upstream mechanical: the new Chinese literals a merge brings in can be diffed against those
comments to find what still needs an English entry.

The app only ever reads the compiled `.mo`, so recompile after editing a `.po`:

```bash
python scripts/compile_i18n.py            # write the .mo files
python scripts/compile_i18n.py --check    # verify only, as CI does
```

To find the English text for a new entry, dump a screenshot the way the app reads it:

```bash
python scripts/ocr_dump.py <image> --missing
```

### Staying in sync with upstream

Upstream is `baoxin1100/ok-kes`. Changes here are kept additive so merges stay clean:

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
