
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import sys
import asyncio

# Mock PARAM and environment variables
mock_param = MagicMock()
mock_param.couleur = 0x123456
mock_param.owners = [123, 456]
sys.modules['PARAM'] = mock_param

# Mock pydactyl
sys.modules['pydactyl'] = MagicMock()
sys.modules['pydactyl.api_client'] = MagicMock()

from cog.panel import BotControl, ServerControlView, ServerDropdown, SERVERS

@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.get_channel = MagicMock()
    bot.add_view = MagicMock()
    return bot

@pytest.fixture
def mock_dependencies():
    with patch('cog.panel.PterodactylClient') as mock_client_cls, \
         patch('cog.panel.tasks.loop') as mock_loop, \
         patch('os.getenv') as mock_getenv:

        # Setup mock environment
        mock_getenv.side_effect = lambda key: "fake_key" if key in ["API_XOUXOU", "API_KATA"] else None

        # Setup mock client instance
        mock_client_instance = MagicMock()
        mock_client_cls.return_value = mock_client_instance

        # Setup loop mock
        mock_loop_instance = MagicMock()
        mock_loop.return_value = lambda func: mock_loop_instance
        mock_loop_instance.start = MagicMock()

        yield {
            'client_cls': mock_client_cls,
            'loop': mock_loop_instance,
            'getenv': mock_getenv,
            'client_instance': mock_client_instance
        }

@pytest.mark.asyncio
async def test_server_dropdown_callback(mock_bot, mock_dependencies):
    cog = BotControl(mock_bot)
    cog.check_server_status = mock_dependencies['loop']

    dropdown = ServerDropdown(cog)
    interaction = AsyncMock()
    dropdown._values = ["Lyxios"]

    cog.update_embed = AsyncMock()

    await dropdown.callback(interaction)

    assert cog.selected_server == "Lyxios"
    interaction.response.defer.assert_called_once()
    cog.update_embed.assert_called_once()

@pytest.mark.asyncio
async def test_start_button_callback(mock_bot, mock_dependencies):
    cog = BotControl(mock_bot)
    cog.check_server_status = mock_dependencies['loop']

    view = ServerControlView(cog)
    interaction = AsyncMock()
    button = MagicMock()

    cog.selected_server = "Lyxios"
    # Ensure client exists for this server
    mock_client = MagicMock()
    cog.pterodactyl_clients["xouxou_hosting"] = mock_client

    cog.update_embed = AsyncMock()

    # Call the callback stored in the button object
    # The callback is wrapped in a _ViewCallback which takes only interaction
    await view.start_button_callback.callback(interaction)

    interaction.response.defer.assert_called_once()
    mock_client.client.servers.send_power_action.assert_called_with("0fc94e2a", "start")
    interaction.followup.send.assert_called_with(f"✅ Lyxios démarré avec succès.", ephemeral=True)
    cog.update_embed.assert_called_once()

@pytest.mark.asyncio
async def test_restart_button_callback(mock_bot, mock_dependencies):
    cog = BotControl(mock_bot)
    cog.check_server_status = mock_dependencies['loop']

    view = ServerControlView(cog)
    interaction = AsyncMock()
    button = MagicMock()

    cog.selected_server = "Lyxios"
    mock_client = MagicMock()
    cog.pterodactyl_clients["xouxou_hosting"] = mock_client
    cog.update_embed = AsyncMock()

    callback_func = view.restart_button_callback.callback
    await callback_func(interaction)

    mock_client.client.servers.send_power_action.assert_called_with("0fc94e2a", "restart")
    interaction.followup.send.assert_called_with(f"🔄 Lyxios redémarré avec succès.", ephemeral=True)

@pytest.mark.asyncio
async def test_stop_button_callback_normal(mock_bot, mock_dependencies):
    cog = BotControl(mock_bot)
    cog.check_server_status = mock_dependencies['loop']

    view = ServerControlView(cog)
    interaction = AsyncMock()
    button = MagicMock()

    cog.selected_server = "Lyxios"
    mock_client = MagicMock()
    cog.pterodactyl_clients["xouxou_hosting"] = mock_client
    cog.update_embed = AsyncMock()

    callback_func = view.stop_button_callback.callback
    await callback_func(interaction)

    mock_client.client.servers.send_power_action.assert_called_with("0fc94e2a", "stop")
    interaction.followup.send.assert_called_with(f"🛑 Commande d'arrêt envoyée à Lyxios.", ephemeral=True)

