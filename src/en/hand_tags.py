"""Equipment labels read by hand, for the pieces the game never labelled itself.

The game labels equipment with the kind of deck it serves and scores each combatant against those kinds, but
only fills that in for Sortie. `game_quality.py` carries the labels across to the Chaos copies of the same
relics, reaching 141 of the 239 pieces a Chaos run can meet. The rest have no Sortie counterpart at all, so no
rule can reach them. This table is those gaps, read off each piece's own effect text against the worked
examples in the generated table - a judgement, not the developers' answer, so the generated table wins wherever
both have an entry and this file is consulted only for a name the generator left out.

A piece is left out when its effect does not clearly serve a kind some combatant actually wants. Roughly half
are: flat stat lines, Stress, Credits, Damage Reduction and Epiphany triggers serve no listed kind, and
inventing one would steer a purchase on a guess. A missing entry reads as "no opinion" and leaves the run where
it already was, so silence is the cheaper mistake.

Two were read off the wrong text at first, and the trap is worth knowing: `Flashbang` and `Nature's Gift` name
a card as well as a relic, and `game_text.py` keeps the card's description for a shared name. The relic's own
wording is on its Sortie tier, under `Mutation:` or `Harmonization:`.

Hand-maintained - unlike its neighbours this one is not regenerated. After a game patch, re-run
`scripts/build_game_data.py` first, then check whether anything here has since been labelled properly, in
which case the entry can go.
"""

# Keyed by the client's own spelling, and valued with the game's own vocabulary of kinds. `TestHandTags`
# pins both: a name that is not real equipment, or a kind no combatant weighs, fails the suite.
HAND_TAGS = {
    'A Lonesome Wedding Ring': ('discard',),
    'Bloodstone of the Void': ('heal',),
    'Bone Ring of Wildfire': ('multiatk', 'powercard'),
    'Broken Golden Quill Pen': ('discard',),
    'Chaos Scripture': ('allatk',),
    'Chimeranite': ('draw',),
    'Chitin Shield': ('counter',),
    'Cloak of the Heart': ('discard',),
    'Closed-Circuit Terminal': ('allatk',),
    'Contaminated Cocoon Cape': ('weak',),
    'Corrupted Gauntlet': ('addatk', 'cri'),
    'Crimson Bloodstone': ('heal',),
    'Crushed Angel Feather': ('ac',),
    'Crustacean Fluider': ('shield',),
    'Cycle of Circulation': ('heal',),
    'Essence-Fragmented Necklace': ('ap',),
    'Essence-Fueled Gauntlets': ('cri', 'shield'),
    'Final Entry': ('allatk',),
    'Flashbang': ('ac', 'weak'),
    'Flower of Dead Souls': ('multiatk',),
    'Forbidden Scripture': ('allatk',),
    'Gauntlets of Protection': ('allatk', 'highcost'),
    'Gospel of Lament': ('ac',),
    'Hymn-Singing Lips': ('discard',),
    'Incomprehensible Holy Object': ('discard', 'shield'),
    'Invader Observation Logs': ('cri', 'multiatk'),
    'Kaleidoscope Fragment': ('weak',),
    'Kentris Chitin Armor': ('shield',),
    'Kirak’s Core': ('heal',),
    'Light Combat Suit': ('shield',),
    'M.S.S Scope': ('shield',),
    'M.S.S. Data Pad': ('weak',),
    'Magic-Infused Sapphire': ('break', 'initiate'),
    'Moon of Destruction': ('allatk',),
    'Nature’s Gift': ('heal',),
    'Nightmare Hairpin': ('ac',),
    'Order’s Baton': ('create',),
    'Pagna Mushroom': ('weak',),
    'Palasia’s Orb': ('weak',),
    'Raider’s Harpoon Gun': ('allatk', 'cri'),
    'Raider’s Scanning Gear': ('cri',),
    'Remnants of Succession': ('multiatk',),
    'Singing Sword': ('bullet',),
    'Source of the Forbidden': ('weak',),
    'Stele of Heresy': ('discard', 'mark', 'weak'),
    'Sun-Setting Bow': ('highcost',),
    'The Chosen Vessel': ('shield',),
    'The Destruction of Erysichthon': ('multiatk',),
    'The Golden Rule': ('multiatk', 'shield'),
    'Twisted Discipline': ('ap',),
    'Twisted Drill Bit': ('allatk',),
    'W-52 "Dopamine Injector"': ('draw',),
    'Wolves Bane’s Spine': ('cri', 'shield'),
}
