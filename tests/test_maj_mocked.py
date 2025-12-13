
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
import discord
from discord.ext import commands
import sys
import json
import io
import asyncio

# Mock PARAM and environment variables
mock_param = MagicMock()
mock_param.owners = [123, 456]
mock_param.UPDATE_ROLE_ID = 101
mock_param.UPDATE_CHANNEL_ID_FR = 201
mock_param.UPDATE_CHANNEL_ID_EN = 202
mock_param.UPDATE_CHANNEL_ID_TEST = 203
mock_param.BOT_ID = 999
mock_param.checkmark = "✅"
mock_param.crossmarck = "❌"
mock_param.in_progress = "⏳"
mock_param.annonce = "📢"
mock_param.test = "🧪"
sys.modules['PARAM'] = mock_param

# Mock google.genai
sys.modules['google'] = MagicMock()
sys.modules['google.genai'] = MagicMock()
sys.modules['google.genai.types'] = MagicMock()

from cog.maj import (
    _ghost_ping,
    _send_and_publish,
    _call_gemini_api,
    _correct_french_text,
    _translate_to_english,
    _build_message,
    UpdateModal,
    UpdateManagerView,
    ManagementCog
)
import cog.maj as maj_module # to access client

@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.get_channel = MagicMock()
    return bot

@pytest.mark.asyncio
async def test_ghost_ping():
    channel = AsyncMock()
    mention_msg = AsyncMock()
    channel.send.return_value = mention_msg

    await _ghost_ping(channel)

    channel.send.assert_called_with(f"<@&{mock_param.UPDATE_ROLE_ID}>")
    mention_msg.delete.assert_called_once()

@pytest.mark.asyncio
async def test_send_and_publish_normal_channel():
    channel = AsyncMock()
    # Ensure is_news is treated as a method returning False, and NOT async
    channel.is_news = MagicMock(return_value=False)

    msg = AsyncMock()
    channel.send.return_value = msg

    await _send_and_publish(channel, "Hello")

    channel.send.assert_called_with(content="Hello", files=None)

    # msg.publish should not be called
    assert msg.publish.call_count == 0

    msg.add_reaction.assert_called_once()

@pytest.mark.asyncio
async def test_send_and_publish_news_channel():
    channel = AsyncMock()
    # Ensure is_news is treated as a method returning True, and NOT async
    channel.is_news = MagicMock(return_value=True)

    msg = AsyncMock()
    channel.send.return_value = msg

    await _send_and_publish(channel, "Hello")

    msg.publish.assert_called_once()

@pytest.mark.asyncio
async def test_call_gemini_api_success():
    mock_response = MagicMock()
    mock_response.text = '{"key": "value"}'

    # Reset mock call count
    maj_module.client.models.generate_content.reset_mock()
    maj_module.client.models.generate_content.return_value = mock_response

    result = await _call_gemini_api("prompt", {})
    assert result == {"key": "value"}

@pytest.mark.asyncio
async def test_call_gemini_api_failure_retry():
    # First call raises exception, second succeeds
    mock_response = MagicMock()
    mock_response.text = '{"success": true}'

    maj_module.client.models.generate_content.reset_mock()
    maj_module.client.models.generate_content.side_effect = [
        Exception("API Error"),
        mock_response
    ]

    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        result = await _call_gemini_api("prompt", {})
        assert result == {"success": True}
        assert maj_module.client.models.generate_content.call_count == 2

@pytest.mark.asyncio
async def test_correct_french_text():
    # Mock _call_gemini_api
    with patch('cog.maj._call_gemini_api', new_callable=AsyncMock) as mock_api:
        mock_api.return_value = {
            "corrected_title": "Titre Corrigé",
            "corrected_changes": "Changements Corrigés",
            "corrected_intro": "Intro Corrigée",
            "corrected_outro": "Outro Corrigée"
        }

        input_data = {
            "title": "Titre", "changes": "Changements", "intro": "Intro", "outro": "Outro"
        }

        result = await _correct_french_text(input_data)

        assert result["title"] == "Titre Corrigé"
        assert result["changes"] == "Changements Corrigés"

@pytest.mark.asyncio
async def test_build_message_french():
    texts = {
        "title": "My Update",
        "intro": "Intro text.",
        "changes": "& Added feature\n~ Removed bug\n£ In progress",
        "outro": "Outro text."
    }

    msg = _build_message(texts, is_english=False)

    assert "# 📢 My Update 📢" in msg
    assert "Coucou à toute la communauté !" in msg
    assert "- ✅: Added feature" in msg
    assert "- ❌: Removed bug" in msg
    assert "- ⏳: In progress" in msg
    assert "L'équipe de développement." in msg

