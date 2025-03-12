import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import os

# Importa funções auxiliares
from utils.database import load_server_settings, save_server_settings, load_user_data, save_user_data
from utils.helpers import get_channel, format_time

# Carregar variáveis do .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Carregar configurações e dados
server_settings = load_server_settings()
user_data = load_user_data()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    """Executado quando o bot está pronto."""
    print(f'✅ Bot {bot.user.name} está online!')
    for guild in bot.guilds:
        if str(guild.id) not in server_settings:
            await setup_server(guild)  # Configurar servidores automaticamente
    daily_poll.start()
    daily_summary.start()

async def setup_server(guild: discord.Guild) -> None:
    """Configura automaticamente um novo servidor."""
    owner = guild.owner
    if not owner:
        return

    # Perguntar ao dono do servidor qual canal usar
    text_channels = guild.text_channels
    channel_msg = "Escolha o canal onde o bot postará a enquete:\n"
    for i, channel in enumerate(text_channels, 1):
        channel_msg += f"{i}. {channel.name}\n"
    
    await owner.send(channel_msg + "Responda com o número correspondente.")

    def check(m: discord.Message) -> bool:
        return m.author == owner and m.content.isdigit() and 1 <= int(m.content) <= len(text_channels)

    try:
        msg = await bot.wait_for('message', check=check, timeout=60)
        channel_id = text_channels[int(msg.content) - 1].id
    except asyncio.TimeoutError:
        channel_id = text_channels[0].id  # Usa o primeiro canal por padrão

    # Perguntar qual cargo usar para o "Tchudu Bem Master..."
    roles = [role for role in guild.roles if role.name != "@everyone"]
    role_msg = "Escolha o cargo para o 'Tchudu Bem Master...':\n"
    for i, role in enumerate(roles, 1):
        role_msg += f"{i}. {role.name}\n"

    await owner.send(role_msg + "Responda com o número correspondente.")

    def check_role(m: discord.Message) -> bool:
        return m.author == owner and m.content.isdigit() and 1 <= int(m.content) <= len(roles)

    try:
        msg = await bot.wait_for('message', check=check_role, timeout=60)
        role_id = roles[int(msg.content) - 1].id
    except asyncio.TimeoutError:
        role_id = roles[0].id  # Usa o primeiro cargo como padrão

    # Salvar configurações no JSON
    server_settings[str(guild.id)] = {
        "channel_id": channel_id,
        "role_id": role_id,
        "min_call_time": 3600,  # Tempo mínimo diário para ser contado como "EiTCHAAAAAAA"
        "weekly_required_time": 7200  # Tempo mínimo semanal obrigatório
    }
    save_server_settings(server_settings)

    print(f"✅ Configuração salva para {guild.name}: Canal {channel_id}, Cargo {role_id}")

@tasks.loop(hours=24)
async def daily_poll():
    """Posta a enquete diária."""
    for guild_id, settings in server_settings.items():
        channel = get_channel(bot, guild_id)
        if channel:
            message = await channel.send(
                "Hoje é 'eitcha' ou é 'tchudu bem'?\n"
                "🟠 **EiTCHAAAAAAA**\n🔵 **OPA...**\n🟢 **TCHUDU BEM....**\n🔴 **FUI BUSCAR O CRACHÁ**"
            )
            for reaction in ["🟠", "🔵", "🟢", "🔴"]:
                await message.add_reaction(reaction)

@tasks.loop(hours=24)
async def daily_summary():
    """Gera o resumo diário baseado nos votos e no tempo em call."""
    for guild_id, settings in server_settings.items():
        channel = get_channel(bot, guild_id)
        if channel:
            eitcha_count = sum(1 for user_id, time in user_data.get(str(guild_id), {}).items() if time >= 3600)
            tchudu_bem_count = sum(1 for user_id, time in user_data.get(str(guild_id), {}).items() if time < 3600)

            summary = f"📊 **Resumo do Dia**:\n🔹 **EiTCHAAAAAAA**: {eitcha_count}\n🔹 **TCHUDU BEM.... (;-;)**: {tchudu_bem_count}"
            await channel.send(summary)

@bot.event
async def on_voice_state_update(member, before, after):
    """Registra tempo em call."""
    guild_id, user_id = str(member.guild.id), str(member.id)

    if after.channel and not before.channel:
        user_data.setdefault(guild_id, {})[user_id] = datetime.utcnow().timestamp()
    elif before.channel and not after.channel and user_id in user_data.get(guild_id, {}):
        duration = datetime.utcnow().timestamp() - user_data[guild_id][user_id]
        user_data[guild_id][user_id] = user_data[guild_id].get(user_id, 0) + duration
        save_user_data(user_data)

@bot.command(name="meutempo")
async def meutempo(ctx):
    """Mostra o tempo total que o usuário ficou em call."""
    guild_id, user_id = str(ctx.guild.id), str(ctx.author.id)
    total_time = user_data.get(guild_id, {}).get(user_id, 0)
    await ctx.send(f"🕒 {ctx.author.mention}, você passou {format_time(total_time)} em call!")

# Iniciar o bot
if TOKEN:
    bot.run(TOKEN)
else:
    print("Erro: DISCORD_TOKEN não foi encontrado no .env")