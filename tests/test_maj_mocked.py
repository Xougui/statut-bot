import os
import sys
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

# Mock environment variable BEFORE module import to avoid logging warning
os.environ["GEMINI_API"] = "fake_key"

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
mock_param.GEMINI_MODEL = "gemini-1.5-flash"
sys.modules["PARAM"] = mock_param

# Mock google.genai
sys.modules["google"] = MagicMock()
sys.modules["google.genai"] = MagicMock()
sys.modules["google.genai.types"] = MagicMock()

import cog.maj as maj_module  # to access client  # noqa: E402
from cog.maj import (  # noqa: E402
    UpdateManagerView,
    UpdateModal,
    _build_message,
    _call_gemini_api,
    _correct_french_text,
    _send_and_publish,
    _send_ping,
)

# Explicitly set the client mock to ensure it's not None
# The module import might have set it to None if import happened before env var or mocking
if maj_module.client is None:
    maj_module.client = MagicMock()


@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.get_channel = MagicMock()
    return bot


@pytest.mark.asyncio
async def test_send_ping() -> None:
    channel = AsyncMock()

    await _send_ping(channel)

    channel.send.assert_called_with(f"<@&{mock_param.UPDATE_ROLE_ID}>")


@pytest.mark.asyncio
async def test_send_and_publish_normal_channel() -> None:
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
async def test_send_and_publish_news_channel() -> None:
    channel = AsyncMock()
    # Ensure is_news is treated as a method returning True, and NOT async
    channel.is_news = MagicMock(return_value=True)

    msg = AsyncMock()
    channel.send.return_value = msg

    await _send_and_publish(channel, "Hello")

    msg.publish.assert_called_once()


@pytest.mark.asyncio
async def test_call_gemini_api_success() -> None:
    mock_response = MagicMock()
    mock_response.text = '{"key": "value"}'

    # Ensure client is mocked
    maj_module.client = MagicMock()

    # Reset mock call count
    maj_module.client.models.generate_content.reset_mock()
    maj_module.client.models.generate_content.return_value = mock_response

    result = await _call_gemini_api("prompt", {})
    assert result == {"key": "value"}


@pytest.mark.asyncio
async def test_call_gemini_api_failure_retry() -> None:
    # First call raises exception, second succeeds
    mock_response = MagicMock()
    mock_response.text = '{"success": true}'

    maj_module.client = MagicMock()

    maj_module.client.models.generate_content.reset_mock()
    maj_module.client.models.generate_content.side_effect = [
        Exception("API Error"),
        mock_response,
    ]

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await _call_gemini_api("prompt", {})
        assert result == {"success": True}
        assert maj_module.client.models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_correct_french_text() -> None:
    # Mock _call_gemini_api
    with patch("cog.maj._call_gemini_api", new_callable=AsyncMock) as mock_api:
        mock_api.return_value = {
            "corrected_title": "Titre Corrigé",
            "corrected_changes": "Changements Corrigés",
            "corrected_intro": "Intro Corrigée",
            "corrected_outro": "Outro Corrigée",
        }

        input_data = {
            "title": "Titre",
            "changes": "Changements",
            "intro": "Intro",
            "outro": "Outro",
        }

        result = await _correct_french_text(input_data)

        assert result["title"] == "Titre Corrigé"
        assert result["changes"] == "Changements Corrigés"


@pytest.mark.asyncio
async def test_build_message_french() -> None:
    texts = {
        "title": "My Update",
        "intro": "Intro text.",
        "changes": "& Added feature\n~ Removed bug\n£ In progress",
        "outro": "Outro text.",
    }

    msg = _build_message(texts, is_english=False)

    assert "# 📢 My Update 📢" in msg
    assert "<@999> a reçu une mise à jour ! 🧪" in msg
    assert "- ✅: Added feature" in msg
    assert "- ❌: Removed bug" in msg
    assert "- ⏳: In progress" in msg
    assert "L'équipe de développement." in msg


