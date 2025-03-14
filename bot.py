import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
from typing import Optional

# Importa funções auxiliares (ajuste para o seu projeto)
from utils.database import load_server_settings, save_server_settings, load_user_data, save_user_data
from utils.helpers import get_channel, format_time

# Carregar variáveis do .env
load_dotenv()
TOKEN: Optional[str] = os.getenv("DISCORD_TOKEN")

# Carregar configurações e dados
server_settings: dict[str, dict] = load_server_settings()
user_data: dict[str, dict[str, float]] = load_user_data()

# Configurar intents (IMPORTANTE: ativar voice_states = True)
intents: discord.Intents = discord.Intents.default()
intents.typing = False
intents.presences = True
intents.members = True
intents.voice_states = True  # Para receber eventos de voz

bot: commands.Bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree  # Slash commands


# --------------------------------------------------
#             CONFIGURAÇÃO INICIAL DO BOT
# --------------------------------------------------

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
    schedule_summary.start()
    award_tchudu_master.start()  # Não esqueça de iniciar a tarefa de premiação

class RoleSelectionView(View):
    """Janela interativa (View) para escolher cargo."""
    def __init__(self, roles: list[discord.Role], owner_id: int):
        super().__init__(timeout=60)
        self.selected_role: Optional[discord.Role] = None
        self.owner_id = owner_id  # Apenas o dono pode clicar
        self.roles = roles

        for role in roles:
            button = Button(label=role.name, style=discord.ButtonStyle.primary)
            button.callback = self.create_callback(role)
            self.add_item(button)

    def create_callback(self, role: discord.Role):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message(
                    "❌ Apenas o dono do servidor pode selecionar o cargo!", ephemeral=True
                )
                return

            self.selected_role = role
            self.stop()
            await interaction.response.send_message(f"✅ Cargo **{role.name}** selecionado!", ephemeral=True)

        return callback

