#!/usr/bin/env python3

import curses
import json
import os
import random
import signal
import time
from collections import Counter
from dataclasses import dataclass, asdict
from itertools import combinations
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================

APP_DIR = Path.cwd()
SAVE_DIR = APP_DIR / "saves"
SAVE_FILE = SAVE_DIR / "tournament.json"

DEFAULTS = {
    "starting_stack": 1000,
    "small_blind": 10,
    "big_blind": 20,
    "bot_count": 3,
    "blind_increase_every": 10,
    "blind_step": 5,
}

MIN_BOTS, MAX_BOTS = 1, 7

NAMES = [
    "Alex", "Angel", "Bili", "Beth", "Chris", "Daniel", "David",
    "Dakota", "Dominica", "Amy", "Frank", "George", "Grace", "Harry",
    "Igor", "Joanna", "Jill", "James", "John", "Kendra", "Carl",
    "Kevin", "Kristy", "Leon", "Liam", "Lucas", "Mark", "Mia", "Max",
    "Michael", "Melanie", "Nathan", "Nick", "Noah", "Oliver", "Oscar",
    "Patrick", "Paul", "Penelope", "Robert", "Ryan", "Samuel", "Simon",
    "Sam", "Tiffanny", "Victor", "William",
]

EASTER_EGGS = [
    "Gordon Freeman", "Walter White", "Tony Hawk", "Saul Goodman",
    "JFK", "Neo", "Rambo", "Batman", "Captn' Knuckles", "Bruce Wayne",
]

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = [(r, v) for r, v in zip(
    ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"],
    range(2, 15)
)]

HAND_NAMES = {
    8: "STRAIGHT FLUSH",
    7: "FOUR OF A KIND",
    6: "FULL HOUSE",
    5: "FLUSH",
    4: "STRAIGHT",
    3: "THREE OF A KIND",
    2: "TWO PAIR",
    1: "PAIR",
    0: "HIGH CARD",
}

# ============================================================
# BASIC HELPERS
# ============================================================

def money(value):
    return f"${value}"


def active_players(players):
    return [p for p in players if p.active and p.stack > 0]


def alive_players(players):
    return [p for p in players if p.active and not p.folded]


def can_act(player):
    return player.active and not player.folded and not player.all_in and player.stack > 0


def call_amount(player, current_bet):
    return max(0, current_bet - player.street_bet)


def next_active_index(players, start):
    for i in range(1, len(players) + 1):
        index = (start + i) % len(players)
        if players[index].active and players[index].stack > 0:
            return index
    return None


def put_chips(player, amount):
    amount = min(max(0, amount), player.stack)
    player.stack -= amount
    player.hand_bet += amount
    player.street_bet += amount
    player.total_bet += amount

    if player.stack == 0:
        player.all_in = True

    return amount

# ============================================================
# FILES
# ============================================================

def ensure_save_dir():
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

def save_exists():
    return SAVE_FILE.exists()

def delete_save():
    try:
        SAVE_FILE.unlink()
    except FileNotFoundError:
        pass

# ============================================================
# CARDS
# ============================================================

@dataclass
class Card:
    rank: str
    value: int
    suit: str

    def __str__(self):
        return f"{self.rank}{self.suit}"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

class Deck:
    def __init__(self):
        self.cards = [
            Card(rank, value, suit)
            for suit in SUITS
            for rank, value in RANKS
        ]
        random.shuffle(self.cards)

    def deal(self):
        return self.cards.pop()

# ============================================================
# PLAYER
# ============================================================

class Player:
    def __init__(self, name, stack, human=False):
        self.name = name
        self.stack = stack
        self.human = human
        self.cards = []
        self.hand_bet = 0
        self.street_bet = 0
        self.total_bet = 0
        self.folded = False
        self.all_in = False
        self.active = True

    def reset_hand(self):
        self.cards = []
        self.hand_bet = self.street_bet = 0
        self.folded = self.all_in = False
        self.total_bet = 0

    def to_dict(self):
        return {
            "name": self.name,
            "stack": self.stack,
            "human": self.human,
            "cards": [c.to_dict() for c in self.cards],
            "hand_bet": self.hand_bet,
            "street_bet": self.street_bet,
            "total_bet": self.total_bet,
            "folded": self.folded,
            "all_in": self.all_in,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, data):
        p = cls(data["name"], data["stack"], data.get("human", False))
        p.cards = [Card.from_dict(c) for c in data.get("cards", [])]

        for key in (
            "hand_bet", "street_bet", "total_bet",
            "folded", "all_in", "active",
        ):
            setattr(p, key, data.get(key, getattr(p, key)))
        return p

# ============================================================
# SETTINGS
# ============================================================

class Settings:
    def __init__(self, **kwargs):
        cfg = DEFAULTS | kwargs

        self.starting_stack = cfg["starting_stack"]
        self.small_blind = cfg["small_blind"]
        self.big_blind = cfg["big_blind"]
        self.bot_count = cfg["bot_count"]
        self.blind_level = 0
        self.blind_increase_every = cfg["blind_increase_every"]
        self.blind_step = cfg["blind_step"]

    def to_dict(self):
        return {
            "starting_stack": self.starting_stack,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "bot_count": self.bot_count,
            "blind_increase_every": self.blind_increase_every,
            "blind_step": self.blind_step,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**{
            key: data.get(key, DEFAULTS[key])
            for key in DEFAULTS
        })

# ============================================================
# HAND EVALUATION
# ============================================================

def straight_high(values):
    values = set(values)
    if 14 in values:
        values.add(1)

    for high in range(14, 4, -1):
        if all(high - i in values for i in range(5)):
            return high
    return None

def evaluate_five(cards):
    values = sorted((c.value for c in cards), reverse=True)
    counts = Counter(values)
    flush = len({c.suit for c in cards}) == 1
    straight = straight_high(values)

    pair_values = sorted(
        (v for v, n in counts.items() if n >= 2),
        reverse=True,
    )

    if flush and straight:
        return 8, straight

    quads = [v for v, n in counts.items() if n == 4]
    if quads:
        q = max(quads)
        return 7, q, max(v for v in values if v != q)

    trips = sorted(
        (v for v, n in counts.items() if n == 3),
        reverse=True,
    )
    pairs = sorted(
        (v for v, n in counts.items() if n >= 2),
        reverse=True,
    )

    if trips:
        t_val = trips[0]
        real_pairs = [v for v in pair_values if v != t_val]
        if real_pairs:
            return 6, t_val, real_pairs[0]

    if flush:
        return 5, *values

    if straight:
        return 4, straight

    if trips:
        t_val = trips[0]
        return 3, t_val, *[v for v in values if v != t_val][:2]

    if len(pair_values) >= 2:
        high, low = pair_values[:2]
        kicker = max(v for v in values if v not in (high, low))
        return 2, high, low, kicker

    if len(pair_values) == 1:
        pair = pair_values[0]
        kickers = [v for v in values if v != pair][:3]
        return 1, pair, *kickers

    return 0, *values

def evaluate_hand(cards):
    if len(cards) < 5:
        return None

    return max(evaluate_five(combo) for combo in combinations(cards, 5))

