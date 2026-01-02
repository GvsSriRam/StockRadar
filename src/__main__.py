"""Module entrypoint: python -m src"""

import asyncio
from .main import main

if __name__ == "__main__":
    asyncio.run(main())