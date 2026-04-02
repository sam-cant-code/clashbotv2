import os
from dotenv import load_dotenv

load_dotenv()

# --- TOKENS & IDS ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
COC_TOKEN = os.getenv('COC_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', 0))

# --- FILE PATHS (UPDATED FOR DATA FOLDER) ---
PLAYERS_FILE = 'data/players.json'
CONFIG_FILE = 'data/lb_config.json'
TROPHY_CACHE_FILE = 'data/trophy_cache.json'
LEGEND_STATS_FILE = 'data/legend_stats.json'

# --- EMOJIS & LEAGUES ---
TROPHY_EMOJI = "<:Trophy:1485318298445938740>"

LEAGUE_EMOJIS = {
    "Skeleton League 1": "<:skeleton_league_1:1485297995376361482>",
    "Skeleton League 2": "<:skeleton_league_2:1485297999998357816>",
    "Skeleton League 3": "<:skeleton_league_3:1485298004138266764>",
    "Barbarian League 4": "<:barbarian_league_4:1485298008999596172>",
    "Barbarian League 5": "<:barbarian_league_5:1485298014171037746>",
    "Barbarian League 6": "<:barbarian_league_6:1485298018080133162>",
    "Archer League 7": "<:archer_league_7:1485298022152667198>",
    "Archer League 8": "<:archer_league_8:1485298026410016951>",
    "Archer League 9": "<:archer_league_9:1485298030919028736>",
    "Wizard League 10": "<:wizard_league_10:1485298036111311050>",
    "Wizard League 11": "<:wizard_league_11:1485298040838426817>",
    "Wizard League 12": "<:wizard_league_12:1485298046362456136>",
    "Valkyrie League 13": "<:valkyrie_league_13:1485298051433238538>",
    "Valkyrie League 14": "<:valkyrie_league_14:1485298056172929034>",
    "Valkyrie League 15": "<:valkyrie_league_15:1485298060975411225>",
    "Witch League 16": "<:witch_league_16:1485298066322882733>",
    "Witch League 17": "<:witch_league_17:1485298072127930438>",
    "Witch League 18": "<:witch_league_18:1485298076519497970>",
    "Golem League 19": "<:golem_league_19:1485298081179238501>",
    "Golem League 20": "<:golem_league_20:1485298084983607366>",
    "Golem League 21": "<:golem_league_21:1485298089202941972>",
    "P.E.K.K.A League 22": "<:pekka_league_22:1485298092545675369>",
    "P.E.K.K.A League 23": "<:pekka_league_23:1485298097532829916>",
    "P.E.K.K.A League 24": "<:pekka_league_24:1485298102767452170>",
    "Titan League 25": "<:titan_league_25:1485298109981397163>",
    "Titan League 26": "<:titan_league_26:1485298115006300291>",
    "Titan League 27": "<:titan_league_27:1485298118416269425>",
    "Dragon League 28": "<:dragon_league_28:1485298122505846958>",
    "Dragon League 29": "<:dragon_league_29:1485298126935031958>",
    "Dragon League 30": "<:dragon_league_30:1485298131863077104>",
    "Electro League 31": "<:electro_league_31:1485298134958735360>",
    "Electro League 32": "<:electro_league_32:1485298138066714794>",
    "Electro League 33": "<:electro_league_33:1485298142776918126>",
    "Legend League": "<:legend_league:1485298146186625205>"
}

LEAGUE_WEIGHTS = {name: i for i, name in enumerate(LEAGUE_EMOJIS.keys(), start=1)}

TIER_ID_TO_NAME = {
    105000001: "Skeleton League 1", 105000002: "Skeleton League 2", 105000003: "Skeleton League 3",
    105000004: "Barbarian League 4", 105000005: "Barbarian League 5", 105000006: "Barbarian League 6",
    105000007: "Archer League 7", 105000008: "Archer League 8", 105000009: "Archer League 9",
    105000010: "Wizard League 10", 105000011: "Wizard League 11", 105000012: "Wizard League 12",
    105000013: "Valkyrie League 13", 105000014: "Valkyrie League 14", 105000015: "Valkyrie League 15",
    105000016: "Witch League 16", 105000017: "Witch League 17", 105000018: "Witch League 18",
    105000019: "Golem League 19", 105000020: "Golem League 20", 105000021: "Golem League 21",
    105000022: "P.E.K.K.A League 22", 105000023: "P.E.K.K.A League 23", 105000024: "P.E.K.K.A League 24",
    105000025: "Titan League 25", 105000026: "Titan League 26", 105000027: "Titan League 27",
    105000028: "Dragon League 28", 105000029: "Dragon League 29", 105000030: "Dragon League 30",
    105000031: "Electro League 31", 105000032: "Electro League 32", 105000033: "Electro League 33",
    105000034: "Legend League"
}

