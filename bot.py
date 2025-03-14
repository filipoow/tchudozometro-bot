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

# ============================================================
#                    CLASSES DE VIEW
# ============================================================

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

class PassouView(discord.ui.View):
    """View com botões: Sim, Não e, quando houver votos suficientes, Condenar."""
    def __init__(self, accuser: discord.Member, accused: discord.Member):
        super().__init__(timeout=None)  # Sem timeout (ou defina um se preferir)
        self.accuser = accuser
        self.accused = accused
        self.sim_count = 0
        self.nao_count = 0

    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Se Passou ou não se passou?",
            description=f"{self.accuser.mention} acha que {self.accused.mention} se passou demais!",
            color=discord.Color.orange()
        )
        embed.set_image(url="https://i.gifer.com/72gi.gif")
        embed.add_field(name="Acho... que sim", value=str(self.sim_count), inline=True)
        embed.add_field(name="Não....", value=str(self.nao_count), inline=True)
        return embed

    @discord.ui.button(label="Sim", style=discord.ButtonStyle.success)
    async def sim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.sim_count += 1
        # Habilita o botão 'Condenar' se houver pelo menos 2 votos de "Sim"
        if self.sim_count >= 2:
            self.condenar_button.disabled = False
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Não", style=discord.ButtonStyle.danger)
    async def nao_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.nao_count += 1
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Condenar", style=discord.ButtonStyle.primary, disabled=True)
    async def condenar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        condemnation_embed = discord.Embed(
            title="Condenado!",
            description=f"{self.accused.mention} foi condenado(a) por se passar demais!",
            color=discord.Color.red()
        )
        condemnation_embed.set_image(url="https://i.gifer.com/EfF.gif")
        await interaction.response.send_message(embed=condemnation_embed)
        # Desabilita os botões após a condenação
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

# ============================================================
#                 COMANDOS SLASH
# ============================================================

@tree.command(name="passou", description="Inicia uma votação para ver se alguém se passou demais.")
async def passou(interaction: discord.Interaction, target: discord.Member) -> None:
    """
    Comando /passou: o autor acusa 'target' de ter se passado.
    Cria um embed com botões "Sim", "Não" e (posteriormente) "Condenar".
    """
    accuser = interaction.user
    accused = target
    view = PassouView(accuser, accused)
    embed = view.create_embed()
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="choquederealidade", description="Dá um choque de realidade em alguém!")
async def choquederealidade(interaction: discord.Interaction, target: discord.Member) -> None:
    """
    Comando para aplicar um choque de realidade.
    Atualiza os contadores e envia um embed com o GIF e os dados de choques.
    """
    giver: discord.Member = interaction.user
    receiver: discord.Member = target
    guild_id: str = str(interaction.guild.id)

    if guild_id not in user_data:
        user_data[guild_id] = {}

    giver_dado_key = f"choque_dado_{giver.id}"
    giver_recebido_key = f"choque_recebido_{giver.id}"
    receiver_dado_key = f"choque_dado_{receiver.id}"
    receiver_recebido_key = f"choque_recebido_{receiver.id}"

    if giver_dado_key not in user_data[guild_id]:
        user_data[guild_id][giver_dado_key] = 0
    if giver_recebido_key not in user_data[guild_id]:
        user_data[guild_id][giver_recebido_key] = 0
    if receiver_dado_key not in user_data[guild_id]:
        user_data[guild_id][receiver_dado_key] = 0
    if receiver_recebido_key not in user_data[guild_id]:
        user_data[guild_id][receiver_recebido_key] = 0

    user_data[guild_id][giver_dado_key] += 1
    user_data[guild_id][receiver_recebido_key] += 1

    save_user_data(user_data)

    embed = discord.Embed(
        title="⚡ Choque de Realidade!",
        description=f"{giver.mention} aplicou um choque de realidade em {receiver.mention}!",
        color=discord.Color.purple()
    )
    embed.set_author(name=giver.display_name, icon_url=giver.display_avatar.url)
    embed.set_image(url="https://i.gifer.com/1IYp.gif")
    embed.set_footer(text=receiver.display_name, icon_url=receiver.display_avatar.url)
    embed.add_field(
        name=f"{giver.display_name}",
        value=(f"**Choques dados:** {user_data[guild_id][giver_dado_key]}\n"
               f"**Choques recebidos:** {user_data[guild_id][giver_recebido_key]}"),
        inline=True
    )
    embed.add_field(
        name=f"{receiver.display_name}",
        value=(f"**Choques dados:** {user_data[guild_id][receiver_dado_key]}\n"
               f"**Choques recebidos:** {user_data[guild_id][receiver_recebido_key]}"),
        inline=True
    )

    await interaction.response.send_message(embed=embed)

@tree.command(name="ranking", description="Mostra quem ficou mais tempo em call")
async def ranking(interaction: discord.Interaction, periodo: Optional[str] = "semana") -> None:
    guild_id = str(interaction.guild_id)
    if guild_id not in user_data:
        await interaction.response.send_message("Nenhum dado registrado ainda! 😢", ephemeral=True)
        return

    time_data = {
        uid[5:]: t
        for uid, t in user_data[guild_id].items() 
        if uid.startswith("time_")
    }
    if not time_data:
        await interaction.response.send_message("Nenhum usuário válido encontrado para o ranking. 😢", ephemeral=True)
        return

    sorted_users = sorted(time_data.items(), key=lambda x: x[1], reverse=True)
    embed = discord.Embed(
        title=f"🏆 Ranking - {periodo.capitalize()}",
        description="Veja quem mais ficou em call!",
        color=discord.Color.gold()
    )
    for i, (u_id, tempo) in enumerate(sorted_users[:10], start=1):
        user = await bot.fetch_user(int(u_id))
        embed.add_field(name=f"{i}️⃣ {user.name}", value=f"🕒 {format_time(tempo)}", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="level", description="Mostra seu XP e nível no servidor")
