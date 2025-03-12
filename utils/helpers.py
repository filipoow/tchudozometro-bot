import discord

def get_channel(bot, guild_id):
    """Retorna o canal configurado para o servidor."""
    from utils.database import load_server_settings
    server_settings = load_server_settings()
    channel_id = server_settings.get(str(guild_id), {}).get("channel_id")
    if isinstance(channel_id, int):
        return bot.get_channel(channel_id)
    return None

def format_time(seconds):
    """Formata tempo de segundos para horas e minutos."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"**{hours} horas e {minutes} minutos**"