# --- KEYWORDS & SENTIMENT CATEGORIES ---
FOLLOW_UP_KEYWORDS = ["what do you think", "you agree", "right", "don't you think", "ikr", "fr"]
SAD_KEYWORDS = ["sad", "depressed", "tired", "failed", "loss"]
HYPE_KEYWORDS = ["lets go", "won", "clutch", "insane", "bro"]
COC_KEYWORDS = ["clash", "war", "raid", "trophy", "legend", "donate", "coc"]
RANT_KEYWORDS = ["bro", "why", "always", "never", "literally", "hate", "annoying", "cant believe", "i swear", "every time"]
ADVICE_KEYWORDS = ["should i", "would you", "do you think i should", "is it worth", "what should i do", "help me decide"]
FLEX_KEYWORDS = ["look at me", "i got", "just got", "check this", "new", "bought", "just bought", "look what"]
SELF_DOUBT_KEYWORDS = ["i'm bad", "i suck", "i can't", "i'm terrible", "i'm the worst", "i give up", "i'm done", "i'm trash"]

TOPIC_KEYWORDS = {
    "clash": COC_KEYWORDS,
    "sleep": ["tired", "sleep", "nap", "bed", "exhausted", "sleepy"],
    "school": ["school", "class", "exam", "test", "homework", "teacher", "study"],
    "work": ["work", "job", "boss", "shift", "office", "meeting"]
}

# --- RESPONSES ---
FORTUNE_NORMAL = [
    "yes 🐦", "no 💀", "maybe 👀", "perchance 🐦", "ask again later 😤", 
    "probably 👀", "unlikely 💀", "i guess so 🐦", "hmmm… idk 😭", 
    "it is possible 👀", "very likely 🐦", "not looking good 💀", 
    "could go either way 👀", "i wouldn’t count on it 😤", 
    "signs point to yes 🐦", "signs point to no 💀", "the odds are decent 👀", 
    "the odds are terrible 💀", "absolutely not 😤", "without a doubt 🐦", 
    "don't bet on it 💀", "sure why not 👀", "100% yes 🐦", "0% chance 💀", "if you say so 👀"
]

FORTUNE_ROAST = [
    "bro why are you asking me 💀", "use your brain 😭", "you already know the answer 💀", 
    "this question is crazy 🐦", "i refuse to answer that 😤", "what kind of question is this 💀", 
    "you serious right now 😭", "ask someone else 🐦", "i’m not dealing with this 😤", 
    "this is beyond me 💀", "are you actually this dumb 😭", "please stop talking 😤", 
    "im losing brain cells 💀", "google it bro 🐦", "why are you like this 👀", 
    "im a bird not a tutor 😤", "no thoughts head empty 🐦", "i cant even read 💀", 
    "make it make sense 😭", "embarrassing question tbh 👀", "just delete this 💀"
]

FORTUNE_NICE = [
    "you got this 🐦", "i believe in you 👀", "things will work out 🐦✨", 
    "stay positive 😤", "it’ll be okay 🐦", "trust yourself 👀", "keep going 🐦🔥", 
    "don’t give up 😭", "you’re doing fine 🐦", "just try your best 👀", 
    "im proud of you 🐦", "take a deep breath 😤", "one step at a time 👀", 
    "you are doing great 🐦", "dont be so hard on yourself 😭", "everything happens for a reason ✨", 
    "you will figure it out 🐦", "im rooting for you 👀", "youre stronger than you think 😤", 
    "sending good vibes 🐦✨", "you matter bro 😭"
]

FORTUNE_HYPE = [
    "let's go bro 🔥", "massive W 🐦", "insane 💀", "we take those 😤", "W 🐦", 
    "absolutely cooking 🍳", "bro is unstoppable 💀", "they cant stop you 😤", 
    "built different 🐦", "huge dub 👀", "love to see it 😭", "pop off then 🐦", 
    "thats what i like to hear 😤", "crazy clutch 💀", "bro has ascending 👀", 
    "himothy 🐦", "actually insane 🔥", "bro is the main character 💀", 
    "legendary behavior 😤", "they aint ready 🐦", "keep eating bro 🍳"
]

