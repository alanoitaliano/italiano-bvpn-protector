"""Works around a berconpy bug in its "players" command parser.

berconpy.ext.arma.parser._PLAYERS_ROW captures the GUID status as `\\w+`, but a
real BE server reports an unverified player's status as a literal "?" (e.g.
"c779d3...(?)  SomePlayer"), which isn't a word character. That makes the whole
row fail to match, so an unverified player is silently dropped from
`ArmaClient.fetch_players()` results entirely - including the initial-scan and
periodic-poll safety nets this app relies on to catch a blacklisted player who's
already connected (berconpy 3.1.4).
"""

from __future__ import annotations

import re

from berconpy.ext.arma import parser as _arma_parser

_arma_parser._PLAYERS_ROW = re.compile(
    r"(?P<id>\d+) +(?P<addr>.*?:\d+) +(?P<ping>\d+) +"
    r"(?P<guid>\w+)\((?P<guid_status>[^)]+)\) +(?P<name>.+)"
)
