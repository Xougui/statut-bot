import sys
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

# Mock PARAM
mock_param = MagicMock()
mock_param.owners = [123]
mock_param.UPDATE_CHANNEL_ID_TEST = 203
mock_param.BOT_ID = 999
mock_param.checkmark = "✅"
mock_param.crossmarck = "❌"
mock_param.in_progress = "⏳"
mock_param.annonce = "📢"
mock_param.test = "🧪"
sys.modules["PARAM"] = mock_param

# Mock google
sys.modules["google"] = MagicMock()
sys.modules["google.genai"] = MagicMock()
sys.modules["google.genai.types"] = MagicMock()

from cog.maj import UpdateModal, _split_message  # noqa: E402


@pytest.mark.asyncio
async def test_split_message_logic() -> None:
    # Test basic splitting
    long_text = "A" * 2005
    chunks = _split_message(long_text, limit=2000)
    assert len(chunks) == 2
    assert len(chunks[0]) == 2000
    assert len(chunks[1]) == 5

    # Test split with newline
    text_newline = ("A" * 1000) + "\n" + ("B" * 1000)
    # Total 2001 chars. Should split at newline.
    # Actually 1000 'A' + 1 '\n' + 1000 'B' = 2001.
    chunks_nl = _split_message(text_newline, limit=2000)
    assert len(chunks_nl) == 2
    assert chunks_nl[0] == "A" * 1000
    assert (
        chunks_nl[1] == "B" * 1000
    )  # lstrip removes the newline if split happens there?
    # Implementation splits at the last newline before the limit.
    # The newline is stripped from the start of the next chunk.


@pytest.mark.asyncio
async def test_update_modal_split_message() -> None:
    # Setup
    interaction = AsyncMock()
    interaction.guild = MagicMock()
    test_channel = AsyncMock()
    interaction.guild.get_channel.return_value = test_channel
    followup = AsyncMock()
    interaction.original_response.return_value = followup

    # Mock mocks
    with (
        patch("builtins.open", mock_open(read_data='{"version": "1.0.0"}')),
        patch("json.dump"),
        patch("cog.maj._correct_french_text", new_callable=AsyncMock) as mock_correct,
        patch(
            "cog.maj._translate_to_english", new_callable=AsyncMock
        ) as mock_translate,
    ):
        # Create a very long string
        long_text = "A" * 1500
        mock_correct.return_value = {
            "title": "FR Title",
            "changes": long_text,
            "intro": "",
            "outro": "",
        }
        mock_translate.return_value = {
            "title": "EN Title",
            "changes": long_text,
            "intro": "",
            "outro": "",
        }

        modal = UpdateModal(attachments=[])
        modal.update_name._value = "v1.1.0"
        modal.version_number._value = "1.1.0"
        modal.changes._value = "Changes"
        modal.intro_message._value = ""
        modal.outro_message._value = ""

        # Act
        await modal.on_submit(interaction)

        # Assert
        assert test_channel.send.call_count > 1

        # Verify the last call has the view
        _, kwargs = test_channel.send.call_args
        assert kwargs.get("view") is not None

        # Verify previous calls did NOT have the view
        for call in test_channel.send.call_args_list[:-1]:
            _, k = call
            assert k.get("view") is None
