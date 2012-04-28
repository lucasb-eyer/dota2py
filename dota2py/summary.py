"""
Try and extract useful information from a Dota 2 replay
"""

from dota2py import parser
from dota2py.proto import demo_pb2, usermessages_pb2, netmessages_pb2
from dota2py.proto import dota_usermessages_pb2
from collections import defaultdict
from functools import partial

index = 0


def debug_dump(message, file_prefix="dump"):
    """
    Utility while developing to dump message data to play with in the
    interpreter
    """

    global index
    index += 1

    with open("%s_%s.dump" % (file_prefix, index), 'w') as f:
        f.write(message.SerializeToString())
        f.close()


def get_side_attr(attr, invert, player):
    """
    Get a player attribute that depends on which side the player is on.
    A creep kill for a radiant hero is a badguy_kill, while a creep kill
    for a dire hero is a goodguy_kill.
    """
    t = player.team
    if invert:
        t = not player.team

    return getattr(player, "%s_%s" % ("goodguy" if t else "badguy", attr))



class Player(object):
    """
    All the information we collect about a player. The idea is that we collect
    everything, and then you can set a verbosity in get_dict to filter how
    detailed the information you get out is. For the moment we just start with
    the basics
    """


    def __init__(self):
        self.hero = None
        self.name = None
        self.team = None
        self.index = None
        self.kills = []
        self.deaths = []

        self.creep_kill_types = defaultdict(int)
        self.creep_deny_types = defaultdict(int)

        self.neutral_kills = 0
        self.roshan_kills = 0

        self.goodguy_kills = 0
        self.badguy_kills = 0

        self.goodguy_tower_kills = 0
        self.badguy_tower_kills = 0

        self.goodguy_rax_kills = 0
        self.badguy_rax_kills = 0

        self.goodguy_building_kills = 0
        self.badguy_building_kills = 0

        self.creep_types = {
            "npc_dota_creep_goodguys" : "goodguy_kills",
            "npc_dota_creep_badguys" : "badguy_kills",
            "npc_dota_goodguys_siege" : "goodguy_kills",
            "npc_dota_badguys_siege" : "badguy_kills",
            "npc_dota_dark_troll_warlord_skeleton_warrior" : "neutral_kills",
            "npc_dota_neutral" : "neutral_kills",
            "npc_dota_roshan" : "roshan_kills",
            "npc_dota_badguys_tower" : "badguy_tower_kills",
            "npc_dota_goodguys_tower" : "goodguy_tower_kills",
            "npc_dota_badguys_melee_rax" : "badguy_rax_kills",
            "npc_dota_goodguys_melee_rax" : "goodguy_rax_kills",
            "npc_dota_badguys_range_rax" : "badguy_rax_kills",
            "npc_dota_goodguys_range_rax" : "goodguy_rax_kills",
            "npc_dota_badguys_fillers" : "badguy_building_kills",
            "npc_dota_goodguys_fillers" : "goodguy_building_kills",
        }

    creep_kills = property(partial(get_side_attr,"kills", False))
    creep_denies = property(partial(get_side_attr, "kills", True))
    tower_kills = property(partial(get_side_attr,"tower_kills", False))
    tower_denies = property(partial(get_side_attr,"tower_kills", True))
    rax_kills = property(partial(get_side_attr,"rax_kills", False))
    rax_denies = property(partial(get_side_attr,"rax_kills", True))
    building_kills = property(partial(get_side_attr,"building_kills", False))
    building_denies = property(partial(get_side_attr,"building_kills", True))

    def add_kill(self, target, timestamp):
        self.kills.append((target, timestamp))

    def add_death(self, source, timestamp):
        self.deaths.append((source, timestamp))

    def creep_kill(self, target, timestamp):
        """
        A creep was tragically killed. Need to split this into radiant/dire
        and neutrals
        """
        self.creep_kill_types[target] += 1

        matched = False
        for k, v in self.creep_types.iteritems():
            if target.startswith(k):
                matched = True
                setattr(self, v, getattr(self, v) + 1)

        if not matched:
            print '> unhandled creep type', self.hero, target

    def __str__(self):
        return str(self.get_dict())

    def get_dict(self, verbosity=1):
        d = {
            "hero": self.hero,
            "name": self.name,
            "team": self.team,
            "index": self.index,
            "kills": len(self.kills),
            "deaths": len(self.deaths),
            "creep_kills": self.creep_kills + self.neutral_kills,
            "creep_denies": self.creep_denies,
            "tower_kills" : self.tower_kills,
            "tower_denies" : self.tower_denies,
            "rax_kills" : self.rax_kills,
            "rax_denies" : self.rax_denies,
            "roshan_kills" : self.roshan_kills,
        }

        if verbosity > 3:
            d["creep_kill_types"] = self.creep_kill_types
            d["creep_deny_types"] = self.creep_deny_types
            d["kill_list"] = self.kills,
            d["death_list"] = self.deaths,
            d["building_kills"] = self.building_kills,
            d["building_denis"] = self.building_denies,

        return d