# ============================================================
# POTS
# ============================================================

def total_pot(players):
    return sum(p.hand_bet for p in players)

def build_side_pots(players):
    levels = sorted({p.hand_bet for p in players if p.hand_bet})
    pots = []
    previous = 0

    for level in levels:
        contributors = [p for p in players if p.hand_bet >= level]
        amount = (level - previous) * len(contributors)

        if amount:
            pots.append({
                "amount": amount,
                "eligible": [
                    p for p in contributors
                    if p.active and not p.folded
                ],
            })

        previous = level

    return pots

def resolve_all_pots(players, community):
    results = []

    for pot in build_side_pots(players):
        eligible = pot["eligible"]
        if not eligible:
            continue

        scores = [(evaluate_hand(p.cards + community), p) for p in eligible]
        best = max(score for score, _ in scores)
        winners = [p for score, p in scores if score == best]

        share, remainder = divmod(pot["amount"], len(winners))

        for i, winner in enumerate(winners):
            winner.stack += share + (i < remainder)

        results.append({
            "amount": pot["amount"],
            "winners": winners,
            "score": best,
        })

    return results

# ============================================================
# CURSES UI
# ============================================================

def safe_add(stdscr, y, x, text, attr=0):
    try:
        h, w = stdscr.getmaxyx()
        if 0 <= y < h and 0 <= x < w:
            stdscr.addstr(y, x, str(text)[:w - x - 1], attr)
    except curses.error:
        pass

def card_color(card):
    return curses.color_pair(2 if card.suit in "♥♦" else 1)

def draw_card(stdscr, y, x, card, hidden=False):
    text = "[ ?? ]" if hidden else f"[ {card.rank}{card.suit} ]"
    color = curses.color_pair(1) if hidden else card_color(card)

    try:
        stdscr.addstr(y, x, text, color | curses.A_BOLD)
    except curses.error:
        pass

def draw_table(
    stdscr,
    players,
    community,
    current=-1,
    street="WAITING",
    message="",
):
    stdscr.erase()
    height, width = stdscr.getmaxyx()

    if width < 90 or height < 30:
        safe_add(stdscr, 2, 2, "Terminal too small! Minimum: 90x30", curses.A_BOLD)
        stdscr.refresh()
        return

    title = " TEXAS HOLD'EM "
    safe_add(
        stdscr, 0, (width - len(title)) // 2,
        title, curses.color_pair(3) | curses.A_BOLD,
    )

    safe_add(stdscr, 2, 3, f"POT: {money(total_pot(players))}", curses.A_BOLD)
    safe_add(stdscr, 2, width - 25, f"STREET: {street}", curses.A_BOLD)

    safe_add(stdscr, 4, 3, "BOARD", curses.color_pair(3) | curses.A_BOLD)

    for i, card in enumerate(community):
        draw_card(stdscr, 4, 12 + i * 10, card)

    positions = [
        (8, 3), (8, 48), (16, 3), (16, 48),
        (8, 70), (16, 70), (22, 3), (22, 48),
    ]

    for i, player in enumerate(players[:len(positions)]):
        if not player.active:
            continue

        y, x = positions[i]

        if player.folded:
            name = f"{player.name} [FOLDED]"
            attr = curses.color_pair(4) | curses.A_BOLD
        elif i == current:
            name = f"> {player.name} <"
            attr = curses.color_pair(3) | curses.A_BOLD
        else:
            name = player.name
            attr = curses.A_BOLD

        safe_add(stdscr, y, x, name, attr)
        safe_add(stdscr, y + 1, x, f"Stack: {money(player.stack)}")
        safe_add(stdscr, y + 2, x, f"Bet:   {money(player.hand_bet)}")

        if player.all_in:
            safe_add(
                stdscr, y + 3, x, "ALL-IN",
                curses.color_pair(3) | curses.A_BOLD,
            )

        show = player.human or player.folded or street == "SHOWDOWN"

        for j, card in enumerate(player.cards):
            draw_card(stdscr, y + 5, x + j * 10, card, not show)

    safe_add(stdscr, height - 6, 3, "-" * min(width - 6, 110))
    safe_add(stdscr, height - 5, 3, "ACTION:", curses.color_pair(3) | curses.A_BOLD)
    safe_add(stdscr, height - 5, 12, message)

    controls = (
        "[C] Check/Call  [R] Raise  [F] Fold  [A] All-in  "
        "[P] Incognito  [Q] Quit"
        if current == 0 else
        "[P] Incognito  [Q] Quit"
    )

    safe_add(stdscr, height - 3, 3, controls, curses.A_BOLD)
    stdscr.refresh()

# ============================================================
# INPUT / SHELL
# ============================================================

def wait_key(stdscr):
    stdscr.nodelay(False)
    key = stdscr.getch()
    stdscr.nodelay(True)
    return key

def ask_number(stdscr, prompt, minimum, maximum):
    curses.echo()
    stdscr.nodelay(False)

    try:
        h, w = stdscr.getmaxyx()
        safe_add(stdscr, h - 2, 2, prompt)
        stdscr.refresh()

        raw = stdscr.getstr(
            h - 2,
            min(w - 20, len(prompt) + 3),
            12,
        ).decode("utf-8", "ignore")

    finally:
        curses.noecho()
        stdscr.nodelay(True)

    try:
        value = int(raw)
        return value if minimum <= value <= maximum else None
    except ValueError:
        return None

def incognito_mode(stdscr):
    curses.def_prog_mode()
    curses.endwin()

    # Czyszczenie terminala przed oddaniem kontroli systemowi
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\nCheck logs in journalctl -b -p 5")

    try:
        # Zawieszamy proces (symulacja Ctrl+Z)
        os.kill(os.getpid(), signal.SIGTSTP)
    finally:
        # KROK NAPRAWCZY: Gdy gra wznawia działanie, natychmiast czyścimy śmieci z powłoki shella
        os.system('cls' if os.name == 'nt' else 'clear')
        
        curses.reset_prog_mode()
        stdscr.keypad(True)
        stdscr.nodelay(False)
        curses.curs_set(0)
        
        # Wymuszamy pełne, sprzętowe przemalowanie ekranu od zera (odpowiednik Ctrl+L w curses)
        stdscr.clearok(True)
        stdscr.erase()
        stdscr.touchwin()
        stdscr.refresh()

def check_global_keys(stdscr):
    stdscr.nodelay(True)

    while True:
        key = stdscr.getch()

        if key == -1:
            return None
        if key in (ord("q"), ord("Q")):
            return "quit"
        if key in (ord("p"), ord("P")):
            incognito_mode(stdscr)
            return "incognito"

def pause_with_keys(stdscr, seconds):
    end = time.monotonic() + seconds

    while time.monotonic() < end:
        if check_global_keys(stdscr) == "quit":
            return "quit"
        time.sleep(0.03)