async def setup_server(guild: discord.Guild) -> None:
    """Configuração automática do servidor com botões para escolha de cargo."""
    guild_id = str(guild.id)

    if guild_id in server_settings:
        print(f"✅ Servidor {guild.name} já configurado. Pulando setup.")
        return

    owner: Optional[discord.Member] = guild.owner
    if not owner:
        return

    # Perguntar ao dono do servidor qual canal usar
    text_channels = guild.text_channels
    channel_options = "\n".join([f"{i+1}️⃣  #{channel.name}" for i, channel in enumerate(text_channels)])

    embed_channel = discord.Embed(
        title="📢 Configuração do Tchudozômetro",
        description="Por favor, escolha o canal onde o bot enviará as enquetes diárias!",
        color=discord.Color.blue()
    )
    embed_channel.add_field(name="📜 Opções disponíveis:", value=channel_options, inline=False)
    embed_channel.set_footer(text="⏳ Responda com o número correspondente.")

    await owner.send(embed=embed_channel)

    def check(m: discord.Message) -> bool:
        return (
            m.author == owner
            and m.content.isdigit()
            and 1 <= int(m.content) <= len(text_channels)
        )

    try:
        msg = await bot.wait_for('message', check=check, timeout=60)
        channel_id = text_channels[int(msg.content) - 1].id
    except asyncio.TimeoutError:
        channel_id = text_channels[0].id  # Usa o primeiro canal por padrão

    # Perguntar qual cargo usar para o "Tchudu Bem Master..."
    roles = [role for role in guild.roles if role.name != "@everyone"]
    if not roles:
        await owner.send("❌ Nenhum cargo disponível para escolher. Crie um cargo e tente novamente!")
        return

    embed_role = discord.Embed(
        title="🏅 Escolha o cargo do 'Tchudu Bem Master...'",
        description="Clique no botão correspondente ao cargo desejado!",
        color=discord.Color.gold()
    )

    view = RoleSelectionView(roles, owner.id)
    message = await owner.send(embed=embed_role, view=view)
    await view.wait()  # Aguarda a resposta do dono do servidor

    if view.selected_role is None:
        await message.edit(
            content="❌ Tempo esgotado! Nenhum cargo foi selecionado.", embed=None, view=None
        )
        return

    role_id = view.selected_role.id

    # Salvar configurações no JSON
    server_settings[guild_id] = {
        "channel_id": channel_id,
        "role_id": role_id,
        "min_call_time": 3600,       # 1 hora
        "weekly_required_time": 7200 # 2 horas
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


# --------------------------------------------------
#                 TAREFAS AGENDADAS
# --------------------------------------------------

def next_run_time(hour: int, minute: int) -> float:
    """Calcula o tempo restante para a próxima execução (em segundos)."""
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
            # Filtra apenas as chaves que começam com "time_"
            time_data = {
                uid: t for uid, t in user_data.get(guild_id, {}).items() 
                if uid.startswith("time_")
            }

            # Conta quantos ficaram >= 1h (3600s) e quantos ficaram < 1h
            eitcha_count = sum(1 for _, time_val in time_data.items() if time_val >= 3600)
            tchudu_bem_count = sum(1 for _, time_val in time_data.items() if 0 < time_val < 3600)

            embed = discord.Embed(
                title="📊 **Resumo do Dia**",
                description="Aqui está o desempenho de hoje! ⏳",
                color=discord.Color.green()
            )
            embed.add_field(
                name="🔥 EiTCHAAAAAAA",
                value=f"🏆 {eitcha_count} jogadores ficaram mais de 1h!",
                inline=False
            )
            embed.add_field(
                name="😴 TCHUDU BEM.... (;-;)",
                value=f"💤 {tchudu_bem_count} passaram menos de 1h.",
                inline=False
            )
            embed.set_footer(text="📅 Estatísticas atualizadas diariamente às 23:00.")

            await channel.send(embed=embed)


# --------------------------------------------------
#                   RANKING
# --------------------------------------------------

@tree.command(name="ranking", description="Mostra quem ficou mais tempo em call")
async def ranking(interaction: discord.Interaction, periodo: Optional[str] = "semana") -> None:
    """Mostra o ranking de quem ficou mais tempo em call."""
    guild_id = str(interaction.guild_id)

    if guild_id not in user_data:
        await interaction.response.send_message("Nenhum dado registrado ainda! 😢", ephemeral=True)
        return

    # Filtra apenas chaves "time_{user_id}"
    time_data = {
        uid[5:]: t  # remove "time_" do começo para pegar só o ID
        for uid, t in user_data[guild_id].items()
        if uid.startswith("time_")
    }

    if not time_data:
        await interaction.response.send_message("Nenhum usuário válido encontrado para o ranking. 😢", ephemeral=True)
        return

    # Ordenar os usuários pelo tempo em call (descendente)
    sorted_users = sorted(time_data.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=f"🏆 Ranking - {periodo.capitalize()}",
        description="Veja quem mais ficou em call!",
        color=discord.Color.gold()
    )

    # Mostra top 10
    for i, (u_id, tempo) in enumerate(sorted_users[:10], start=1):
        user = await bot.fetch_user(int(u_id))
        embed.add_field(name=f"{i}️⃣ {user.name}", value=f"🕒 {format_time(tempo)}", inline=False)

    await interaction.response.send_message(embed=embed)


# ---------------------------------------------------
#            PREMIAÇÃO TCHUDU BEM MASTER
# ---------------------------------------------------

@tasks.loop(hours=24)
async def award_tchudu_master() -> None:
    """A cada mês, premia automaticamente quem menos jogou (1º dia do mês)."""
    now = datetime.now()
    if now.day != 1:  # Somente no primeiro dia do mês
        return

    for guild_id, settings in server_settings.items():
        if guild_id not in user_data:
            continue

        # Filtra apenas chaves "time_{user_id}"
        time_data = {
            uid: t for uid, t in user_data[guild_id].items() if uid.startswith("time_")
        }
        if not time_data:
            continue

        # Identifica o usuário com MENOS tempo de call
        min_user = min(time_data, key=time_data.get, default=None)
        if not min_user:
            continue

        # "min_user" é algo como "time_123456", então pegamos só o ID
        actual_min_user_id = min_user[5:]

        guild = bot.get_guild(int(guild_id))
        if not guild:
            continue

        role = guild.get_role(settings["role_id"])
        if not role:
            continue

        member = guild.get_member(int(actual_min_user_id))
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


# --------------------------------------------------
#         SISTEMA DE XP / NÍVEIS POR TEMPO EM CALL
# --------------------------------------------------

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    """Registra tempo em call e dá XP baseado no tempo."""
    guild_id = str(member.guild.id)
    user_id = str(member.id)

    # [DEBUG opcional] print(f"[DEBUG] {member} entrou/saiu de call. Before={before.channel}, After={after.channel}")

    # Se entrou na call (after.channel != None) e não estava em call antes
    if after.channel and not before.channel:
        # Salva o timestamp de entrada na call
        user_data.setdefault(guild_id, {})[f"join_{user_id}"] = datetime.utcnow().timestamp()

    # Se saiu da call (before.channel != None) e não entrou em outra call (after.channel == None)
    elif before.channel and not after.channel:
        join_key = f"join_{user_id}"
        join_time = user_data[guild_id].pop(join_key, None)
        if join_time:
            # Calcula a duração em segundos
            duration = datetime.utcnow().timestamp() - join_time

            # Soma no tempo total
            time_key = f"time_{user_id}"
            total_time = user_data[guild_id].get(time_key, 0) + duration
            user_data[guild_id][time_key] = total_time

            # Cálculo de XP: 10 XP a cada 10 minutos (600s) - AJUSTE se quiser testar mais rápido
            xp_ganho = int(duration // 600) * 10
            xp_key = f"xp_{user_id}"
            xp_atual = user_data[guild_id].get(xp_key, 0) + xp_ganho
            user_data[guild_id][xp_key] = xp_atual

            # Nível = xp // 100 (por exemplo, 100 XP = Nível 1)
            nivel_key = f"nivel_{user_id}"
            nivel_anterior = user_data[guild_id].get(nivel_key, 0)
            nivel_atual = xp_atual // 100

            # Se subiu de nível
            if nivel_atual > nivel_anterior:
                user_data[guild_id][nivel_key] = nivel_atual

                # Anuncia o level up
                embed = discord.Embed(
                    title="🎉 Subiu de nível!",
                    description=f"Parabéns {member.mention}, você agora é **Nível {nivel_atual}**!",
                    color=discord.Color.green()
                )
                channel = get_channel(bot, guild_id)
                if channel:
                    await channel.send(embed=embed)

            # Salva as alterações no JSON
            save_user_data(user_data)


# --------------------------------------------------
#         COMANDO SLASH: /level (ou /level)
# --------------------------------------------------

@tree.command(name="level", description="Mostra seu XP e nível no servidor")
async def level(interaction: discord.Interaction) -> None:
    """Mostra o nível e XP do usuário."""
    guild_id = str(interaction.guild_id)
    user_id = str(interaction.user.id)

    xp_key = f"xp_{user_id}"
    nivel_key = f"nivel_{user_id}"

    xp_total = user_data.get(guild_id, {}).get(xp_key, 0)
    nivel = user_data.get(guild_id, {}).get(nivel_key, 0)

    embed = discord.Embed(
        title="📊 Seu progresso",
        description=f"🎮 **XP:** {xp_total}\n🏆 **Nível:** {nivel}",
        color=discord.Color.blue()
    )

    await interaction.response.send_message(embed=embed)


# --------------------------------------------------
#                INICIAR O BOT
# --------------------------------------------------

if TOKEN:
    bot.run(TOKEN)
else:
    print("Erro: DISCORD_TOKEN não foi encontrado no .env")