async def level(interaction: discord.Interaction) -> None:
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

# ============================================================
#                     EVENTOS E TAREFAS
# ============================================================

@bot.event
async def on_ready() -> None:
    print(f'✅ Bot {bot.user.name} está online!' if bot.user else "Bot está online!")
    try:
        synced = await bot.tree.sync()
        print(f"📌 Sincronizados {len(synced)} comandos slash!")

        # Listar os comandos sincronizados
        for command in synced:
            print(f"- {command.name}")
    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")

    for guild in bot.guilds:
        if str(guild.id) not in server_settings:
            await setup_server(guild)

    schedule_poll.start()
    schedule_summary.start()
    award_tchudu_master.start()

async def setup_server(guild: discord.Guild) -> None:
    guild_id = str(guild.id)
    if guild_id in server_settings:
        print(f"✅ Servidor {guild.name} já configurado. Pulando setup.")
        return
    owner: Optional[discord.Member] = guild.owner
    if not owner:
        return

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
        return (m.author == owner and m.content.isdigit() and 1 <= int(m.content) <= len(text_channels))
    try:
        msg = await bot.wait_for('message', check=check, timeout=60)
        channel_id = text_channels[int(msg.content) - 1].id
    except asyncio.TimeoutError:
        channel_id = text_channels[0].id

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
    await view.wait()
    if view.selected_role is None:
        await message.edit(content="❌ Tempo esgotado! Nenhum cargo foi selecionado.", embed=None, view=None)
        return

    role_id = view.selected_role.id
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

def next_run_time(hour: int, minute: int) -> float:
    now = datetime.now()
    next_run = datetime(now.year, now.month, now.day, hour, minute)
    if now >= next_run:
        next_run += timedelta(days=1)
    return (next_run - now).total_seconds()

@tasks.loop(hours=24)
async def schedule_poll() -> None:
    await asyncio.sleep(next_run_time(7, 0))
    await daily_poll()

@tasks.loop(hours=24)
async def schedule_summary() -> None:
    await asyncio.sleep(next_run_time(23, 0))
    await daily_summary()

async def daily_poll() -> None:
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
    for guild_id, settings in server_settings.items():
        channel = get_channel(bot, guild_id)
        if channel:
            time_data = { uid: t for uid, t in user_data.get(guild_id, {}).items() if uid.startswith("time_") }
            eitcha_count = sum(1 for _, time_val in time_data.items() if time_val >= 3600)
            tchudu_bem_count = sum(1 for _, time_val in time_data.items() if 0 < time_val < 3600)
            embed = discord.Embed(
                title="📊 **Resumo do Dia**",
                description="Aqui está o desempenho de hoje! ⏳",
                color=discord.Color.green()
            )
            embed.add_field(name="🔥 EiTCHAAAAAAA", value=f"🏆 {eitcha_count} jogadores ficaram mais de 1h!", inline=False)
            embed.add_field(name="😴 TCHUDU BEM.... (;-;)", value=f"💤 {tchudu_bem_count} passaram menos de 1h.", inline=False)
            embed.set_footer(text="📅 Estatísticas atualizadas diariamente às 23:00.")
            await channel.send(embed=embed)

@tasks.loop(hours=24)
async def award_tchudu_master() -> None:
    now = datetime.now()
    if now.day != 1:
        return
    for guild_id, settings in server_settings.items():
        if guild_id not in user_data:
            continue
        time_data = { uid: t for uid, t in user_data[guild_id].items() if uid.startswith("time_") }
        if not time_data:
            continue
        min_user = min(time_data, key=time_data.get, default=None)
        if not min_user:
            continue
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
        for m in guild.members:
            if role in m.roles:
                await m.remove_roles(role)
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

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    guild_id = str(member.guild.id)
    user_id = str(member.id)
    if after.channel and not before.channel:
        user_data.setdefault(guild_id, {})[f"join_{user_id}"] = datetime.utcnow().timestamp()
    elif before.channel and not after.channel:
        join_key = f"join_{user_id}"
        join_time = user_data[guild_id].pop(join_key, None)
        if join_time:
            duration = datetime.utcnow().timestamp() - join_time
            time_key = f"time_{user_id}"
            total_time = user_data[guild_id].get(time_key, 0) + duration
            user_data[guild_id][time_key] = total_time
            xp_ganho = int(duration // 600) * 10
            xp_key = f"xp_{user_id}"
            xp_atual = user_data[guild_id].get(xp_key, 0) + xp_ganho
            user_data[guild_id][xp_key] = xp_atual
            nivel_key = f"nivel_{user_id}"
            nivel_anterior = user_data[guild_id].get(nivel_key, 0)
            nivel_atual = xp_atual // 100
            if nivel_atual > nivel_anterior:
                user_data[guild_id][nivel_key] = nivel_atual
                embed = discord.Embed(
                    title="🎉 Subiu de nível!",
                    description=f"Parabéns {member.mention}, você agora é **Nível {nivel_atual}**!",
                    color=discord.Color.green()
                )
                channel = get_channel(bot, guild_id)
                if channel:
                    await channel.send(embed=embed)
            save_user_data(user_data)

# ============================================================
#                       INICIAR O BOT
# ============================================================

if TOKEN:
    bot.run(TOKEN)
else:
    print("Erro: DISCORD_TOKEN não foi encontrado no .env")