def next_hand_input(stdscr):
    stdscr.nodelay(False)
    safe_add(
        stdscr,
        stdscr.getmaxyx()[0] - 1,
        2,
        "ENTER = next hand | P = incognito | Q = menu",
        curses.A_BOLD,
    )
    stdscr.refresh()

    key = stdscr.getch()

    if key in (ord("q"), ord("Q")):
        return "quit"

    if key in (ord("p"), ord("P")):
        incognito_mode(stdscr)

    return "continue"

# ============================================================
# HUMAN ACTION
# ============================================================

def human_action(
    stdscr,
    players,
    community,
    current_bet,
    min_raise,
    street,
    tournament=None,
):
    player = players[0]

    while True:
        to_call = call_amount(player, current_bet)
        message = (
            "CHECK / RAISE / FOLD / ALL-IN"
            if not to_call
            else f"To call: {money(to_call)}"
        )

        draw_table(
            stdscr, players, community, 0,
            street, message,
        )

        key = wait_key(stdscr)

        if key in (ord("p"), ord("P")):
            incognito_mode(stdscr)
            continue

        if key in (ord("q"), ord("Q")):
            return "quit", 0

        # RĘCZNY ZAPIS W TURZE GRACZA
        if key in (ord("s"), ord("S")):
            if tournament:
                save_tournament(tournament)
                # Szybki flash komunikatu na dole ekranu
                h, w = stdscr.getmaxyx()
                safe_add(stdscr, h - 5, 12, "GAME SAVED!                               ")
                stdscr.refresh()
                time.sleep(0.6)
            continue

        if key in (ord("f"), ord("F")):
            return "fold", 0

        if key in (ord("c"), ord("C")):
            return (
                ("check", 0)
                if not to_call
                else ("call", min(to_call, player.stack))
            )

        if key in (ord("a"), ord("A")):
            return "allin", player.stack

        if key in (ord("r"), ord("R")):
            maximum = player.street_bet + player.stack
            minimum = min(current_bet + min_raise, maximum)

            if maximum <= current_bet:
                continue

            amount = ask_number(
                stdscr,
                f"Raise to [{minimum}-{maximum}]:",
                minimum,
                maximum,
            )

            if amount is not None:
                return "raise", amount - player.street_bet


# ============================================================
# BOT AI
# ============================================================

def bot_action(
    player,
    players,
    community,
    current_bet,
    min_raise,
    settings,
):
    to_call = call_amount(player, current_bet)
    stack = player.stack
    bb = settings.big_blind
    pot = total_pot(players)
    roll = random.random()

    opponents = [
        p for p in players
        if p is not player and p.active and not p.folded
    ]
    opponent_count = len(opponents)

    pot_odds = to_call / (pot + to_call) if pot + to_call else 0

    def call():
        return "call", min(to_call, stack)

    def raise_by(amount):
        target = min(
            current_bet + amount,
            player.street_bet + stack,
        )
        if target > current_bet:
            return "raise", target - player.street_bet
        return call()

    def random_raise(sizes):
        return raise_by(bb * random.choice(sizes))

    cards = player.cards + community

    # --------------------------------------------------------
    # PRE-FLOP
    # --------------------------------------------------------

    if not community:
        values = sorted((c.value for c in player.cards), reverse=True)
        high, low = values
        pair = high == low
        suited = player.cards[0].suit == player.cards[1].suit
        connected = high - low <= 2

        premium = (pair and high >= 10) or (high == 14 and low >= 10)
        strong = premium or pair or high >= 13
        playable = strong or suited or connected or high >= 10

        if not to_call:
            if premium and roll < .70:
                return random_raise([2, 3, 4])

            if strong and roll < .45:
                return random_raise([1, 2, 3])

            bluff = .08
            if opponent_count == 1:
                bluff = .16
            elif opponent_count == 2:
                bluff = .12

            if suited or connected:
                bluff += .05

            return random_raise([1, 2]) if roll < bluff else ("check", 0)

        if premium:
            return call() if roll < .20 else random_raise([2, 3, 4])

        if strong:
            if pot_odds < .20 and roll < .75:
                return call()

            if pot_odds < .35:
                if roll < .25:
                    return random_raise([1, 2])
                if roll < .90:
                    return call()

            if pot_odds < .50 and roll < .60:
                return call()

            if pair and high >= 10 and roll < .35:
                return call()

            return "fold", 0

        if playable:
            if pot_odds < .20 and roll < .75:
                return call()

            if pot_odds < .35 and roll < .55:
                return call()

            if (suited or connected) and pot_odds < .45 and roll < .35:
                return call()

            if opponent_count <= 2 and roll < .08:
                return random_raise([2])

            return "fold", 0

        if pot_odds < .15 and roll < .35:
            return call()

        if to_call <= bb and roll < .30:
            return call()

        bluff = .10 if opponent_count == 1 else .07 if opponent_count == 2 else .04

        if pot_odds < .25:
            bluff += .04

        return random_raise([2, 3]) if roll < bluff else ("fold", 0)

    # --------------------------------------------------------
    # POST-FLOP
    # --------------------------------------------------------

    hand = evaluate_hand(cards)
    strength = hand[0] if hand else 0

    suits = Counter(c.suit for c in cards)
    flush_draw = max(suits.values(), default=0) == 4

    values = sorted(set(c.value for c in cards))
    if 14 in values:
        values.append(1)

    straight_draw = any(
        max(combo) - min(combo) <= 4
        for combo in combinations(sorted(set(values)), 4)
    ) if len(values) >= 4 else False

    draw = flush_draw or straight_draw

    # Monster
    if strength >= 6:
        if roll < .20:
            return ("check", 0) if not to_call else call()
        return random_raise([2, 3, 4, 5])

    # Straight / flush
    if strength >= 4:
        if not to_call:
            return random_raise([1, 2, 3]) if roll < .60 else ("check", 0)

        if pot_odds < .45 and roll < .85:
            return call()

        return random_raise([2]) if roll < .25 else call()

    # Trips / two pair
    if strength >= 2:
        if not to_call:
            return random_raise([1, 2, 3]) if roll < .55 else ("check", 0)

        if pot_odds < .30 and roll < .90:
            return call()

        if pot_odds < .50 and roll < .70:
            return call()

        return random_raise([2]) if roll < .15 else ("fold", 0)

    # Pair
    if strength == 1:
        if not to_call:
            return random_raise([1, 2]) if roll < .35 else ("check", 0)

        if draw and pot_odds < .45 and roll < .75:
            return call()

        if pot_odds < .20 and roll < .80:
            return call()

        if pot_odds < .35 and roll < .55:
            return call()

        if pot_odds < .50 and roll < .25:
            return call()

        if opponent_count == 1 and roll < .06:
            return random_raise([2])

        return "fold", 0

    # Draw
    if draw:
        if not to_call:
            return random_raise([1, 2, 3]) if roll < .45 else ("check", 0)

        if pot_odds < .30 and roll < .75:
            return call()

        if pot_odds < .45 and roll < .50:
            return call()

        if opponent_count <= 2 and roll < .15:
            return random_raise([2, 3])

        return "fold", 0

    # High card / air
    if not to_call:
        bluff = .22 if opponent_count == 1 else .16 if opponent_count == 2 else .12
        return random_raise([1, 2, 3]) if roll < bluff else ("check", 0)

    if pot_odds < .15:
        if roll < .25:
            return call()
        if opponent_count == 1 and roll < .08:
            return random_raise([2])

    if pot_odds < .30:
        if roll < .15:
            return call()
        if opponent_count == 1 and roll < .05:
            return random_raise([2])

    return "fold", 0

