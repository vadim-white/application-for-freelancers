from fastapi import Depends, Request
from .middleware import jwt_middleware

async def require_jwt(request: Request):
    # call middleware-like validator (raises HTTPException if invalid)
    print('dsfbgruigerfe')
    await jwt_middleware(request)
    return request
