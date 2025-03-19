import os

# Environment settings
VALID_ENVIRONMENTS = ["dev", "prod", "update"]
ENVIRONMENT = os.getenv("DEPLOY_MODE", "prod")

# Validate environment
if ENVIRONMENT not in VALID_ENVIRONMENTS:
    raise ValueError(f"Invalid environment: {ENVIRONMENT}. Must be one of {VALID_ENVIRONMENTS}")

# Port settings
PORT = int(os.getenv("PORT", "8080"))

# API settings
API_SETTINGS = {
    "dev": {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "debug": False
    },
    "prod": {
        "docs_url": None,
        "redoc_url": None,
        "debug": False
    },
    "update": {
        "docs_url": None,
        "redoc_url": None,
        "debug": False
    }
} 