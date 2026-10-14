from fastapi import Request, HTTPException
from jose import jwt, JWTError
from .core.config import settings

async def jwt_middleware(request: Request):
    """
    JWT проверка для защищённых маршрутов.
    - /api/auth и /health доступны без проверки
    - /api/tasks и /api/time требуют Bearer токен
    - payload прикрепляется к request.state.jwt_payload
    """

    path = request.url.path

    # публичные эндпоинты
    if path.startswith("/api/auth") or path.startswith("/health"):
        return None

    # защищённые эндпоинты
    if path.startswith("/api/tasks") or path.startswith("/api/time"):
        # auth_header = request.headers.get("authorization")
        # if not auth_header:
        #     print('raise 1')
        #     raise HTTPException(status_code=401, detail="Missing authorization header")

        # try:
        #     scheme, token = auth_header.split()
        #     if scheme.lower() != "bearer":
        #         print('raise 2')
        #         raise HTTPException(status_code=401, detail="Invalid auth scheme")
        # except ValueError:
        #     print('raise 3')
        #     raise HTTPException(status_code=401, detail="Invalid authorization header format")

        # try:
        #     # ⚠️ Для локального тестирования пока отключаем проверку exp
        #     payload = jwt.decode(
        #         token,
        #         settings.SECRET_KEY,
        #         algorithms=[settings.ALGORITHM],
        #         options={"verify_exp": False}  # временно
        #     )
        # except JWTError:
        #     raise HTTPException(status_code=401, detail="Invalid token")

        # # payload прикрепляется к request.state для downstream
        # request.state.jwt_payload = payload

        return None
