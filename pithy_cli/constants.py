"""Constants used across Pithy CLI.

This module defines all magic numbers and configuration values used throughout
the codebase, following clean code principles by giving meaningful names to
literal values.
"""

# File size limits (in bytes)
MAX_DIFF_BYTES = 120_000
MAX_FILE_BYTES = 120_000
BINARY_DETECTION_SAMPLE_BYTES = 4_096

# LLM settings
DEFAULT_TITLE_COUNT = 3
LLM_MAX_TOKENS_STANDARD = 500
LLM_MAX_TOKENS_FILE_SUMMARY = 800
LLM_TEMPERATURE = 0.3

# Cache and security settings
DEFAULT_PASSWORD_CACHE_TTL_HOURS = 8
DEFAULT_PASSWORD_CACHE_TTL_SECONDS = 8 * 60 * 60

# Argon2 key derivation parameters
ARGON2_MEMORY_COST_KB = 32_768  # 32 MB
ARGON2_TIME_COST_ITERATIONS = 3
ARGON2_PARALLELISM = 1
ARGON2_KEY_LENGTH_BYTES = 32

# Cryptography settings
SALT_LENGTH_BYTES = 16
NONCE_LENGTH_BYTES = 12

# Git context settings
GIT_DIFF_CONTEXT_LINES = 3
