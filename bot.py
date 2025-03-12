import discord
from discord import app_commands
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

# Registrar os slash commands
tree = bot.tree

@bot.event
async def on_ready() -> None:
    """Executado quando o bot está pronto."""
    print(f'✅ Bot {bot.user.name} está online!' if bot.user else "Bot está online!")
    await bot.tree.sync()
    print("📌 Slash commands sincronizados!")

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

### 📌 Comando !ranking ###
@tree.command(name="ranking", description="Mostra quem ficou mais tempo em call")
async def ranking(interaction: discord.Interaction, periodo: Optional[str] = "semana") -> None:
    """Mostra o ranking de quem ficou mais tempo em call."""
    guild_id = str(interaction.guild_id)

    if guild_id not in user_data:
        await interaction.response.send_message("Nenhum dado registrado ainda! 😢", ephemeral=True)
        return

    ranking_data = user_data[guild_id]

    # 📌 **Filtrar apenas os IDs numéricos dos usuários**
    valid_users = {user_id: tempo for user_id, tempo in ranking_data.items() if user_id.isdigit()}

    if not valid_users:
        await interaction.response.send_message("Nenhum usuário válido encontrado para o ranking. 😢", ephemeral=True)
        return

    # Ordenar os usuários pelo tempo em call
    sorted_users = sorted(valid_users.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=f"🏆 Ranking - {periodo.capitalize()}",
        description="Veja quem mais ficou em call!",
        color=discord.Color.gold()
    )

    for i, (user_id, tempo) in enumerate(sorted_users[:10], start=1):
        user = await bot.fetch_user(int(user_id))  # Agora pegamos somente IDs numéricos válidos
        embed.add_field(name=f"{i}️⃣ {user.name}", value=f"🕒 {format_time(tempo)}", inline=False)

    await interaction.response.send_message(embed=embed)

### 📌 Premiação automática: "Tchudu Bem Master" ###
@tasks.loop(hours=24)
async def award_tchudu_master() -> None:
    """A cada mês, premia automaticamente quem menos jogou."""
    now = datetime.now()
    if now.day != 1:  # Somente no primeiro dia do mês
        return

    for guild_id, settings in server_settings.items():
        if guild_id not in user_data:
            continue

        # Identifica o usuário com MENOS tempo de call
        min_user = min(user_data[guild_id], key=user_data[guild_id].get, default=None)
        if not min_user:
            continue

        guild = bot.get_guild(int(guild_id))
        if not guild:
            continue

        role = guild.get_role(settings["role_id"])
        if not role:
            continue

        member = guild.get_member(int(min_user))
        if not member:
            continue

        # Remove o cargo do antigo "Tchudu Bem Master"
        for m in guild.members:
            if role in m.roles:
                await m.remove_roles(role)

        # Adiciona o cargo ao novo "Tchudu Bem Master"
        await member.add_roles(role)

        embed = discord.Embed(
            title="🏅 Novo Tchudu Bem Master!",
            description=f"😱 {member.mention} ficou com **menos tempo em call** este mês!",
            color=discord.Color.red()
        )
        embed.set_footer(text="Tente se redimir no próximo mês... 😂")

        channel = get_channel(bot, guild_id)
        if channel:
            await channel.send(embed=embed)

### 📌 Sistema de XP e níveis ###
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    """Registra tempo em call e dá XP baseado no tempo."""
    guild_id = str(member.guild.id)
    user_id = str(member.id)

    if after.channel and not before.channel:
        user_data.setdefault(guild_id, {})[user_id] = datetime.utcnow().timestamp()
    elif before.channel and not after.channel and user_id in user_data.get(guild_id, {}):
        duration = datetime.utcnow().timestamp() - user_data[guild_id][user_id]
        user_data[guild_id][user_id] = user_data[guild_id].get(user_id, 0) + duration
        save_user_data(user_data)

    # Sistema de XP: ganha 10 XP por cada 10 minutos em call
    xp_ganho = (duration // 600) * 10  # A cada 10 minutos = +10 XP
    xp_nivel = user_data[guild_id].get(f"xp_{user_id}", 0) + xp_ganho

    # Atualiza o XP do usuário
    user_data[guild_id][f"xp_{user_id}"] = xp_nivel
    save_user_data(user_data)

    # Sistema de níveis: a cada 100 XP, sobe de nível
    level_atual = xp_nivel // 100
    nivel_anterior = user_data[guild_id].get(f"nivel_{user_id}", 0)

    if level_atual > nivel_anterior:
        user_data[guild_id][f"nivel_{user_id}"] = level_atual
        save_user_data(user_data)

        embed = discord.Embed(
            title="🎉 Subiu de nível!",
            description=f"Parabéns {member.mention}, você agora é **Nível {level_atual}**!",
            color=discord.Color.green()
        )
        channel = get_channel(bot, guild_id)
        if channel:
            await channel.send(embed=embed)

### 📌 Comando para ver o nível ###
@tree.command(name="meunivel", description="Mostra seu XP e nível no servidor")
async def meunivel(interaction: discord.Interaction) -> None:
    """Mostra o nível e XP do usuário."""
    guild_id = str(interaction.guild_id)
    user_id = str(interaction.user.id)

    xp_total = user_data.get(guild_id, {}).get(f"xp_{user_id}", 0)
    nivel = user_data.get(guild_id, {}).get(f"nivel_{user_id}", 0)

    embed = discord.Embed(
        title="📊 Seu progresso",
        description=f"🎮 **XP:** {xp_total}\n🏆 **Nível:** {nivel}",
        color=discord.Color.blue()
    )

    await interaction.response.send_message(embed=embed)

# Iniciar o bot
if TOKEN:
    bot.run(TOKEN)
else:
    print("Erro: DISCORD_TOKEN não foi encontrado no .env")