@pytest.mark.asyncio
async def test_build_message_english():
    texts = {
        "title": "My Update",
        "intro": "Intro text.",
        "changes": "& Added feature",
        "outro": "Outro text."
    }

    msg = _build_message(texts, is_english=True)

    assert "Hello to the entire community!" in msg
    assert "- ✅ Added feature" in msg
    assert "The Development Team." in msg

@pytest.mark.asyncio
async def test_update_modal_submit():
    # Setup
    # Use AsyncMock for interaction, but we need guild attribute to be MagicMock to avoid async resolution
    interaction = AsyncMock()
    interaction.guild = MagicMock()

    test_channel = AsyncMock()
    interaction.guild.get_channel.return_value = test_channel

    followup = AsyncMock()
    interaction.original_response.return_value = followup

    # Mock open for version.json
    with patch('builtins.open', mock_open(read_data='{"version": "1.0.0"}')) as mock_file, \
         patch('json.dump') as mock_json_dump, \
         patch('cog.maj._correct_french_text', new_callable=AsyncMock) as mock_correct, \
         patch('cog.maj._translate_to_english', new_callable=AsyncMock) as mock_translate:

        mock_correct.return_value = {"title": "FR Title", "changes": "FR Changes", "intro": "", "outro": ""}
        mock_translate.return_value = {"title": "EN Title", "changes": "EN Changes", "intro": "", "outro": ""}

        modal = UpdateModal(attachments=[])

        # Manually set values on the instance
        modal.update_name._value = "v1.1.0"
        modal.version_number._value = "1.1.0"
        modal.changes._value = "Changes"
        modal.intro_message._value = ""
        modal.outro_message._value = ""

        # Act
        await modal.on_submit(interaction)

        # Assert
        interaction.response.send_message.assert_called_once()
        mock_json_dump.assert_called() # Version saved
        mock_correct.assert_called_once()
        mock_translate.assert_called_once()

        # Verify test channel sending
        interaction.guild.get_channel.assert_called_with(mock_param.UPDATE_CHANNEL_ID_TEST)
        test_channel.send.assert_called_once()
        args, kwargs = test_channel.send.call_args
        assert kwargs['view'] is not None
        assert isinstance(kwargs['view'], UpdateManagerView)

@pytest.mark.asyncio
async def test_update_manager_view_send_prod():
    fr_texts = {"title": "FR", "changes": "C", "intro": "I", "outro": "O"}
    en_texts = {"title": "EN", "changes": "C", "intro": "I", "outro": "O"}
    interaction = AsyncMock()

    view = UpdateManagerView(fr_texts, en_texts, [], interaction)

    fr_channel = MagicMock()
    fr_channel.name = "fr-channel"
    en_channel = MagicMock()
    en_channel.name = "en-channel"

    def get_channel(id):
        if id == 201: return fr_channel
        if id == 202: return en_channel
        return None

    # We need interaction.guild to be a MagicMock to allow side_effect on get_channel synchronously
    interaction.guild = MagicMock()
    interaction.guild.get_channel.side_effect = get_channel

    # Mock _send_and_publish and _ghost_ping
    with patch('cog.maj._send_and_publish', new_callable=AsyncMock) as mock_send, \
         patch('cog.maj._ghost_ping', new_callable=AsyncMock) as mock_ping:

        # Mock button click
        callback = view.send_prod.callback
        await callback(interaction)

        assert mock_send.call_count == 2 # FR and EN
        assert mock_ping.call_count == 2 # FR and EN
        interaction.followup.send.assert_called_with("✅ Mise à jour déployée en production !", ephemeral=True)

@pytest.mark.asyncio
async def test_management_cog_patch_note(mock_bot):
    cog = ManagementCog(mock_bot)
    interaction = AsyncMock()

    with patch('builtins.open', mock_open(read_data='{"version": "1.0.0"}')), \
         patch('json.load', return_value={"version": "1.0.0"}), \
         patch('json.dump'), \
         patch('cog.maj._send_and_publish', new_callable=AsyncMock) as mock_send, \
         patch('cog.maj._ghost_ping', new_callable=AsyncMock) as mock_ping:

        await cog.patch_note_command.callback(cog, interaction)

        mock_send.call_count == 2
        mock_ping.call_count == 2
        interaction.followup.send.assert_called_with("✅ Patch **1.0.1** annoncé.", ephemeral=True)
