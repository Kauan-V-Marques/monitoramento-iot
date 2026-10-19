"""Sobe a plataforma: python -m plataforma [--porta 8000]"""

import argparse
import asyncio
import sys

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--porta", type=int, default=8000)
    args = parser.parse_args()

    # O psycopg assíncrono não funciona com o loop padrão do Windows (Proactor).
    # loop="none" faz o uvicorn usar o loop criado aqui em vez de escolher o dele.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    config = uvicorn.Config(
        "plataforma.app:criar_app", factory=True, host=args.host, port=args.porta, loop="none"
    )
    asyncio.run(uvicorn.Server(config).serve())


if __name__ == "__main__":
    main()
