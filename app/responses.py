from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message


def app_response(data: Any):
    return {'status': 'success', 'data': data, 'error': None}


def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.code,
                        content={'status': 'error', 'data': None, 'error': {'code': exc.code, 'message': exc.message}})


def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={'status': 'error', 'data': None,
                                                              'error': {'code': exc.status_code,
                                                                        'message': exc.detail}})


def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        place = '.'.join(str(item) for item in error.get('loc', []))
        errors.append(f'{place}: {error.get("msg")}')
    return JSONResponse(status_code=422,
                        content={'status': 'error', 'data': None,
                                 'error': {'code': 422, 'message': '; '.join(errors)}})


def exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={'status': 'error', 'data': None,
                                                  'error': {'code': 500, 'message': 'Internal server error'}})


def setup_exception_handlers(app: FastAPI):
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, exception_handler)
