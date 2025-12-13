# We need to import the module to patch it, but we need to mock PARAM first
# or PARAM needs to be available.
# Since PARAM is imported at top level in cog/statut.py, we need to patch it before import
# or relying on the fact that we can patch 'cog.statut.PARAM' after import if we are careful.
# However, cog/statut.py does:
# assigns BOT_ID from PARAM.BOT_ID
# So updating PARAM after import won't change BOT_ID in statut.py
# We must patch sys.modules or use patch.dict on os.environ if it used env vars, but it uses PARAM.
# Strategy: Mock PARAM completely before importing cog.statut
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

mock_param = MagicMock()
mock_param.BOT_ID = 123
mock_param.CHANNEL_ID = 456
mock_param.MESSAGE_ID = 789
mock_param.LOGS_CHANNEL_ID = 101
mock_param.ROLE_ID = 102
mock_param.offline = "🔴"
mock_param.online = "🟢"
mock_param.maintenance = "🔵"
sys.modules["PARAM"] = mock_param

from cog.statut import Status, Statut  # noqa: E402


@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    # Mock loop
    bot.loop = MagicMock()
    bot.guilds = []
    return bot


@pytest.fixture
def statut_cog(mock_bot: MagicMock) -> Statut:
    # Prevent the task from starting automatically during init
    with patch("discord.ext.tasks.Loop.start") as mock_start:
        cog = Statut(mock_bot)
        # Verify start was called
        mock_start.assert_called_once()
        return cog


def test_get_status_from_embed(statut_cog) -> None:
    embed_online = MagicMock(title="🟢・**Bot en ligne**")
    assert statut_cog._get_status_from_embed(embed_online) == Status.ONLINE

    embed_offline = MagicMock(title="🔴・**Bot hors ligne**")
    assert statut_cog._get_status_from_embed(embed_offline) == Status.OFFLINE

    embed_maintenance = MagicMock(title="🔵・**Bot en maintenance**")
    assert statut_cog._get_status_from_embed(embed_maintenance) == Status.MAINTENANCE

    assert statut_cog._get_status_from_embed(None) is None


def test_get_status_from_channel_name(statut_cog) -> None:
    channel = MagicMock()
    channel.name = "═🟢・online"
    assert statut_cog._get_status_from_channel_name(channel) == Status.ONLINE

    channel.name = "═🔴・offline"
    assert statut_cog._get_status_from_channel_name(channel) == Status.OFFLINE

    channel.name = "═🔵・maintenance"
    assert statut_cog._get_status_from_channel_name(channel) == Status.MAINTENANCE

    assert statut_cog._get_status_from_channel_name(None) is None


@pytest.mark.asyncio
async def test_update_embed(statut_cog) -> None:
    message = AsyncMock()

    # Test ONLINE
    assert await statut_cog._update_embed(message, Status.ONLINE) is True
    assert message.edit.call_args[1]["embed"].color.value == 0x00BF63

    # Test OFFLINE
    assert await statut_cog._update_embed(message, Status.OFFLINE) is True
    assert message.edit.call_args[1]["embed"].color.value == 0xFF3131

    # Test Exception
    message.edit.side_effect = discord.HTTPException(
        response=MagicMock(), message="Error"
    )
    assert await statut_cog._update_embed(message, Status.ONLINE) is False


@pytest.mark.asyncio
async def test_update_channel_name(statut_cog) -> None:
    channel = AsyncMock()
    channel.name = "old_name"

    # Test Update
    assert await statut_cog._update_channel_name(channel, Status.ONLINE) is True
    channel.edit.assert_called_with(name="═🟢・online")

    # Test No Change Needed
    channel.name = "═🟢・online"
    channel.edit.reset_mock()
    assert await statut_cog._update_channel_name(channel, Status.ONLINE) is True
    channel.edit.assert_not_called()

    # Test Rate Limit (429) - simulated with side effect
    # We need to control side_effect to eventually succeed or we mock sleep

    # Test Forbidden (403)
    channel.name = "old_name"
    response = MagicMock()
    response.status = 403
    channel.edit.side_effect = discord.HTTPException(
        response=response, message="Forbidden"
    )
    assert await statut_cog._update_channel_name(channel, Status.ONLINE) is False


@pytest.mark.asyncio
async def test_update_status_logic_manual(statut_cog) -> None:
    interaction = AsyncMock()
    interaction.edit_original_response = AsyncMock()

    # Mock methods
    statut_cog._update_embed = AsyncMock(return_value=True)
    statut_cog._update_channel_name = AsyncMock(return_value=True)
    statut_cog._send_log = AsyncMock(return_value=True)
    statut_cog._send_ping = AsyncMock(return_value=True)

    # Mock fetch_message
    channel = AsyncMock()
    channel.name = "═🔴・offline"
    statut_cog.bot.get_channel.return_value = channel

    message = AsyncMock()
    message.embeds = [MagicMock(title="🔴・**Bot hors ligne**")]
    channel.fetch_message.return_value = message

    statut_cog._last_known_status = Status.OFFLINE

    # Run
    await statut_cog._update_status_logic(
        interaction=interaction, forced_status=Status.ONLINE
    )

    statut_cog._update_embed.assert_called_once()
    statut_cog._update_channel_name.assert_called_once()
    statut_cog._send_log.assert_called_once()
    statut_cog._send_ping.assert_called_once()
    assert statut_cog._last_known_status == Status.ONLINE


@pytest.mark.asyncio
async def test_update_status_logic_automatic_no_change(statut_cog) -> None:
    # Setup target bot is online
    target_bot = MagicMock()
    target_bot.status = discord.Status.online
    guild = MagicMock()
    guild.get_member.return_value = target_bot
    statut_cog.bot.guilds = [guild]

    # Setup current status is online
    channel = AsyncMock()
    channel.name = "═🟢・online"
    statut_cog.bot.get_channel.return_value = channel
    message = AsyncMock()
    message.embeds = [MagicMock(title="🟢・**Bot en ligne**")]
    channel.fetch_message.return_value = message

    statut_cog._last_known_status = Status.ONLINE

    statut_cog._update_embed = AsyncMock()
    statut_cog._update_channel_name = AsyncMock()

    await statut_cog._update_status_logic()

    statut_cog._update_embed.assert_not_called()
    statut_cog._update_channel_name.assert_not_called()


@pytest.mark.asyncio
async def test_update_status_logic_automatic_change(statut_cog) -> None:
    # Setup target bot is OFFLINE
    target_bot = MagicMock()
    target_bot.status = discord.Status.offline
    guild = MagicMock()
    guild.get_member.return_value = target_bot
    statut_cog.bot.guilds = [guild]

    # Setup current status is ONLINE
    channel = AsyncMock()
    channel.name = "═🟢・online"
    statut_cog.bot.get_channel.return_value = channel
    message = AsyncMock()
    message.embeds = [MagicMock(title="🟢・**Bot en ligne**")]
    channel.fetch_message.return_value = message

    statut_cog._last_known_status = Status.ONLINE

    statut_cog._update_embed = AsyncMock(return_value=True)
    statut_cog._update_channel_name = AsyncMock(return_value=True)
    statut_cog._send_log = AsyncMock(return_value=True)
    statut_cog._send_ping = AsyncMock(return_value=True)

    await statut_cog._update_status_logic()

    statut_cog._update_embed.assert_called_once()
    statut_cog._update_channel_name.assert_called_once()
    statut_cog._send_log.assert_called_once()
    statut_cog._send_ping.assert_called_once()
    assert statut_cog._last_known_status == Status.OFFLINE