# ============================================================
# BETTING
# ============================================================

def betting_round(
    stdscr,
    players,
    community,
    street,
    first_player,
    settings,
    tournament=None,
):
    if street != "PRE-FLOP":
        for p in players:
            p.street_bet = 0

    current_bet = max(
        (p.street_bet for p in players if p.active and not p.folded),
        default=0,
    )

    min_raise = settings.big_blind
    acted = set()
    index = first_player

    while True:
        if check_global_keys(stdscr) == "quit":
            return "quit"

        alive = alive_players(players)
        if len(alive) <= 1:
            return "continue"

        if not any(can_act(p) for p in alive):
            break

        player = players[index]

        if not can_act(player):
            index = (index + 1) % len(players)
            continue

        if player.human:
            action, amount = human_action(
                stdscr, players, community,
                current_bet, min_raise, street, tournament,
            )
            if action == "quit":
                return "quit"
        else:
            action, amount = bot_action(
                player, players, community,
                current_bet, min_raise, settings,
            )

            draw_table(
                stdscr, players, community,
                index, street,
                f"{player.name}: {action.upper()}",
            )

            if pause_with_keys(stdscr, .45) == "quit":
                return "quit"

        if action == "fold":
            player.folded = True
            acted.add(index)

        elif action == "check":
            if call_amount(player, current_bet):
                continue
            acted.add(index)

        elif action == "call":
            actual = put_chips(player, amount)
            acted.add(index)

        elif action in ("raise", "allin"):
            old = player.street_bet
            put_chips(player, amount if action == "raise" else player.stack)
            new = player.street_bet

            if new > current_bet:
                raise_size = new - current_bet
                current_bet = new
                min_raise = max(min_raise, raise_size)
                acted = {index}
            else:
                acted.add(index)

        alive = alive_players(players)
        if len(alive) <= 1:
            break

        ready = all(
            p.all_in
            or (
                p.street_bet == current_bet
                and players.index(p) in acted
            )
            for p in alive
        )

        if ready:
            break

        index = (index + 1) % len(players)

    return "continue"

# ============================================================
# SHOWDOWN
# ============================================================

def showdown(stdscr, players, community):
    pots = resolve_all_pots(players, community)

    clear_pot(players)

    lines = []
    for i, p in enumerate(pots):
        score_data = p['score']
        score_idx = score_data[0] if isinstance(score_data, (tuple, list)) else score_data
        lines.append(
            f"Pot {i + 1}: {money(p['amount'])} -> "
            f"{', '.join(w.name for w in p['winners'])} "
            f"({HAND_NAMES.get(score_idx, 'HIGH CARD')})"
        )

    while True:
        draw_table(
            stdscr,
            players,
            community,
            -1,
            "SHOWDOWN",
            " | ".join(lines),
        )

        key = wait_key(stdscr)

        if key in (ord("p"), ord("P")):
            incognito_mode(stdscr)
            continue

        if key in (ord("q"), ord("Q")):
            return "quit"

        return "continue"

# ============================================================
# HAND
# ============================================================
def clear_pot(players):
    for p in players:
        p.hand_bet = 0
        p.street_bet = 0
        p.total_bet =0

def award_uncontested(stdscr, players, community, street, dealer):
    alive = alive_players(players)

    if len(alive) != 1:
        return None

    winner = alive[0]
    pot = total_pot(players)
    winner.stack += pot

    clear_pot(players)

    draw_table(
        stdscr,
        players,
        community,
        -1,
        street,
        f"{winner.name} won {money(pot)}",
    )

    if pause_with_keys(stdscr, .8) == "quit":
        return "quit"

    return next_active_index(players, dealer)


def deal_hand(stdscr, players, dealer, settings, tournament=None):
    active = [i for i, p in enumerate(players) if p.active and p.stack > 0]

    if len(active) < 2:
        return "gameover", dealer

    if dealer not in active:
        dealer = active[0]

    deck = Deck()

    for p in players:
        p.reset_hand()

    community = []

    for _ in range(2):
        for i in active:
            players[i].cards.append(deck.deal())

    sb_index = dealer if len(active) == 2 else next_active_index(players, dealer)
    bb_index = next_active_index(players, sb_index)

    sb = players[sb_index]
    bb = players[bb_index]

    sb_amount = put_chips(sb, settings.small_blind)
    bb_amount = put_chips(bb, settings.big_blind)

    first = sb_index if len(active) == 2 else next_active_index(players, bb_index)

    message = (
        f"{sb.name} posts {money(sb_amount)} SB | "
        f"{bb.name} posts {money(bb_amount)} BB"
    )

    draw_table(stdscr, players, community, first, "PRE-FLOP", message)

    if pause_with_keys(stdscr, .5) == "quit":
        return "quit", dealer

    if betting_round(
        stdscr, players, community,
        "PRE-FLOP", first, settings, tournament
    ) == "quit":
        return "quit", dealer

    result = award_uncontested(
        stdscr, players, community,
        "WIN", dealer,
    )

    if result is not None:
        if result == "quit":
            return "quit", dealer
        return "continue", result  # Natychmiast kończy funkcję deal_hand i przechodzi do nowego rozdania

    for street, count in (("FLOP", 3), ("TURN", 1), ("RIVER", 1)):
        deck.deal()

        for _ in range(count):
            community.append(deck.deal())

        first = next_active_index(players, dealer)

        draw_table(stdscr, players, community, first, street, street)

        if pause_with_keys(stdscr, .4) == "quit":
            return "quit", dealer

        if betting_round(
            stdscr, players, community,
            street, first, settings, tournament
        ) == "quit":
            return "quit", dealer

        result = award_uncontested(
            stdscr, players, community,
            street, dealer,
        )

        if result is not None:
            if result == "quit":
                return "quit", dealer
            return "continue", result  # Przerywa obecne rozdanie, bo wszyscy zfolmowali
    result = showdown(stdscr, players, community)

    return (
        ("quit", dealer)
        if result == "quit"
        else ("continue", next_active_index(players, dealer))
    )

# ============================================================
# QUICK MATCH
# ============================================================

def make_quick_players(settings):
    names = random.sample(
        NAMES,
        min(settings.bot_count, len(NAMES)),
    )

    return [
        Player("YOU", settings.starting_stack, True),
        *(Player(name, settings.starting_stack) for name in names),
    ]


def increase_blinds(settings):
    settings.small_blind += settings.blind_step
    settings.big_blind = settings.small_blind * 2


