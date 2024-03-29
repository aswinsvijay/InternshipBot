import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
from utils import sql, google
import datetime

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')          # Bot access token

class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # lastdate is the last day when internships were purged from channels
        # lastdate is set as the day before, to ensure internships are purged when bot comes online
        self.lastdate = datetime.datetime.now().date() - datetime.timedelta(days=1)
        self.db = None

        self.loop.create_task(self.startup())   #startup tasks

    async def startup(self):
        await self.wait_until_ready()
        self.db = await sql.database_connect()

        self.delete_internships_loop.start()

        owner = (await self.application_info()).owner
        self.owner_id = owner.id
        await owner.send(f'{self.user.name} is ready.')

    @tasks.loop(minutes=15)
    async def delete_internships_loop(self):
        today = datetime.datetime.now().date()

        if today != self.lastdate:
            internships = await self.db.delete_internships(today)
            forms_list = [i[2] for i in internships]
            await google.close_forms(forms_list)
            internships_dict = dict()
            for i in internships:
                internships_dict.setdefault(i[0], []).append(i[1])

            for channel_id in internships_dict.keys():
                channel = self.get_channel(channel_id)
                for message_id in internships_dict[channel_id]:
                    message = channel.get_partial_message(message_id)
                    await message.delete()
            self.lastdate = today

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return

        # If message starts with bot's command prefix, process commands and return
        if message.content.startswith(tuple(self.command_prefix(self, message))):
            await self.process_commands(message)
            return

        # If message sender is Zapier and message is in the designated channel
        # consider it as internship
        if message.author.name == 'Zapier':
            if message.channel.id == await self.db.get_internship_channel(message.guild.id):
                await self.internship(message)

    async def internship(self, message):
        message.content = message.content.split('\n')
        title = message.content[0]
        email = message.content[1]
        date = message.content[2]
        date = datetime.datetime.strptime(date, '%m/%d/%Y').date()

        form = await google.create_form(title, email)
        if len(form)==2:
            await self.db.add_internship(
                message.id, message.guild.id,
                title, email, date,
                form[0], form[1]
            )
            await message.add_reaction('✅')

# Setting up the bot
bot = Bot(
    commands.when_mentioned,
    strip_after_prefix = True,
    help_command = commands.DefaultHelpCommand(
        no_category = 'Others'
    )
)

if __name__ == '__main__':
    # Cogs for the bot
    for file in os.listdir('./cogs'):
        if file.endswith('.py'):
            bot.load_extension(f'cogs.{file[:-3]}')

    bot.run(BOT_TOKEN)