class DemoSummary(object):
    """
    A collection of useful information from the demo
    """

    def __init__(self, filename, verbosity=3, frames=None):
        self.filename = filename
        self.frames = frames
        self.verbosity = verbosity

        self.info = defaultdict(dict)

        self.heroes = defaultdict(Player)
        self.player_info = {}

    def parse(self):
        print "Parsing demo '%s' for game information" % (self.filename, )

        self.dp = parser.DemoParser(self.filename, verbosity=1,
                                    frames=self.frames, hooks={
            demo_pb2.CDemoFileInfo: self.parse_file_info,
            parser.GameEvent: self.parse_game_event,
            parser.PlayerInfo: self.parse_player_info,
            usermessages_pb2.CUserMsg_TextMsg: self.parse_user_message,
            dota_usermessages_pb2.CDOTAUserMsg_ChatEvent: self.parse_dota_um,
            dota_usermessages_pb2.CDOTAUserMsg_OverheadEvent:
                self.parse_overhead_event,
        })
        self.dp.parse()

        for hero, player in self.heroes.iteritems():
            player.hero = hero

        #self.info["heroes"] = self.heroes

    def parse_overhead_event(self, event):
        if event.message_type == dota_usermessages_pb2.OVERHEAD_ALERT_GOLD:
            pass

    def parse_dota_um(self, user_message):
        """
        The chat messages that arrive when certain events occur.
        The most useful ones are CHAT_MESSAGE_RUNE_PICKUP,
        CHAT_MESSAGE_RUNE_BOTTLE, CHAT_MESSAGE_GLYPH_USED,
        CHAT_MESSAGE_TOWER_KILL
        """
        pass

    def parse_user_message(self, user_message):
        """
        The combat summaries come through as CUserMsg_TextMsg objects
        """
        #print user_message
        #debug_dump(user_message, 'user_message')

    def parse_player_info(self, player):
        """
        Parse a PlayerInfo struct. This arrives before a FileInfo message
        """
        if not player.ishltv:
            self.player_info[player.name] = {
                "user_id": player.userID,
                "guid": player.guid,
                "bot": player.fakeplayer,
            }

    def parse_file_info(self, file_info):
        """
        The CDemoFileInfo contains our winners as well as the length of the
        demo
        """

        self.info["playback_time"] = file_info.playback_time
        self.info["match_id"] = file_info.game_info.dota.match_id
        self.info["game_mode"] = file_info.game_info.dota.game_mode
        self.info["game_winner"] = file_info.game_info.dota.game_winner

        for index, player in enumerate(file_info.game_info.dota.player_info):
            p = self.heroes[player.hero_name]
            p.name = player.player_name
            p.index = index
            p.team = 0 if index < 5 else 1

            self.info["players"][player.player_name] = p

    def parse_game_event(self, ge):
        """
        Game events contain the combat log as well as 'chase_hero' events which
        could be interesting
        """

        if ge.name == "dota_combatlog":
            if ge.keys["type"] == 4:
                #Something died
                try:
                    source = self.dp.combat_log_names[ge.keys["sourcename"]]
                    target = self.dp.combat_log_names[ge.keys["targetname"]]
                    target_illusion = ge.keys["targetillusion"]
                    timestamp = ge.keys["timestamp"]

                    if (target.startswith("npc_dota_hero") and not
                        target_illusion):

                        self.heroes[target].add_death(source, timestamp)
                        self.heroes[source].add_kill(target, timestamp)
                    elif source.startswith("npc_dota_hero"):
                        self.heroes[source].creep_kill(target, timestamp)
                except KeyError, e:
                    """
                    Sometimes we get combat logs for things we dont have in
                    combat_log_names. My theory is that the server sends
                    us incremental updates to the string table using
                    CSVCMsg_UpdateStringTable but I'm not sure how to parse
                    that
                    """
                    pass

                #To get what spell/thing killed I think we probably look at the
                #combatlog event right before this one

    def print_info(self, d=None, indentation=0):
        for k, v in (d or self.info).items():
            if isinstance(v, dict):
                print "%s%s:" % ('  ' * indentation, k)
                self.print_info(v, indentation + 1)
            else:
                print "%s%s: %s" % ('  ' * indentation, k, v)


def main():
    import argparse
    p = argparse.ArgumentParser(description="Dota 2 demo parser")
    p.add_argument('demo', help="The .dem file to parse")
    p.add_argument("--verbosity", dest="verbosity", default=3, type=int,
                        help="how verbose [1-5] (optional)")
    p.add_argument("--frames", dest="frames", default=None, type=int,
                        help="maximum number of frames to parse (optional)")

    args = p.parse_args()

    d = DemoSummary(args.demo, verbosity=args.verbosity, frames=args.frames)
    d.parse()
    d.print_info()

if __name__ == "__main__":
    main()