def quick_game_over(stdscr, players):
    stdscr.erase()
    alive = active_players(players)
    winner = alive[0] if alive else None

    safe_add(stdscr, 8, 25, "====================", curses.A_BOLD)
    safe_add(
        stdscr, 10, 25, "     GAME OVER",
        curses.color_pair(3) | curses.A_BOLD,
    )

    if winner:
        safe_add(stdscr, 12, 25, f"{winner.name} won!", curses.A_BOLD)

    safe_add(stdscr, 16, 25, "R = restart")
    safe_add(stdscr, 17, 25, "Q = menu")
    stdscr.refresh()

    while True:
        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            return "menu"
        if key in (ord("r"), ord("R")):
            return "restart"


def quick_match(stdscr, settings):
    while True:
        game_settings = Settings(**settings.to_dict())
        players = make_quick_players(settings)
        dealer = 0
        hands = 0

        while len(active_players(players)) > 1:
            result, dealer = deal_hand(
                stdscr, players, dealer, game_settings,
            )

            if result in ("quit", "gameover"):
                return "menu"

            hands += 1

            if (
                game_settings.blind_increase_every
                and hands % game_settings.blind_increase_every == 0
            ):
                increase_blinds(game_settings)

            for p in players:
                if p.stack <= 0:
                    p.active = False

            if next_hand_input(stdscr) == "quit":
                return "menu"

        result = quick_game_over(stdscr, players)

        if result != "restart":
            return "menu"

# ============================================================
# TOURNAMENT
# ============================================================

class Tournament:
    def __init__(self, settings):
        self.settings = settings
        self.stage = 0
        self.round_number = 1
        self.total_hands = 0
        self.hands_won = 0
        self.total_winnings = 0
        self.opponents_faced = []
        self.hands_at_current_level = 0

        self.player = Player(
            "YOU",
            settings.starting_stack,
            True,
        )

        self.opponents = []
        self.current_match = None
        self.dealer = 0
        self.bracket = self.build_bracket()

    def build_bracket(self):
        return {
            "quarterfinal": [["YOU", "???", "???", "???"], ["", "", "", ""], ["", "", "", ""], ["", "", "", ""]],
            "semifinal": [["TBD"] * 4, ["TBD"] * 4],
            "final": [["TBD"] * 4],
        }

    def to_dict(self):
        return {
            "settings": self.settings.to_dict(),
            "stage": self.stage,
            "round_number": self.round_number,
            "total_hands": self.total_hands,
            "hands_at_current_level": self.hands_at_current_level,
            "hands_won": self.hands_won,
            "total_winnings": self.total_winnings,
            "opponents_faced": self.opponents_faced,
            "player": self.player.to_dict(),
            "opponents": [p.to_dict() for p in self.opponents],
            "bracket": self.bracket,
            "current_match": self.current_match,
            "dealer": self.dealer,
        }

    @classmethod
    def from_dict(cls, data):
        t = cls(Settings.from_dict(data["settings"]))

        for key in (
            "stage",
            "round_number",
            "total_hands",
            "hands_at_current_level",
            "hands_won",
            "total_winnings",
            "opponents_faced",
            "bracket",
            "current_match",
            "dealer",
        ):
            if key in data:
                setattr(t, key, data[key])

        t.player = Player.from_dict(data["player"])
        t.opponents = [
            Player.from_dict(p)
            for p in data.get("opponents", [])
        ]

        return t

def save_tournament(tournament):
    from datetime import datetime
    ensure_save_dir()
    tmp = SAVE_FILE.with_suffix(".tmp")

    data = tournament.to_dict()
    data["saved_at"] = datetime.now().strftime("%Y-%m-%d o godz: %H:%M:%S")

    with tmp.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )

    tmp.replace(SAVE_FILE)

def load_tournament_with_meta():
    try:
        with SAVE_FILE.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)
            return Tournament.from_dict(raw_data), raw_data.get("saved_at", "Nieznana data")
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None, None

def tournament_name(tournament):
    used = {tournament.player.name, *tournament.opponents_faced}
    pool = NAMES if tournament.stage == 0 else EASTER_EGGS + NAMES
    available = [name for name in pool if name not in used]
    return random.choice(available or pool)


def generate_bracket_bots(tournament):
    """Generuje losowe imiona dla botów w pozostałych drzewkach drabinki."""
    stages = ["quarterfinal", "semifinal", "final"]
    
    # Ćwierćfinały (Mecze 1, 2, 3 - bo mecz 0 to gracz)
    for m in range(1, 4):
        tournament.bracket["quarterfinal"][m] = [tournament_name(tournament) for _ in range(4)]
        for name in tournament.bracket["quarterfinal"][m]:
            tournament.opponents_faced.append(name)
            
    # Półfinały i Finał ustawiamy wstępnie na TBD
    tournament.bracket["semifinal"] = [["TBD"] * 4, ["TBD"] * 4]
    tournament.bracket["final"] = [["TBD"] * 4]

def create_opponents(tournament):
    """Tworzy boty przeciwników dla aktualnego stołu gracza."""
    # Czyszczenie starej listy przeciwników na danym szczeblu
    tournament.opponents = []
    
    # Tworzymy 3 przeciwników na stół gracza
    for _ in range(3):
        name = tournament_name(tournament)
        # Zapisujemy imię, by bot nie powtórzył się w tym turnieju
        tournament.opponents_faced.append(name)
        
        # Tworzymy obiekt bota (imię, stack startowy, human=False)
        bot = Player(name, tournament.settings.starting_stack, False)
        tournament.opponents.append(bot)

def tournament_new(settings):
    t = Tournament(settings)
    #create_opponents(t)

    first_table_bots = [tournament_name(t) for _ in range(3)]
    for name in first_table_bots:
        t.opponents_faced.append(name)

    t.opponents = [Player(name, settings.starting_stack, False) for name in first_table_bots]

    t.current_match = {
        "stage": 0,
        "opponents": first_table_bots,
    }

    # Stół gracza to pierwszy mecz (podlista) w ćwierćfinałach
    player_table = ["YOU"] + first_table_bots
    
    # Inicjalizujemy czyste struktury meczów (każdy mecz to lista 4 miejsc)
    t.bracket = {
        "quarterfinal": [player_table, [""]*4, [""]*4, [""]*4],
        "semifinal": [["TBD"]*4, ["TBD"]*4],
        "final": [["TBD"]*4],
    }
    
    # Generujemy boty dla pozostałych 3 stołów ćwierćfinałowych
    generate_bracket_bots(t)

    return t

def tournament_match(stdscr, tournament):
    players = [tournament.player] + tournament.opponents[:3]

    while True:
        if tournament.player.stack <= 0:
            return "lost"

        if len([p for p in players if p.stack > 0]) <= 1:
            return "won"

        result, tournament.dealer = deal_hand(
            stdscr,
            players,
            tournament.dealer,
            tournament.settings,
            tournament,
        )

        if result == "quit":
            return "quit"

        tournament.total_hands += 1
        tournament.hands_at_current_level += 1

        # Pobieramy interwał ustawiony przez gracza w menu głównym
        interval = tournament.settings.blind_increase_every

        # Warunek skoku blindów oparty o dedykowany licznik poziomu
        if tournament.hands_at_current_level >= interval:
            tournament.settings.small_blind *= 2
            tournament.settings.big_blind *= 2

            # Zerujemy licznik poziomu, żeby zacząć odliczać od nowa
            tournament.hands_at_current_level = 0

        if tournament.player.stack > tournament.settings.starting_stack:
            tournament.hands_won += 1

        for p in players:
            if p.stack <= 0:
                p.active = False

        if next_hand_input(stdscr) == "quit":
            return "menu"