@pytest.mark.asyncio
async def test_build_message_english() -> None:
    texts = {
        "title": "My Update",
        "intro": "Intro text.",
        "changes": "& Added feature",
        "outro": "Outro text.",
    }

    msg = _build_message(texts, is_english=True)

    assert "<@999> received an update ! 🧪" in msg
    assert "- ✅ Added feature" in msg
    assert "The Development Team." in msg


@pytest.mark.asyncio
async def test_update_modal_submit() -> None:
    # Setup
    # Use AsyncMock for interaction, but we need guild attribute to be MagicMock to avoid async resolution
    interaction = AsyncMock()
    interaction.guild = MagicMock()

    test_channel = AsyncMock()
    interaction.guild.get_channel.return_value = test_channel

    followup = AsyncMock()
    interaction.original_response.return_value = followup

    # Mock open for version.json
    with (
        patch("builtins.open", mock_open(read_data='{"version": "1.0.0"}')),
        patch("json.dump") as mock_json_dump,
        patch("cog.maj._correct_french_text", new_callable=AsyncMock) as mock_correct,
        patch(
            "cog.maj._translate_to_english", new_callable=AsyncMock
        ) as mock_translate,
    ):
        mock_correct.return_value = {
            "title": "FR Title",
            "changes": "FR Changes",
            "intro": "",
            "outro": "",
        }
        mock_translate.return_value = {
            "title": "EN Title",
            "changes": "EN Changes",
            "intro": "",
            "outro": "",
        }

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
        mock_json_dump.assert_called()  # Version saved
        mock_correct.assert_called_once()
        mock_translate.assert_called_once()

        # Verify test channel sending
        interaction.guild.get_channel.assert_called_with(
            mock_param.UPDATE_CHANNEL_ID_TEST
        )
        test_channel.send.assert_called_once()
        _args, kwargs = test_channel.send.call_args
        assert kwargs["view"] is not None
        assert isinstance(kwargs["view"], UpdateManagerView)


@pytest.mark.asyncio
async def test_update_manager_view_send_prod() -> None:
    fr_texts = {"title": "FR", "changes": "C", "intro": "I", "outro": "O"}
    en_texts = {"title": "EN", "changes": "C", "intro": "I", "outro": "O"}
    interaction = AsyncMock()

    view = UpdateManagerView(fr_texts, en_texts, [], interaction)

    fr_channel = MagicMock()
    fr_channel.name = "fr-channel"
    en_channel = MagicMock()
    en_channel.name = "en-channel"

    def get_channel(id) -> MagicMock | None:
        if id == 201:
            return fr_channel
        if id == 202:
            return en_channel
        return None

    # We need interaction.guild to be a MagicMock to allow side_effect on get_channel synchronously
    interaction.guild = MagicMock()
    interaction.guild.get_channel.side_effect = get_channel

    # Mock _send_and_publish and _ghost_ping
    with (
        patch("cog.maj._send_and_publish", new_callable=AsyncMock) as mock_send,
        patch("cog.maj._send_ping", new_callable=AsyncMock) as mock_ping,
    ):
        # Mock button click
        # Access the callback. Since we're in a test and it's a bound method on the view instance,
        # but decorated by ui.button, accessing view.send_prod returns the Item (Button).
        # We need the callback.
        # But wait, in the previous fix for patch_note, I used `PatchNoteView.send_prod.callback`.
        # Here `UpdateManagerView.send_prod.callback` should work, but I need to bind it or pass self.

        # However, `view.send_prod` (instance) might already be the Button object.
        # Button objects store their callback.

        # In this specific test file (which existed before), `view.send_prod` was seemingly working as a function?
        # Or maybe the test was failing before but I didn't see it (I only saw errors related to client).

        # Let's try to invoke it correctly.
        # If view.send_prod is a Button, we call its callback.

        if hasattr(view.send_prod, "callback"):
            # It is an Item
            await view.send_prod.callback(interaction)
        else:
            # It is a function (unlikely with @ui.button)
            await view.send_prod(interaction)

        assert mock_send.call_count == 2  # FR and EN
        assert mock_ping.call_count == 2  # FR and EN
        interaction.followup.send.assert_called_with(
            "✅ Mise à jour déployée en production !", ephemeral=True
        )
