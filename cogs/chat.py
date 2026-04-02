import discord
from discord.ext import commands
import time
import re
import random
from better_profanity import profanity
import config
from utils import fetch_joke

class ChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_image_reply(self, message, text, image_filename, is_reply=True):
        filepath = f"images/{image_filename}"
        embed = discord.Embed(description=text if text else None, color=0x2b2d31)
        try:
            file = discord.File(filepath, filename=image_filename)
            embed.set_image(url=f'attachment://{image_filename}')
            if is_reply:
                await message.reply(embed=embed, file=file)
            else:
                await message.channel.send(embed=embed, file=file)
        except FileNotFoundError:
            if text:
                embed2 = discord.Embed(description=text, color=0x2b2d31)
                if is_reply:
                    await message.reply(embed=embed2)
                else:
                    await message.channel.send(embed=embed2)

    def decay_grudge(self, user_state, now):
        if user_state["last_interaction"]:
            hours_passed = (now - user_state["last_interaction"]) / 3600
            decay = int(hours_passed * 2) 
            user_state["grudge_score"] = max(0, user_state["grudge_score"] - decay)
            
        if user_state["grudge_score"] > 20: user_state["mood"] = "annoyed"
        elif user_state["grudge_score"] > 10: user_state["mood"] = "playful"
        else: user_state["mood"] = "friendly"

    def get_smart_fortune(self, user_state, target_text):
        if user_state["grudge_score"] >= 20: pool = ["no.", "sleep.", "stop.", "...", "leave me alone."]
        elif user_state["grudge_score"] >= 10: pool = config.FORTUNE_ROAST
        elif any(word in target_text for word in config.SAD_KEYWORDS): pool = config.FORTUNE_NICE
        elif any(word in target_text for word in config.HYPE_KEYWORDS): pool = config.FORTUNE_HYPE
        else: pool = config.FORTUNE_NORMAL

        valid_pool = [r for r in pool if r != user_state["last_bot_response"]]
        if not valid_pool: valid_pool = pool
        response = random.choice(valid_pool)
        user_state["last_bot_response"] = response
        return response

    async def handle_tweaking(self, message, user_state, now):
        msg = message.content
        user_state["messages"] = [t for t in user_state["messages"] if now - t < 5]      
        user_state["caps_times"] = [t for t in user_state["caps_times"] if now - t < 30] 
        user_state["swear_times"] = [t for t in user_state["swear_times"] if now - t < 30]
        user_state["chaos_times"] = [t for t in user_state["chaos_times"] if now - t < 30]

        user_state["messages"].append(now)
        if msg.isupper() and len(msg) > 6: user_state["caps_times"].append(now)
        if profanity.contains_profanity(msg): user_state["swear_times"].append(now)
        if "???" in msg or "!!!" in msg: user_state["chaos_times"].append(now)

        is_spam = len(user_state["messages"]) >= 6
        is_caps = len(user_state["caps_times"]) >= 3
        is_swear = len(user_state["swear_times"]) >= 3
        is_chaos = len(user_state["chaos_times"]) >= 2

        tweaking = is_spam or is_caps or is_swear or is_chaos

        if tweaking and (now - user_state["last_trigger"] > 10):
            user_state["last_trigger"] = now
            user_state["grudge_score"] += 15 

            if user_state["grudge_score"] > 30: 
                response_text = "stop."
                await self.send_image_reply(message, response_text, 'pic_2.jpg', is_reply=False)
            elif user_state["grudge_score"] > 20: 
                response_text = "stop."
                await self.send_image_reply(message, response_text, 'pic_5.jpg', is_reply=False)
            elif is_spam and is_caps: 
                response_text = "BRO IS LOSING IT 💀🐦"
                embed = discord.Embed(description=response_text, color=0x2b2d31)
                try:
                    file = discord.File("images/tweaking.jpeg", filename="tweaking.jpeg")
                    embed.set_image(url="attachment://tweaking.jpeg")
                    await message.channel.send(embed=embed, file=file)
                except FileNotFoundError: await message.channel.send(embed=embed)
            else: 
                if is_swear: response_text = "calm down 😤🐦"
                elif is_chaos: response_text = "what are you even saying 🤯🐦"
                else: response_text = "calm down blud💀🐦"
                
                if 15 <= user_state["grudge_score"] <= 30:
                    await self.send_image_reply(message, response_text, 'pic_1.jpg', is_reply=False)
                else:
                    embed = discord.Embed(description=response_text, color=0x2b2d31)
                    await message.channel.send(embed=embed)

            user_state["messages"].clear()
            user_state["caps_times"].clear()
            user_state["swear_times"].clear()
            user_state["chaos_times"].clear()
            return True
        return False

    async def handle_greeting(self, message, user_state, clean_lower, now):
        is_goodnight = re.search(r'\b(g+o+d+|g+u+d+)\s*(n+i+g*h*t+|n+i+t+e+)\b|\bg+n+i+g*h*t+\b', clean_lower)
        
        if user_state["goodnight_time"] > 0 and not is_goodnight:
            if now - user_state["goodnight_time"] < (8 * 3600):
                callouts = ["back already? 💀", "thought you were sleeping 🐦", "liar 😤"]
                resp = random.choice(callouts)
                user_state["last_bot_response"] = resp
                user_state["goodnight_time"] = 0
                
                if user_state["grudge_score"] > 20:
                    await self.send_image_reply(message, resp, 'pic_5.jpg', is_reply=False)
                else:
                    await message.channel.send(resp)
                return True
            else: user_state["goodnight_time"] = 0 

        if is_goodnight:
            good_night_responses = [
                "good night pookie 🐦💤", "sleep before I get angry 😤🐦", "don’t let the bugs bite 😭", 
                "go recharge bro 🔋", "finally going to sleep? 💀", "rest well… you’ll need it 😤",
                "sweet dreams 🐦✨", "night night 👀", "don’t text back at 3am 💀", "good night… behave 😤🐦"
            ]
            resp = "finally." if user_state["grudge_score"] > 20 else random.choice(good_night_responses)
            user_state["last_bot_response"] = resp
            user_state["goodnight_time"] = now
            
            if user_state["grudge_score"] > 20:
                await self.send_image_reply(message, resp, 'pic_5.jpg', is_reply=False)
            else:
                await message.channel.send(resp)
            return True

        if re.search(r'\b(g+o+d+|g+u+d+)\s*(m+o+r+n+i+n+g+|m+r+n+i+n+g+)\b|\bg+m+\b', clean_lower):
            good_morning_responses = ["morning… too early for this 😤", "why are you awake 💀", "good morning pookie 🐦☕", "go back to sleep 😭", "who wakes up this early 👀", "morning bro 🐦"]
            resp = "..." if user_state["grudge_score"] > 20 else random.choice(good_morning_responses)
            user_state["last_bot_response"] = resp
            
            if user_state["grudge_score"] > 20:
                await self.send_image_reply(message, resp, 'pic_5.jpg', is_reply=False)
            else:
                await message.channel.send(resp)
            return True

        if re.match(r"^(h+i+|h+e+y+|h+e+l+l+o+|y+o+)\b", clean_lower):
            hi_responses = [f"hi {message.author.display_name} 👀", "hello there 🐦", f"oh… it’s {message.author.display_name} again 💀", "hi pookie 🐦💤", "hey hey 🐦", "hi… state your business 👀", "yo 🐦", "hello human 🐦", "hi 😭"]
            resp = "no." if user_state["grudge_score"] > 20 else random.choice(hi_responses)
            user_state["last_bot_response"] = resp
            
            if user_state["grudge_score"] > 20:
                await self.send_image_reply(message, resp, 'pic_5.jpg', is_reply=False)
            else:
                await message.channel.send(resp)
            return True
        return False

    async def handle_mention(self, message, user_state, clean_lower, clean_content):
        word_count = len(clean_content.split())
        context_lower = " ".join(user_state["history"]).lower()
        
        is_follow_up = any(kw in clean_lower for kw in config.FOLLOW_UP_KEYWORDS)
        target_text = context_lower if is_follow_up else clean_lower

        image_to_send = None

        if profanity.contains_profanity(clean_content):
            user_state["bad_word_count"] += 1
            bw_count = user_state["bad_word_count"]
            
            if bw_count == 1:
                reply_text = "😤"
                image_to_send = "pic_5.jpg"
            elif bw_count == 2:
                reply_text = "again? 💀"
                image_to_send = "pic_4.jpg"
            elif bw_count == 3:
                reply_text = "stop. 😤"
                image_to_send = "pic_1.jpg"
            else:
                reply_text = "im done. 💀"
                image_to_send = "pic_2.jpg"
                
        elif re.search(r'\bwhat( is|\'s) your name\b|\bwho are you\b', clean_lower):
            reply_text = "i am angry birb. don't wear it out 😤🐦"
        elif re.search(r'\bwho (made|created) you\b|\bwho is your (creator|daddy)\b', clean_lower):
            reply_text = "my glorious creator... who doesn't pay me enough 😤"
        elif re.search(r'\bare you (a )?bot\b', clean_lower):
            reply_text = "i am a highly advanced avian intelligence. watch your mouth 🐦"
        elif re.search(r'\bdo you love me\b', clean_lower):
            reply_text = "don't make this weird 💀"
            
        elif word_count >= 30:
            reply_text = "tldr 💀"
            image_to_send = "image0.jpg"
        elif word_count == 1:
            responses = ["huh 🐦", "okay 💀", "...👀", "and? 😤", "elaborate 🐦", "what 💀"]
            reply_text = random.choice(responses)
            
        elif clean_content.isupper() and clean_content.count('!') >= 3:
            responses = ["OKAY OKAY 🐦", "chill 💀", "i hear you 😤", "CALM DOWN 💀", "okay okay i'm listening 🐦"]
            reply_text = random.choice(responses)
        elif '...' in clean_content or clean_content.endswith('…'):
            responses = ["...what happened 🐦", "you okay 👀", "bro... 💀", "talk to me 🐦", "that ellipsis is worrying me 😭"]
            reply_text = random.choice(responses)

        elif "joke" in target_text or "make me laugh" in target_text:
            reply_text = await fetch_joke(self.bot.session)
            
        elif any(word in target_text for word in config.SELF_DOUBT_KEYWORDS):
            reply_text = random.choice(config.SELF_DOUBT_RESPONSES)
            image_to_send = "image0.jpg"
        elif any(word in target_text for word in config.RANT_KEYWORDS):
            reply_text = random.choice(config.RANT_RESPONSES)
        elif any(word in target_text for word in config.ADVICE_KEYWORDS):
            reply_text = random.choice(config.ADVICE_RESPONSES)
        elif any(word in target_text for word in config.FLEX_KEYWORDS):
            reply_text = random.choice(config.FLEX_RESPONSES)
        elif any(word in target_text for word in config.SAD_KEYWORDS):
            reply_text = random.choice(config.FORTUNE_NICE)
            image_to_send = "image0.jpg"
        elif any(word in target_text for word in config.HYPE_KEYWORDS):
            reply_text = random.choice(config.FORTUNE_HYPE)
            image_to_send = "pic_4.jpg"
        elif any(word in target_text for word in config.COC_KEYWORDS):
            reply_text = random.choice(config.COC_RESPONSES)
            
        elif re.match(r"^(who|what|where|when|why|how|which)\b", clean_lower):
            reply_text = "..." if user_state["grudge_score"] > 20 else random.choice(config.FORTUNE_OPEN_ENDED)
            
        elif word_count < 5 and user_state["mentioned_topics"]:
            topic = random.choice(list(user_state["mentioned_topics"]))
            topic_responses = {
                "clash": ["bro is still thinking about clash 💀", "go do your war attacks instead 🐦", "coc is life huh 😤"],
                "sleep": ["go to bed then 💀", "bro is sleep deprived 🐦", "im tired just looking at you 😤"],
                "school": ["do your homework bro 💀", "school is a scam anyway 🐦", "pay attention in class 😤"],
                "work": ["get back to work 💀", "capitalism is tough 🐦", "boss makes a dollar i make a dime 😤"]
            }
            reply_text = random.choice(topic_responses[topic])
            
        else:
            reply_text = self.get_smart_fortune(user_state, target_text)
            if reply_text in config.FORTUNE_NICE:
                image_to_send = "image0.jpg"
            elif reply_text in config.FORTUNE_HYPE:
                image_to_send = "pic_4.jpg"
            elif reply_text in ["no.", "sleep.", "stop.", "...", "leave me alone."]:
                image_to_send = "pic_5.jpg"

        if image_to_send == "image0.jpg":
            reply_text = " ".join(reply_text.split()[:4])

        if user_state["grudge_score"] > 20 and not profanity.contains_profanity(clean_content):
            image_to_send = "pic_5.jpg"

        user_state["last_bot_response"] = reply_text
        
        if image_to_send:
            await self.send_image_reply(message, reply_text, image_to_send, is_reply=True)
        else:
            await message.reply(reply_text)

    async def handle_interjection(self, message):
        if random.random() < 0.02: 
            reactions = ["👀", "...", "okay then 🐦", "noted 💀"]
            await message.channel.send(random.choice(reactions))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot: return

        now = time.time()
        user_state = self.bot.user_data[message.author.id]

        self.decay_grudge(user_state, now)
        
        clean_lower = re.sub(rf'^<@!?{self.bot.user.id}>\s*', '', message.content.lower()).strip()
        clean_content = message.content.replace(f'<@{self.bot.user.id}>', '').strip()

        if clean_content:
            user_state["history"].append(clean_content)
            user_state["history"] = user_state["history"][-3:]

        for topic, keywords in config.TOPIC_KEYWORDS.items():
            if any(kw in clean_lower for kw in keywords):
                user_state["mentioned_topics"].add(topic)

        if await self.handle_tweaking(message, user_state, now):
            user_state["last_interaction"] = now
            return

        if await self.handle_greeting(message, user_state, clean_lower, now):
            user_state["last_interaction"] = now
            return

        is_bot_mentioned = self.bot.user in message.mentions
        is_reply = message.reference and getattr(message.reference.resolved, 'author', None) == self.bot.user

        if is_bot_mentioned or is_reply:
            await self.handle_mention(message, user_state, clean_lower, clean_content)
            user_state["last_interaction"] = now
            return

        await self.handle_interjection(message)
        user_state["last_interaction"] = now

async def setup(bot):
    await bot.add_cog(ChatCog(bot))