def simulate_other_tables(tournament):
    """Symuluje awans losowych botów do wyższych szczebli drabinki."""
    if tournament.stage == 1: # Przechodzimy do półfinału
        # Z ćwierćfinału 0 awansuje YOU. Z tabel 1, 2, 3 losujemy po jednym bocie
        w1 = random.choice(tournament.bracket["quarterfinal"][1])
        w2 = random.choice(tournament.bracket["quarterfinal"][2])
        w3 = random.choice(tournament.bracket["quarterfinal"][3])

        tournament.bracket["semifinal"][0] = ["YOU", w1, w2, w3]
        tournament.bracket["semifinal"][1] = [tournament_name(tournament) for _ in range(4)]

    elif tournament.stage == 2: # Przechodzimy do finału
        # Z półfinału 0 awansuje YOU. Z półfinału 1 losujemy bota
        w_semi1 = random.choice(tournament.bracket["semifinal"][1])
        
        # Tworzymy dwa dodatkowe boty do uzupełnienia stołu finałowego
        b1 = tournament_name(tournament)
        b2 = tournament_name(tournament)

        # Zapisujemy czystą, płaską listę 4 imion do pierwszego (i jedynego) stołu finałowego
        tournament.bracket["final"][0] = ["YOU", w_semi1, b1, b2]

        #### Dokładamy jeszcze 2 losowych z puli, by finał miał 4 osoby
        ####tournament.bracket["final"][0] = ["YOU", w_semi1, tournament_name(tournament), tournament_name(tournament)]

def prepare_next_stage(tournament):
    tournament.hands_at_current_level = 0
    tournament.stage += 1
    tournament.round_number += 1

    tournament.player.stack = tournament.settings.starting_stack
    tournament.player.active = True
    tournament.player.reset_hand()

    # 1. Najpierw symulujemy inne stoły, żeby uzupełnić drabinkę kolejnego etapu
    simulate_other_tables(tournament)

    # 2. Szukamy stołu, na którym po symulacji wylądował gracz "YOU"
    current_stage_key = "semifinal" if tournament.stage == 1 else "final"
    target_bracket = tournament.bracket[current_stage_key]

    # Sprawdzamy, czy struktura etapu to lista stołów (półfinał), czy pojedynczy stół (finał)
    if tournament.stage == 1:
        # Półfinały: szukamy stołu, na którym jest "YOU"
        player_table = next((table for table in target_bracket if "YOU" in table), target_bracket[0])
    else:
        # Finał: jest tylko jeden stół
        player_table = target_bracket[0]

    # 3. Wyciągamy imiona przeciwników (odrzucamy samego siebie "YOU")
    bot_names = [name for name in player_table if name != "YOU"]

    # Awaryjne dopełnienie, gdyby drabinka nie wygenerowała imion
    while len(bot_names) < 3:
        bot_names.append(tournament_name(tournament))

    # 4. Tworzymy fizyczne obiekty botów dokładnie o takich imionach, jakie są na schemacie
    tournament.opponents = [Player(name, tournament.settings.starting_stack, False) for name in bot_names]

    tournament.current_match = {
        "stage": tournament.stage,
        "opponents": bot_names,
    }

# ============================================================
# TOURNAMENT SCREENS
# ============================================================

