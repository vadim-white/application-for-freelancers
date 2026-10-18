"""TCP-форвардер для run.sh на macOS: 127.0.0.1:<порт> внутри контейнера -> <хост>:<порт>.

Docker Desktop пускает из контейнера к портам хоста только через host.docker.internal, а стек
опубликован на 127.0.0.1. Форвардер даёт браузеру открыть тот же адрес, что и на хосте
(http://127.0.0.1:5173), — origin и CORS те же, что у пользователя.
Запуск: python forward.py <порт> <хост>.
"""

import asyncio
import sys


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()
    except OSError:  # в т. ч. ConnectionError: соединение закрыто с любой стороны
        pass


async def main(port: int, host: str) -> None:
    async def handle(client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter) -> None:
        try:
            up_r, up_w = await asyncio.open_connection(host, port)
        except OSError:
            client_w.close()
            return
        await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))
        up_w.close()
        client_w.close()

    server = await asyncio.start_server(handle, "127.0.0.1", port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), sys.argv[2]))