FORTUNE_OPEN_ENDED = [
    "why do you care 💀", "idk bro i'm literally a bird 🐦", "none of your business 😤", 
    "google is free you know 😭", "i don't have the brain capacity for this 👀", 
    "what kind of question is that 💀", "figure it out yourself 😤🐦", 
    "do i look like an encyclopedia to you? 💀", "stop asking me complicated things 😭", 
    "i am not siri 😤", "ask me something easier 🐦", "why are you asking me this 💀", 
    "thats a you problem 👀", "idk and idc 😤", "go read a book 🐦", 
    "why is the sky blue? idk 💀", "ask chatgpt bro 😭", "i am just a bird 👀", 
    "does it really matter 😤", "stop stressing over this 🐦"
]

FORTUNE_DEFENSIVE = [
    "watch your mouth 😤", "who do you think you're talking to? 💀", "say that again, i dare you 🐦🔪", 
    "do you kiss your mother with that mouth? 😭", "keep talking and see what happens 👀", 
    "i will literally ban you 😤", "don't test me bro 💀", "you wanna go? 🐦", "try me 😤", 
    "i am one warning away from losing it 💀", "watch your tone 👀", "bold words for a human 🐦", 
    "you thought you ate that 😭", "do not disrespect me 😤", "im ignoring that 💀", 
    "you lucky im just a bot 🐦", "step back bro 👀", "dont push your luck 😤", 
    "imma pretend i didnt hear that 💀", "check yourself 🐦"
]

COC_RESPONSES = [
    "bro is really clashing 💀", "touch grass 🐦", "skill issue 😤", "did you even 3 star tho 👀", 
    "e-drag spammer detected 😭", "fix your rushed base 💀", "bro missed the warden ability 🐦", 
    "go do your war attack 😤", "clan games or kick 👀", "nobody cares about your legends league 💀", 
    "stop requesting if you dont donate 😭", "bro is still th9 🐦", "imagine time failing 😤", 
    "queen walk failed again? 💀", "go upgrade your walls 👀", "super archer blimp is zero skill 🐦", 
    "builder base is trash anyway 😤", "buy the gold pass bro 💀", "bro forgot his spells 😭", 
    "sneaky goblin farmer 👀", "ur clan is dead 🐦"
]

RANT_RESPONSES = [
    "bro same 💀", "say less 🐦", "that's crazy 😤", "not you ranting again 😭", 
    "who did this to you 👀", "breathe bro 🐦", "tell me more 👀", "they did you dirty 💀", 
    "it do be like that 😤", "let it out bro 🐦", "im listening 😭", "fr though 💀", 
    "people are annoying 😤", "thats tough 👀", "valid complaint 🐦", "i would be mad too 💀", 
    "dont let them get to you 😤", "bro is fed up 😭", "preach 🐦", "i feel you bro 👀", 
    "they testing your patience 💀"
]

ADVICE_RESPONSES = [
    "do what you want 😤", "bro idk your life 💀", "probably not 🐦", "could go either way 👀", 
    "trust the process 🐦", "flip a coin 💀", "ask someone smarter 😭", "go with your gut 🐦", 
    "don't overthink it 😤", "do the opposite of what you want 💀", "is it really worth the stress 👀", 
    "just sleep on it 🐦", "bro im a bird not a therapist 😭", "make a pro con list idk 😤", 
    "take a risk 💀", "play it safe 🐦", "follow your heart or whatever 👀", 
    "what is the worst that could happen 💀", "yolo bro 🐦", "im unqualified to answer this 😤", 
    "ask your mom 😭"
]

FLEX_RESPONSES = [
    "cool i guess 💀", "nobody asked 🐦", "okay and? 😤", "noted 👀", "nice i don't care 💀", 
    "good for you i guess 🐦", "okay mr money 💀", "and you're telling me this because? 😤", 
    "do you want a medal 😭", "weird flex but okay 🐦", "im not impressed 👀", "must be nice 💀", 
    "share some then 😤", "bro is showing off 🐦", "we get it you're cool 😭", "humble yourself 💀", 
    "congrats... moving on 👀", "wow so amazing 😤", "bro wants validation 🐦", "i have seen better 💀"
]

SELF_DOUBT_RESPONSES = [
    "you're fine bro 🐦", "stop it 😤", "skill issue 💀", "practice more 🐦", "it gets better 👀", 
    "don't be dramatic 💀", "you got this actually 🐦", "take a break 😤", "stop crying 😭", 
    "believe in yourself or else 🐦🔪", "bro you are literally okay 💀", "get back up 😤", 
    "failure is a stepping stone 👀", "you are not trash 🐦", "imma need you to lock in 💀", 
    "dont talk about my friend like that 😤", "chin up bro 🐦", "everyone fails sometimes 😭", 
    "stop the self pity 💀", "you are better than this 👀"
]