def bracket_screen(stdscr, tournament):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    # 0. NAGŁÓWKI KOLUMN – IDEALNIE NAD BOKSAMI
    title = f"--- TOURNAMENT DRABINKA (ETAP: {tournament.stage + 1}/3) ---"
    safe_add(stdscr, 1, (w - len(title)) // 2, title, curses.color_pair(3) | curses.A_BOLD)

    safe_add(stdscr, 3, 2, "ĆWIERĆFINAŁY (Stół 4-os.)", curses.A_BOLD)
    safe_add(stdscr, 3, 35, "PÓŁFINAŁY", curses.A_BOLD)
    safe_add(stdscr, 3, 68, "FINAŁ", curses.A_BOLD)

    # 1. RYSOWANIE ĆWIERĆFINAŁÓW (X = 2)
    for m_idx, match in enumerate(tournament.bracket["quarterfinal"]):
        base_y = 5 + (m_idx * 6)
        is_player_table = (m_idx == 0)
        
        attr = curses.color_pair(3) if (is_player_table and tournament.stage == 0) else 0
        safe_add(stdscr, base_y, 2, "┌──────────────────────┐", attr)
        for i in range(4):
            p_item = match[i] if i < len(match) and match[i] else "---"
            p_name = p_item[0] if isinstance(p_item, list) and p_item else str(p_item)
            
            if p_name == "YOU":
                safe_add(stdscr, base_y + 1 + i, 2, "│ ", attr)
                safe_add(stdscr, base_y + 1 + i, 4, "YOU (TY)", curses.color_pair(3) | curses.A_BOLD)
                safe_add(stdscr, base_y + 1 + i, 25, "│", attr)
            else:
                safe_add(stdscr, base_y + 1 + i, 2, f"│ {p_name:<20} │", attr)
        safe_add(stdscr, base_y + 5, 2, "└──────────────────────┘", attr)

    # LINIE ŁĄCZĄCE: ĆWIERĆFINAŁY -> PÓŁFINAŁY
    safe_add(stdscr, 7, 26, "──────┐")    # wylot z M0
    for y in range(8, 10): safe_add(stdscr, y, 32, "│")
    safe_add(stdscr, 10, 32, "├─────►")   # punkt zejścia i strzałka do Semi 1
    safe_add(stdscr, 11, 32, "│")
    safe_add(stdscr, 12, 26, "──────┘")   # wylot z M1

    safe_add(stdscr, 19, 26, "──────┐")   # wylot z M2
    for y in range(20, 22): safe_add(stdscr, y, 32, "│")
    safe_add(stdscr, 22, 32, "├─────►")   # punkt zejścia i strzałka do Semi 2
    safe_add(stdscr, 23, 32, "│")
    safe_add(stdscr, 24, 26, "──────┘")   # wylot z M3

    # 2. RYSOWANIE PÓŁFINAŁÓW (X = 35)
    for m_idx, match in enumerate(tournament.bracket["semifinal"]):
        base_y = 8 + (m_idx * 12)
        is_player_table = any((p[0] if isinstance(p, list) else str(p)) == "YOU" for p in match if p)
        attr = curses.color_pair(3) if (is_player_table and tournament.stage == 1) else 0
        
        safe_add(stdscr, base_y, 35, "┌──────────────────────┐", attr)
        for i in range(4):
            p_item = match[i] if i < len(match) and match[i] else "TBD"
            p_name = p_item[0] if isinstance(p_item, list) and p_item else str(p_item)
            
            if p_name == "YOU":
                safe_add(stdscr, base_y + 1 + i, 35, "│ ", attr)
                safe_add(stdscr, base_y + 1 + i, 37, "YOU (TY)", curses.color_pair(3) | curses.A_BOLD)
                safe_add(stdscr, base_y + 1 + i, 58, "│", attr)
            else:
                safe_add(stdscr, base_y + 1 + i, 35, f"│ {p_name:<20} │", attr)
        safe_add(stdscr, base_y + 5, 35, "└──────────────────────┘", attr)

    # LINIE ŁĄCZĄCE: PÓŁFINAŁY -> FINAŁ
    safe_add(stdscr, 10, 59, "──────┐")   # wylot z Semi 1
    for y in range(11, 16): safe_add(stdscr, y, 65, "│")
    safe_add(stdscr, 16, 65, "├─────►")   # punkt zejścia i strzałka do Finału
    for y in range(17, 23): safe_add(stdscr, y, 65, "│")
    safe_add(stdscr, 22, 59, "──────┘")   # wylot z Semi 2

    # 3. RYSOWANIE FINAŁU (X = 68) - Wyciągamy pierwszy stół z listy finałowej [0]
    final_table = tournament.bracket["final"][0] if tournament.bracket["final"] else ["TBD"] * 4
    is_player_table = any((p[0] if isinstance(p, list) else str(p)) == "YOU" for p in final_table if p)
    attr = curses.color_pair(3) if (is_player_table and tournament.stage == 2) else 0
    
    safe_add(stdscr, 14, 68, "┌──────────────────────┐", attr)
    for i in range(4):
        p_item = final_table[i] if i < len(final_table) and final_table[i] else "TBD"
        p_name = p_item[0] if isinstance(p_item, list) and p_item else str(p_item)
        
        if p_name == "YOU":
            safe_add(stdscr, 15 + i, 68, "│ ", attr)
            safe_add(stdscr, 15 + i, 70, "YOU (TY)", curses.color_pair(3) | curses.A_BOLD)
            safe_add(stdscr, 15 + i, 91, "│", attr)
        else:
            safe_add(stdscr, 15 + i, 68, f"│ {p_name:<20} │", attr)
    safe_add(stdscr, 19, 68, "└──────────────────────┘", attr)

    # PANEL SYSTEMOWY NA DOLE
    safe_add(stdscr, h - 3, 2, "ENTER = Rozpocznij grę na swoim stole", curses.color_pair(3) | curses.A_BOLD)
    safe_add(stdscr, h - 2, 2, "S = Zapisz stan turnieju   |   P = Incognito   |   Q = Wyjście do menu")

    stdscr.refresh()

def tournament_loss_screen(stdscr, tournament):
    stdscr.erase()

    safe_add(
        stdscr, 8, 30,
        "TOURNAMENT OVER",
        curses.color_pair(4) | curses.A_BOLD,
    )
    safe_add(
        stdscr, 11, 30,
        f"Hands played: {tournament.total_hands}",
    )
    safe_add(stdscr, 13, 30, "R = restart tournament")
    safe_add(stdscr, 14, 30, "Q = menu")
    stdscr.refresh()

    while True:
        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            return "menu"

        if key in (ord("r"), ord("R")):
            delete_save()
            return "restart"

def tournament_win_screen(stdscr, tournament):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    cup = [
        "⠀⠀⠀⠀⣠⠤⠤⣄⣠⣤⣤⡤⠤⠤⠤⠤⠤⠤⠤⣤⣠⠒⠒⠲⣄⠀⠀⠀⠀⠀",
        "⠀⠀⠀⡜⢁⡶⠶⢤⡇⠀⠈⠉⠉⠉⠉⠉⠉⠉⠉⠉⠳⠒⠲⡄⠘⡆⠀⠀⠀⠀",
        "⠀⠀⡇⢸⠀⠀⠀⡃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀ ⠀⡇⠀⢹⠀⢸⠀⠀",
        "⠀⠀⢧⠘⣆⠀⠀⡇⠀⠀⠀WINNER⠀⠀⢰⠇⢠⠇⢰⠃⠀⠀",
        "⠀⠀⠀⠈⢦⡘⠦⣀⠹⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡞⣀⡜⠀⡸⠁⠀⠀⠀",
        "⠀⠀⠀⠀⠀⠙⠦⣌⡙⠻⣄⠀⠀⠀⠀⠀⠀⠀⣠⠞⠋⣁⡴⠚⠁⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠚⠳⣄⠀⠀⠀⠀⣠⠖⠓⠋⠉⠀⠀⠀⠀⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⢳⡀⠀⡼⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡇⠸⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡜⠀⠀⢳⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣞⣀⣀⣀⣀⣳⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣾⠉⠉⠉⠉⠉⠉⢹⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡷⠤⠤⠤⠤⠤⠤⠼⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠓⠒⠒⠒⠒⠒⠒⠒⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
    ]

    for i, line in enumerate(cup):
        safe_add(
            stdscr,
            3 + i,
            max(2, (w - len(line)) // 2),
            line,
            curses.color_pair(3) | curses.A_BOLD,
        )

    safe_add(
        stdscr, 15, max(2, (w - 28) // 2),
        "TOURNAMENT CHAMPION!",
        curses.color_pair(3) | curses.A_BOLD,
    )

    stats = [
        f"Hands played:  {tournament.total_hands}",
        f"Hands won:     {tournament.hands_won}",
        f"Opponents:     {len(tournament.opponents_faced)}",
        f"Final stack:   {money(tournament.player.stack)}",
    ]

    for i, line in enumerate(stats):
        safe_add(
            stdscr,
            18 + i,
            max(2, (w - len(line)) // 2),
            line,
        )

    safe_add(
        stdscr, 25, max(2, (w - 28) // 2),
        "ENTER = back to menu",
        curses.A_BOLD,
    )

    stdscr.refresh()

    while stdscr.getch() not in (10, 13, ord(" ")):
        pass

    delete_save()
    return "menu"

def tournament_menu(stdscr, settings):
    while True:
        stdscr.erase()

        safe_add(
            stdscr, 4, 30,
            "TOURNAMENT",
            curses.color_pair(3) | curses.A_BOLD,
        )

        for y, text in (
            (9, "1. NEW GAME"),
            (11, "2. LOAD GAME"),
            (13, "3. BACK"),
        ):
            safe_add(stdscr, y, 30, text)

        tournament, saved_time = load_tournament_with_meta()
        if tournament:
            safe_add(
                stdscr, 16, 30,
                f"SAVE FOUND ({saved_time})",
                curses.color_pair(3) | curses.A_BOLD,
            )

        h, w = stdscr.getmaxyx()
        safe_add(stdscr, h - 2, 30, "P = Incognito", curses.A_BOLD)

        stdscr.refresh()
        key = stdscr.getch()

        if key in (ord("p"), ord("P")):
            incognito_mode(stdscr)
        elif key == ord("1"):
            return run_tournament(
                stdscr,
                tournament_new(settings),
            )
        elif key == ord("2"):

            if tournament:
                return run_tournament(stdscr, tournament)

            safe_add(
                stdscr, 18, 30,
                "Could not load save.",
                curses.color_pair(4),
            )
            stdscr.refresh()
            time.sleep(1)

        elif key == ord("3"):
            return "menu"

def run_tournament(stdscr, tournament):
    while True:
        bracket_screen(stdscr, tournament)
        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            return "menu"

        if key in (ord("p"), ord("P")):
            incognito_mode(stdscr)
            continue

        if key in (ord("s"), ord("S")):
            save_tournament(tournament)
            h, w = stdscr.getmaxyx()
            safe_add(stdscr, h - 4, 2, "Gra została pomyślnie zapisana!", curses.color_pair(3) | curses.A_BOLD)
            stdscr.refresh()
            time.sleep(1)
            continue

        if key not in (10, 13):
            continue

        result = tournament_match(stdscr, tournament)

        if result in ("quit", "menu"):
            return "menu"

        if result == "lost":
####            return tournament_loss_screen(stdscr, tournament)
            loss_choice = tournament_loss_screen(stdscr, tournament)

            if loss_choice == "restart":
                # POPRAWKA: Jeśli gracz wybrał Restart, tworzymy nowy turniej 
                # na tych samych ustawieniach i nadpisujemy obiekt `tournament`
                tournament = tournament_new(tournament.settings)
                continue # Wracamy na początek pętli (do rysowania nowej drabinki)
                
            return "menu" # Jeśli wybrał 'Q' lub cokolwiek innego, wracamy do menu

        if tournament.stage >= 2 and result == "won":
            return tournament_win_screen(stdscr, tournament)

        for p in tournament.opponents:
            if p.name not in tournament.opponents_faced:
                tournament.opponents_faced.append(p.name)

        prepare_next_stage(tournament)


# ============================================================
# OPTIONS
# ============================================================

def options_menu(stdscr, settings):
    items = [
        ("Starting cash", "starting_stack", 100, 1_000_000),
        ("Small blind", "small_blind", 1, 100_000),
        ("Big blind", "big_blind", None, 100_000),
        ("Bot count", "bot_count", MIN_BOTS, MAX_BOTS),
        ("Blind increase every", "blind_increase_every", 1, 1000),
        ("Blind step", "blind_step", 1, 100_000),
        ("Back", None, None, None),
    ]

    selected = 0

    while True:
        stdscr.erase()

        safe_add(
            stdscr, 3, 30,
            "OPTIONS",
            curses.color_pair(3) | curses.A_BOLD,
        )

        values = [
            money(settings.starting_stack),
            money(settings.small_blind),
            money(settings.big_blind),
            str(settings.bot_count),
            str(settings.blind_increase_every),
            money(settings.blind_step),
            "",
        ]

        for i, (label, _, _, _) in enumerate(items):
            attr = (
                curses.color_pair(3) | curses.A_BOLD
                if i == selected else 0
            )

            safe_add(
                stdscr,
                7 + i * 2,
                25,
                f"{'> ' if i == selected else '  '}"
                f"{label:<22} {values[i]}",
                attr,
            )

        safe_add(stdscr, 22, 25, "UP/DOWN = select | ENTER = change")
        safe_add(stdscr, 24, 25, "ESC = back | P = Incognito", curses.A_BOLD)
        stdscr.refresh()

        key = stdscr.getch()

        if key in (ord("p"), ord("P")):
            incognito_mode(stdscr)
            continue
        elif key in (27, ord("q"), ord("Q")):
            return
        elif key == curses.KEY_UP:
            selected = (selected - 1) % len(items)
            continue
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(items)
            continue
        elif key not in (10, 13):
            continue
        elif selected == 6:
            return

        label, attr_name, minimum, maximum = items[selected]

        if selected == 2:
            minimum = settings.small_blind

        value = ask_number(
            stdscr,
            f"{label}:",
            minimum,
            maximum,
        )

        if value is None:
            continue

        setattr(settings, attr_name, value)

        if selected == 1:
            settings.big_blind = value * 2

# ============================================================
# MAIN MENU
# ============================================================

def main_menu(stdscr, settings):
    items = ["QUICK MATCH", "TOURNAMENT", "OPTIONS", "QUIT"]
    selected = 0

    title = [
        "███████╗ ██████╗ ██╗     ██████╗  ██╗  ███████╗███╗   ███╗",
        "██╔════╝██╔═══██╗██║     ██╔══██╗ ██║  ██╔════╝████╗ ████║",
        "█████╗  ██║   ██║██║     ██║  ██║ ╚═╝  █████╗  ██╔████╔██║",
        "██╔══╝  ██║   ██║██║     ██║  ██║      ██╔══╝  ██║╚██╔╝██║",
        "██║     ╚██████╔╝███████╗██████╔╝      ███████╗██║ ╚═╝ ██║",
        "╚═╝      ╚═════╝ ╚══════╝╚═════╝       ╚══════╝╚═╝     ╚═╝",
    ]

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        for i, line in enumerate(title):
            safe_add(
                stdscr,
                2 + i,
                max(2, (w - len(line)) // 2),
                line,
                curses.color_pair(3) | curses.A_BOLD,
            )

        for i, item in enumerate(items):
            attr = (
                curses.color_pair(3) | curses.A_BOLD
                if i == selected else 0
            )

            safe_add(
                stdscr,
                11 + i * 2,
                max(2, (w - 20) // 2),
                f"{'> ' if i == selected else '  '}{item}",
                attr,
            )

        safe_add(
            stdscr,
            h - 4,
            3,
            f"Stack: {money(settings.starting_stack)} | "
            f"Blinds: {settings.small_blind}/{settings.big_blind} | "
            f"Bots: {settings.bot_count} | "
            f"Blinds up: co {settings.blind_increase_every} rozd. (+{money(settings.blind_step)})",
        )

        safe_add(
            stdscr,
            h - 2,
            3,
            f"Saves: {SAVE_DIR} | P = Logs | Q = Quit",
        )

        stdscr.refresh()
        key = stdscr.getch()

        if key in (ord("p"), ord("P")):
            incognito_mode(stdscr)

        elif key in (ord("q"), ord("Q")):
            return

        elif key == curses.KEY_UP:
            selected = (selected - 1) % len(items)

        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(items)

        elif key in (10, 13):
            if selected == 0:
                quick_match(stdscr, settings)
            elif selected == 1:
                tournament_menu(stdscr, settings)
            elif selected == 2:
                options_menu(stdscr, settings)
            else:
                return

# ============================================================
# INIT
# ============================================================

def initialize_colors():
    if not curses.has_colors():
        return

    curses.start_color()
    curses.use_default_colors()

    for pair, color in (
        (1, curses.COLOR_WHITE),
        (2, curses.COLOR_RED),
        (3, curses.COLOR_YELLOW),
        (4, curses.COLOR_RED),
    ):
        curses.init_pair(pair, color, -1)


def app(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.nodelay(False)

    initialize_colors()
    ensure_save_dir()

    main_menu(
        stdscr,
        Settings(**DEFAULTS),
    )


def main():
    ensure_save_dir()

    try:
        curses.wrapper(app)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
