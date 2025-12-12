import os
from dotenv import load_dotenv
import re
import logging

logger = logging.getLogger(__name__)

# Load .env file if present, but allow environment variables to be set on the system
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    # `override=False` ensures system environment variables take precedence
    load_dotenv(env_path, override=False)
    logger.info(f"Loaded .env file from {env_path}")
else:
    logger.info(f".env file not found at {env_path}; relying on system environment variables")

class Config:
    def __init__(self):
        # Load and validate Discord token
        self.discord_token = os.getenv("DISCORD_TOKEN")
        if self.discord_token:
            self.discord_token = self.discord_token.strip()  # Remove whitespace
            logger.debug(f"Discord token length: {len(self.discord_token)}")
            # Discord tokens are base64-like, ~59-100 chars
            if not re.match(r'^[A-Za-z0-9._-]{50,100}$', self.discord_token):
                logger.error(
                    "Invalid Discord token format (length: %d)", len(self.discord_token)
                )
                raise ValueError("Invalid Discord token format. Ensure no spaces, quotes, or invalid characters.")
        else:
            logger.error("DISCORD_TOKEN not found in environment variables")
            raise ValueError("DISCORD_TOKEN not found in environment variables")
        logger.info(
            "Successfully loaded discord token (length: %d)", len(self.discord_token)
        )

        # Load Pollinations token (OPTIONAL - bot can run without it)
        self.pollinations_token = os.getenv("POLLINATIONS_TOKEN")
        if self.pollinations_token:
            self.pollinations_token = self.pollinations_token.strip()
            logger.debug(f"Pollinations token length: {len(self.pollinations_token)}")
            if not re.match(r'^[A-Za-z0-9]{16}$', self.pollinations_token):
                logger.warning(
                    "Pollinations token format may be invalid (length: %d) - AI features may not work",
                    len(self.pollinations_token),
                )
            logger.info(
                "Successfully loaded pollinations token (length: %d)",
                len(self.pollinations_token),
            )
        else:
            logger.warning("POLLINATIONS_TOKEN not set - AI chat features disabled, Claude chat still works")
            self.pollinations_token = None

        # Bot configuration
        self.default_model = "unity"
        try:
            with open("system_instructions.txt", "r") as f:
                self.system_instructions = f.read().strip()
        except FileNotFoundError:
            logger.error("system_instructions.txt not found")
            raise FileNotFoundError("system_instructions.txt not found")
        self.api_url = f"https://text.pollinations.ai/openai?token={self.pollinations_token}" if self.pollinations_token else None
        self.models_url = "https://text.pollinations.ai/models"
        self.max_history = 20
        self.max_memories = 5
        allowed_channels_env = os.getenv("ALLOWED_CHANNELS", "")
        self.allowed_channels = {
            ch.strip() for ch in allowed_channels_env.split(",") if ch.strip()
        }
        self.code_keywords = [
            "code", "script", "program", "function", "class",
            "method", "javascript", "python", "java", "html", "css"
        ]
        self.image_keywords = [
            "image", "picture", "photo", "generate", "create", "draw", "art"
        ]
        self.memory_regex = r"\$\$ memory \$\$([\s\S]*?)\$\$ \/memory \$\$"
        self.code_block_regex = r"```(\w*)\n([\s\S]*?)\n```"
        self.url_regex = r"https?://[^\s>]+"

    def is_image_request(self, message: str) -> bool:
        return any(keyword in message.lower() for keyword in self.image_keywords)

    def is_code_request(self, message: str) -> bool:
        return any(keyword in message.lower() for keyword in self.code_keywords)

    def extract_image_prompt(self, message: str) -> str:
        return message.strip()
