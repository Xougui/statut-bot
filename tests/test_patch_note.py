
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
import discord
from discord import ui
import json
import os

# Ensure env var is set for module import
os.environ["GEMINI_API"] = "fake_key"

from cog.patch_note import PatchNoteCog, PatchNoteModal, PatchNoteView

@pytest.mark.asyncio
async def test_patch_note_command_registration():
    bot = AsyncMock()
    cog = PatchNoteCog(bot)
    assert hasattr(cog, "patch_note")
    assert cog.patch_note.name == "patch-note"

@pytest.mark.asyncio
async def test_patch_note_modal_submit():
    # Mock interaction
    interaction = AsyncMock()
    interaction.response = AsyncMock()
    interaction.original_response = AsyncMock()

    # get_channel is synchronous, returns a Channel (AsyncMock in this case)
    interaction.guild.get_channel = MagicMock(return_value=AsyncMock())

    # Mock attachment data
    attachment_data = ("image.png", b"fake_image_data")

    # Initialize Modal
    modal = PatchNoteModal(attachment_data)

    # Mock inputs
    modal.version_input = MagicMock(value="1.0.1")
    modal.message_input = MagicMock(value="New patch features")

    # Mock Gemini helper
    with patch("cog.patch_note._process_patch_text", new_callable=AsyncMock) as mock_process:
        mock_process.return_value = ("Corrigé FR", "Translated EN")

        with patch("cog.patch_note._split_message", return_value=["msg1"]):
             with patch("cog.patch_note.PARAM") as mock_param:
                mock_param.UPDATE_CHANNEL_ID_TEST = 123

                await modal.on_submit(interaction)

    # Verify flow
    interaction.response.send_message.assert_called()
    mock_process.assert_called_with("New patch features")
    # Verify preview sent to test channel
    interaction.guild.get_channel.assert_called_with(123)
    channel = interaction.guild.get_channel.return_value
    channel.send.assert_called()

@pytest.mark.asyncio
async def test_patch_note_view_send_prod():
    # Mock interaction
    interaction = AsyncMock()
    interaction.guild.get_channel = MagicMock(return_value=AsyncMock())

    view = PatchNoteView(
        fr_message="Message FR",
        en_message="Message EN",
        new_version="1.0.1",
        file_data=("image.png", b"data"),
        original_interaction=interaction
    )

    # Mock file operations and helpers
    with patch("builtins.open", mock_open()), \
         patch("json.dump"), \
         patch("cog.patch_note._send_and_publish", new_callable=AsyncMock) as mock_send_pub, \
         patch("cog.patch_note._ghost_ping", new_callable=AsyncMock), \
         patch("cog.patch_note.PARAM") as mock_param:

        mock_param.UPDATE_CHANNEL_ID_FR = 111
        mock_param.UPDATE_CHANNEL_ID_EN = 222

        # Simulate button click
        button = MagicMock(spec=ui.Button)

        # Invoke the callback directly using the class method to avoid binding issues
        # The callback signature is (self, interaction, button)
        # PatchNoteView.send_prod is a _ViewCallback. It works by accessing its own .callback
        # But wait, if I access it via Class it might be unbound.
        # Let's try calling it on the instance `view.send_prod` but passing arguments correctly.
        # Actually, `view.send_prod` is the decorated thing.
        # The discord.py ui.button decorator returns a _ViewCallback descriptor.
        # When accessed from instance, it returns the ItemCallback.
        # If we access the function itself:

        # We can just manually trigger the logic by calling the method IF it wasn't decorated, but it is.
        # The decorated method is stored in `callback` attribute of the item.

        # In testing, the easiest way is often to extract the original function if possible,
        # OR just rely on the fact that `view.send_prod` when called might be trying to add the item to a view or something else if not in a proper context?
        # No, `view.send_prod` as a method call on the instance should trigger the callback logic?
        # Wait, `ui.button` decorator makes it so `send_prod` is NOT the callback anymore, but an Item definition helper.

        # The actual callback is wrapped inside the Item constructed.
        # But for `View` subclasses, the methods decorated with `@ui.button` are used to construct items when `View` is instantiated.
        # The actual callback logic remains in the function, but the attribute on the class/instance is the Item factory/descriptor.

        # To test the LOGIC of the callback, we should probably access the underlying function.
        # `_ViewCallback` stores the original function in `func` or `callback`.

        # Based on previous error "AttributeError: 'function' object has no attribute 'callback'",
        # PatchNoteView.send_prod IS the function itself.
        await PatchNoteView.send_prod(view, interaction, button)

    # Verify
    # Should get channels for FR and EN
    assert interaction.guild.get_channel.call_count == 2
    assert mock_send_pub.call_count == 2 # Once for FR, once for EN
