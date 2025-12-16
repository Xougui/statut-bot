import os
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import discord
from discord import ui
import pytest

# Ensure env var is set for module import
os.environ["GEMINI_API"] = "fake_key"

from cog.patch_note import PatchNoteCog, PatchNoteModal, PatchNoteView


@pytest.mark.asyncio
async def test_patch_note_command_registration() -> None:
    bot = AsyncMock()
    cog = PatchNoteCog(bot)
    assert hasattr(cog, "patch_note")
    assert cog.patch_note.name == "patch-note"


@pytest.mark.asyncio
async def test_patch_note_modal_submit() -> None:
    # Mock interaction
    interaction = AsyncMock()
    interaction.response = AsyncMock()
    interaction.original_response = AsyncMock()

    # get_channel is synchronous, returns a Channel (AsyncMock in this case)
    interaction.guild.get_channel = MagicMock(return_value=AsyncMock())

    # Mock attachment data
    attachment_data = [MagicMock(spec=discord.Attachment)]
    attachment_data[0].read = AsyncMock(return_value=b"fake_image_data")
    attachment_data[0].filename = "image.png"

    # Initialize Modal
    modal = PatchNoteModal(attachment_data)

    # Mock inputs
    modal.version_input = MagicMock(value="1.0.1")
    modal.message_input = MagicMock(value="New patch features")

    # Mock Gemini helper
    with (
        patch(
            "cog.patch_note._correct_french_text", new_callable=AsyncMock
        ) as mock_correct,
        patch(
            "cog.patch_note._translate_to_english", new_callable=AsyncMock
        ) as mock_translate,
        patch("cog.patch_note._split_message", return_value=["msg1"]),
        patch("cog.patch_note.PARAM") as mock_param,
    ):
        mock_correct.return_value = {"changes": "Corrigé FR"}
        mock_translate.return_value = {"changes": "Translated EN"}
        mock_param.UPDATE_CHANNEL_ID_TEST = 123

        await modal.on_submit(interaction)

    # Verify flow
    interaction.response.send_message.assert_called()
    mock_correct.assert_called_with({"changes": "New patch features"})
    # Verify preview sent to test channel
    interaction.guild.get_channel.assert_called_with(123)
    channel = interaction.guild.get_channel.return_value
    channel.send.assert_called()


@pytest.mark.asyncio
async def test_patch_note_view_send_prod() -> None:
    # Mock interaction
    interaction = AsyncMock()
    interaction.guild.get_channel = MagicMock(return_value=AsyncMock())

    view = PatchNoteView(
        fr_texts={"changes": "Message FR"},
        en_texts={"changes": "Message EN"},
        new_version="1.0.1",
        files_data=[("image.png", b"data")],
        original_interaction=interaction,
    )

    # Mock file operations and helpers
    with (
        patch("builtins.open", mock_open()),
        patch("json.dump"),
        patch(
            "cog.patch_note._send_and_publish", new_callable=AsyncMock
        ) as mock_send_pub,
        patch("cog.patch_note._ghost_ping", new_callable=AsyncMock),
        patch("cog.patch_note.PARAM") as mock_param,
    ):
        mock_param.UPDATE_CHANNEL_ID_FR = 111
        mock_param.UPDATE_CHANNEL_ID_EN = 222

        # Simulate button click
        button = MagicMock(spec=ui.Button)

        # Try calling the callback via the descriptor's callback attribute on the class
        # If PatchNoteView.send_prod is a _ViewCallback, it has a .callback attribute which is the function.
        # If PatchNoteView.send_prod is the function itself (unlikely with @ui.button), we call it.
        # The previous error "AttributeError: 'function' object has no attribute 'callback'" suggests
        # that PatchNoteView.send_prod MIGHT be the function in this environment?

        if hasattr(PatchNoteView.send_prod, "callback"):
            await PatchNoteView.send_prod.callback(view, interaction, button)
        else:
            # It's just the function?
            await PatchNoteView.send_prod(view, interaction, button)

    # Verify
    # Should get channels for FR and EN
    assert interaction.guild.get_channel.call_count == 2
    assert mock_send_pub.call_count == 2  # Once for FR, once for EN
