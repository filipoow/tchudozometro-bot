import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
from typing import Optional

# Importa funções auxiliares
from utils.database import load_server_settings, save_server_settings, load_user_data, save_user_data
from utils.helpers import get_channel, format_time

# Carregar variáveis do .env
load_dotenv()
TOKEN: Optional[str] = os.getenv("DISCORD_TOKEN")

# Carregar configurações e dados
server_settings: dict[str, dict] = load_server_settings()
user_data: dict[str, dict[str, float]] = load_user_data()

# Configurar intents para evitar erro de Privileged Intents
intents: discord.Intents = discord.Intents.default()
intents.typing = False
intents.presences = True
intents.members = True

bot: commands.Bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready() -> None:
    """Executado quando o bot está pronto."""
    print(f'✅ Bot {bot.user.name} está online!' if bot.user else "Bot está online!")
    for guild in bot.guilds:
        if str(guild.id) not in server_settings:
            await setup_server(guild)

    # Iniciar as tarefas agendadas
    schedule_poll.start()
    schedule_summary.start()

async def setup_server(guild: discord.Guild) -> None:
    """Configura automaticamente um novo servidor apenas se ele ainda não estiver salvo."""
    guild_id = str(guild.id)

    # Se o servidor já está salvo, não faz nada
    if guild_id in server_settings:
        print(f"✅ Servidor {guild.name} já está configurado. Pulando setup.")
        return

    owner: Optional[discord.Member] = guild.owner
    if not owner:
        return

    # Perguntar ao dono do servidor qual canal usar
    text_channels: list[discord.TextChannel] = guild.text_channels
    channel_msg: str = "Escolha o canal onde o bot postará a enquete:\n"
    for i, channel in enumerate(text_channels, 1):
        channel_msg += f"{i}. {channel.name}\n"

    await owner.send(channel_msg + "Responda com o número correspondente.")

    def check(m: discord.Message) -> bool:
        return m.author == owner and m.content.isdigit() and 1 <= int(m.content) <= len(text_channels)

    try:
        msg: discord.Message = await bot.wait_for('message', check=check, timeout=60)
        channel_id: int = text_channels[int(msg.content) - 1].id
    except asyncio.TimeoutError:
        channel_id = text_channels[0].id  # Usa o primeiro canal por padrão

    # Perguntar qual cargo usar para o "Tchudu Bem Master..."
    roles: list[discord.Role] = [role for role in guild.roles if role.name != "@everyone"]
    role_msg: str = "Escolha o cargo para o 'Tchudu Bem Master...':\n"
    for i, role in enumerate(roles, 1):
        role_msg += f"{i}. {role.name}\n"

    await owner.send(role_msg + "Responda com o número correspondente.")

    def check_role(m: discord.Message) -> bool:
        return m.author == owner and m.content.isdigit() and 1 <= int(m.content) <= len(roles)

    try:
        msg = await bot.wait_for('message', check=check_role, timeout=60)
        role_id: int = roles[int(msg.content) - 1].id
    except asyncio.TimeoutError:
        role_id = roles[0].id  # Usa o primeiro cargo como padrão

    # Salvar configurações no JSON
    server_settings[guild_id] = {
        "channel_id": channel_id,
        "role_id": role_id,
        "min_call_time": 3600,
        "weekly_required_time": 7200
    }
    save_server_settings(server_settings)

    print(f"✅ Configuração salva para {guild.name}: Canal {channel_id}, Cargo {role_id}")

def next_run_time(hour: int, minute: int) -> float:
    """Calcula o tempo restante para a próxima execução."""
    now = datetime.now()
    next_run = datetime(now.year, now.month, now.day, hour, minute)
    if now >= next_run:
        next_run += timedelta(days=1)  # Agenda para o próximo dia
    return (next_run - now).total_seconds()

@tasks.loop(hours=24)
async def schedule_poll() -> None:
    """Aguarda até as 07:00 da manhã para postar a enquete diária."""
    await asyncio.sleep(next_run_time(7, 0))  # Aguarda até as 07:00
    await daily_poll()

async def daily_poll() -> None:
    """Posta a enquete diária às 7:00 da manhã."""
    for guild_id, settings in server_settings.items():
        channel: Optional[discord.TextChannel] = get_channel(bot, guild_id)
        if channel:
            message: discord.Message = await channel.send(
                "Hoje é 'eitcha' ou é 'tchudu bem'?\n"
                "🟠 **EiTCHAAAAAAA**\n🔵 **OPA...**\n🟢 **TCHUDU BEM....**\n🔴 **FUI BUSCAR O CRACHÁ**"
            )
            for reaction in ["🟠", "🔵", "🟢", "🔴"]:
                await message.add_reaction(reaction)

@tasks.loop(hours=24)
async def schedule_summary() -> None:
    """Aguarda até as 23:00 para enviar o resumo diário."""
    await asyncio.sleep(next_run_time(23, 0))  # Aguarda até as 23:00
    await daily_summary()

async def daily_summary() -> None:
    """Envia o resumo diário às 23:00."""
    for guild_id, settings in server_settings.items():
        channel: Optional[discord.TextChannel] = get_channel(bot, guild_id)
        if channel:
            eitcha_count: int = sum(1 for user_id, time in user_data.get(str(guild_id), {}).items() if time >= 3600)
            tchudu_bem_count: int = sum(1 for user_id, time in user_data.get(str(guild_id), {}).items() if time < 3600)

            summary: str = f"📊 **Resumo do Dia**:\n🔹 **EiTCHAAAAAAA**: {eitcha_count}\n🔹 **TCHUDU BEM.... (;-;)**: {tchudu_bem_count}"
            await channel.send(summary)

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    """Registra tempo em call."""
    guild_id: str = str(member.guild.id)
    user_id: str = str(member.id)

    if after.channel and not before.channel:
        user_data.setdefault(guild_id, {})[user_id] = datetime.utcnow().timestamp()
    elif before.channel and not after.channel and user_id in user_data.get(guild_id, {}):
        duration: float = datetime.utcnow().timestamp() - user_data[guild_id][user_id]
        user_data[guild_id][user_id] = user_data[guild_id].get(user_id, 0) + duration
        save_user_data(user_data)

@bot.command(name="meutempo")
async def meutempo(ctx: commands.Context) -> None:
    """Mostra o tempo total que o usuário ficou em call."""
    guild_id: str = str(ctx.guild.id)
    user_id: str = str(ctx.author.id)
    total_time: float = user_data.get(guild_id, {}).get(user_id, 0)
    await ctx.send(f"🕒 {ctx.author.mention}, você passou {format_time(total_time)} em call!")

# Iniciar o bot
if TOKEN:
    bot.run(TOKEN)
else:
    print("Erro: DISCORD_TOKEN não foi encontrado no .env")
