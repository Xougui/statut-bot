import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

# To allow the test to run from the root directory, we need to add the root to the path
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from cog.statut import Statut
import PARAM

class TestStatutCog(unittest.TestCase):

    # We patch the start method of the Loop class from discord.ext.tasks.
    # This prevents the task from starting automatically during cog initialization.
    @patch('discord.ext.tasks.Loop.start')
    def setUp(self, mock_loop_start):
        """Set up a fresh instance of the cog for each test."""
        # Mock the bot object
        self.bot = MagicMock()
        self.bot.wait_until_ready = AsyncMock()
        self.bot.get_channel.return_value = MagicMock()

        # Now, when Statut is instantiated, self.check_bot_status.start() will
        # call the mock object instead of the real implementation.
        self.cog = Statut(self.bot)

    def test_ping_uses_correct_role_id(self):
        """
        Tests if the _send_and_delete_ping method uses the PING_ROLE_ID from the config.
        """
        # Get the role ID from the PARAM file
        expected_role_id = PARAM.ROLE_ID

        # Mock the channel object and its methods
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        mock_channel.name = "test-channel"

        # Mock the ping message and its delete method
        mock_ping_message = MagicMock()
        mock_ping_message.delete = AsyncMock()
        mock_channel.send.return_value = mock_ping_message

        status_text = "online"
        expected_content = f"<@&{expected_role_id}> Le bot vient de passer {status_text}."

        # Run the async method
        asyncio.run(self.cog._send_and_delete_ping(mock_channel, status_text))

        # Assert that channel.send was called once with the correct content
        mock_channel.send.assert_called_once_with(content=expected_content)

        # Assert that the sent message was deleted
        mock_ping_message.delete.assert_called_once()

if __name__ == '__main__':
    unittest.main()
