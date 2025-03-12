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
    schedule_summary.start()  # Corrigido: Adicionando a tarefa do resumo

async def setup_server(guild: discord.Guild) -> None:
    """Configura automaticamente um novo servidor apenas se ele ainda não estiver salvo."""
    guild_id = str(guild.id)

    if guild_id in server_settings:
        print(f"✅ Servidor {guild.name} já está configurado. Pulando setup.")
        return

    owner: Optional[discord.Member] = guild.owner
    if not owner:
        return

    # Perguntar ao dono do servidor qual canal usar
    text_channels = guild.text_channels
    channel_options = "\n".join(
        [f"{i+1}️⃣  #{channel.name}" for i, channel in enumerate(text_channels)]
    )

    embed_channel = discord.Embed(
        title="📢 Configuração do Tchudozômetro",
        description="Por favor, escolha o canal onde o bot enviará as enquetes diárias!",
        color=discord.Color.blue()
    )
    embed_channel.add_field(
        name="📜 Opções disponíveis:",
        value=channel_options,
        inline=False
    )
    embed_channel.set_footer(text="⏳ Responda com o número correspondente.")

    await owner.send(embed=embed_channel)

    def check(m: discord.Message) -> bool:
        return m.author == owner and m.content.isdigit() and 1 <= int(m.content) <= len(text_channels)

    try:
        msg = await bot.wait_for('message', check=check, timeout=60)
        channel_id = text_channels[int(msg.content) - 1].id
    except asyncio.TimeoutError:
        channel_id = text_channels[0].id  # Usa o primeiro canal por padrão

    # Perguntar qual cargo usar para o "Tchudu Bem Master..."
    roles = [role for role in guild.roles if role.name != "@everyone"]
    role_options = "\n".join(
        [f"{i+1}️⃣  @{role.name}" for i, role in enumerate(roles)]
    )

    embed_role = discord.Embed(
        title="🏅 Escolha o cargo do 'Tchudu Bem Master...'",
        description="Qual cargo deve ser atribuído ao jogador com menos tempo em call?",
        color=discord.Color.gold()
    )
    embed_role.add_field(
        name="🎭 Opções disponíveis:",
        value=role_options,
        inline=False
    )
    embed_role.set_footer(text="⏳ Responda com o número correspondente.")

    await owner.send(embed=embed_role)

    def check_role(m: discord.Message) -> bool:
        return m.author == owner and m.content.isdigit() and 1 <= int(m.content) <= len(roles)

    try:
        msg = await bot.wait_for('message', check=check_role, timeout=60)
        role_id = roles[int(msg.content) - 1].id
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

    embed_confirm = discord.Embed(
        title="✅ Configuração concluída!",
        description="Tchudozômetro está pronto para começar!",
        color=discord.Color.green()
    )
    embed_confirm.add_field(name="📢 Canal escolhido:", value=f"<#{channel_id}>", inline=False)
    embed_confirm.add_field(name="🏅 Cargo escolhido:", value=f"<@&{role_id}>", inline=False)
    embed_confirm.set_footer(text="🚀 O bot começará a enviar as enquetes diariamente às 07:00!")

    await owner.send(embed=embed_confirm)

    print(f"✅ Configuração salva para {guild.name}: Canal {channel_id}, Cargo {role_id}")

def next_run_time(hour: int, minute: int) -> float:
    """Calcula o tempo restante para a próxima execução."""
    now = datetime.now()
    next_run = datetime(now.year, now.month, now.day, hour, minute)
    if now >= next_run:
        next_run += timedelta(days=1)
    return (next_run - now).total_seconds()

@tasks.loop(hours=24)
async def schedule_poll() -> None:
    """Aguarda até as 07:00 da manhã para postar a enquete diária."""
    await asyncio.sleep(next_run_time(7, 0))
    await daily_poll()

@tasks.loop(hours=24)
async def schedule_summary() -> None:
    """Aguarda até as 23:00 para enviar o resumo diário."""
    await asyncio.sleep(next_run_time(23, 0))
    await daily_summary()

async def daily_poll() -> None:
    """Posta a enquete diária às 7:00 da manhã."""
    for guild_id, settings in server_settings.items():
        channel = get_channel(bot, guild_id)
        if channel:
            embed = discord.Embed(
                title="📢 Hoje é 'EITCHA' ou 'TCHUDU BEM'?",
                description="Vote abaixo e registre sua presença! 🎮",
                color=discord.Color.blue()
            )
            embed.add_field(name="🟠 EiTCHAAAAAAA", value="🔥 Fiquei mais de 1h!", inline=False)
            embed.add_field(name="🔵 OPA...", value="👀 Ainda não sei...", inline=False)
            embed.add_field(name="🟢 TCHUDU BEM....", value="💤 Passei menos de 1h na call...", inline=False)
            embed.add_field(name="🔴 FUI BUSCAR O CRACHÁ", value="🚪 Não participei hoje.", inline=False)
            embed.set_footer(text="📅 Vote antes da meia-noite!")

            message = await channel.send(embed=embed)
            for reaction in ["🟠", "🔵", "🟢", "🔴"]:
                await message.add_reaction(reaction)

async def daily_summary() -> None:
    """Envia o resumo diário às 23:00."""
    for guild_id, settings in server_settings.items():
        channel = get_channel(bot, guild_id)
        if channel:
            eitcha_count = sum(1 for user_id, time in user_data.get(str(guild_id), {}).items() if time >= 3600)
            tchudu_bem_count = sum(1 for user_id, time in user_data.get(str(guild_id), {}).items() if time < 3600)

            embed = discord.Embed(
                title="📊 **Resumo do Dia**",
                description="Aqui está o desempenho de hoje! ⏳",
                color=discord.Color.green()
            )
            embed.add_field(name="🔥 EiTCHAAAAAAA", value=f"🏆 {eitcha_count} jogadores ficaram mais de 1h!", inline=False)
            embed.add_field(name="😴 TCHUDU BEM.... (;-;)", value=f"💤 {tchudu_bem_count} passaram menos de 1h.", inline=False)
            embed.set_footer(text="📅 Estatísticas atualizadas diariamente às 23:00.")

            await channel.send(embed=embed)

# Iniciar o bot
if TOKEN:
    bot.run(TOKEN)
else:
    print("Erro: DISCORD_TOKEN não foi encontrado no .env")