@pytest.mark.asyncio
async def test_stop_button_callback_self(mock_bot, mock_dependencies):
    cog = BotControl(mock_bot)
    cog.check_server_status = mock_dependencies['loop']

    view = ServerControlView(cog)
    interaction = AsyncMock()
    button = MagicMock()

    cog.selected_server = "Lyxios Manage"
    mock_client = MagicMock()
    cog.pterodactyl_clients["katabump_hosting"] = mock_client

    cog.embed_message = AsyncMock()

    callback_func = view.stop_button_callback.callback

    # We mock asyncio.sleep to speed up test
    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        await callback_func(interaction)

        interaction.followup.send.assert_called_with(f"🛑 Lyxios Manage (le bot) va s'arrêter dans 3 secondes. L'embed sera mis à jour en 'Hors ligne'.", ephemeral=True)

        # Verify pre-shutdown embed update
        cog.embed_message.edit.assert_called_once()
        args, kwargs = cog.embed_message.edit.call_args
        assert kwargs['embed'].description.startswith("Le serveur **Lyxios Manage** est en cours d'arrêt")

        mock_sleep.assert_called_with(3)
        mock_client.client.servers.send_power_action.assert_called_with("063a03b1", "stop")

@pytest.mark.asyncio
async def test_update_embed(mock_bot, mock_dependencies):
    cog = BotControl(mock_bot)
    cog.check_server_status = mock_dependencies['loop']

    cog.selected_server = "Lyxios"
    mock_client = MagicMock()
    cog.pterodactyl_clients["xouxou_hosting"] = mock_client

    # Mock server info and stats
    mock_client.client.servers.get_server.return_value = {"node": "Test Node"}
    mock_client.client.servers.get_server_utilization.return_value = {
        "current_state": "running",
        "resources": {
            "cpu_absolute": 50.0,
            "memory_bytes": 1024 * 1024 * 512, # 512 Mo
            "disk_bytes": 1024 * 1024 * 1024 # 1024 Mo
        }
    }

    channel = AsyncMock()
    cog.bot.get_channel.return_value = channel
    message = AsyncMock()
    cog.embed_message = message

    await cog.update_embed()

    message.edit.assert_called_once()
    args, kwargs = message.edit.call_args
    embed = kwargs['embed']

    assert embed.title == "🔧 Système de Contrôle des Bots"
    assert embed.color.value == discord.Color.green().value

    # Check fields
    fields = {f.name: f.value for f in embed.fields}
    assert fields["🔹 Bot sélectionné :"] == "Lyxios"
    assert fields["📡 Statut du serveur :"] == "🟢 En ligne"
    assert fields["🖥️ Utilisation CPU :"] == "50.0%"
    assert fields["📂 Utilisation RAM :"] == "512.0 Mo"

@pytest.mark.asyncio
async def test_update_embed_error(mock_bot, mock_dependencies):
    cog = BotControl(mock_bot)
    cog.check_server_status = mock_dependencies['loop']

    cog.selected_server = "Lyxios"
    mock_client = MagicMock()
    cog.pterodactyl_clients["xouxou_hosting"] = mock_client

    # Mock Exception
    mock_client.client.servers.get_server.side_effect = Exception("API Error")

    channel = AsyncMock()
    cog.bot.get_channel.return_value = channel
    message = AsyncMock()
    cog.embed_message = message

    await cog.update_embed()

    message.edit.assert_called_once()
    args, kwargs = message.edit.call_args
    embed = kwargs['embed']

    assert embed.color.value == discord.Color.red().value
    fields = {f.name: f.value for f in embed.fields}
    assert fields["📡 Statut du serveur :"] == "🔴 Erreur Interne"
    assert "Une erreur est survenue" in fields["⚠️ Erreur :"]

@pytest.mark.asyncio
async def test_on_ready(mock_bot, mock_dependencies):
    cog = BotControl(mock_bot)
    cog.check_server_status = mock_dependencies['loop']

    channel = AsyncMock()
    cog.bot.get_channel.return_value = channel

    # Mock message loading failure (None ID)
    cog.message_id = None

    cog.check_server_status.start = MagicMock()
    cog.update_embed = AsyncMock()

    await cog.on_ready()

    cog.bot.get_channel.assert_called_with(cog.channel_id)
    cog.bot.add_view.assert_called_once()
    cog.update_embed.assert_called_once_with(first_time=True)
    cog.check_server_status.start.assert_called_once()
