"""Servidor web do Resumidor de Reuniões.

Rode com:  python app.py   e abra http://localhost:8000
"""

import os
import secrets
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agente import ErroAgente, ata_para_markdown, gerar_ata

PASTA = Path(__file__).parent
LIMITE_CARACTERES = 100_000
# Senha de acesso (opcional). Na hospedagem, defina APP_SENHA para que só
# quem tem a senha consiga gerar atas e gastar créditos da sua chave.
SENHA = os.environ.get("APP_SENHA", "")

app = FastAPI(title="Resumidor de Reuniões")
app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")


class Pedido(BaseModel):
    anotacoes: str


@app.get("/")
def pagina_inicial():
    return FileResponse(PASTA / "static" / "index.html")


@app.get("/api/exemplo")
def exemplo():
    texto = (PASTA / "exemplo_reuniao.txt").read_text(encoding="utf-8")
    return {"anotacoes": texto}


@app.get("/api/config")
def config():
    return {"precisa_senha": bool(SENHA)}


@app.post("/api/resumir")
def resumir(pedido: Pedido, x_senha: str = Header(default="")):
    if SENHA and not secrets.compare_digest(x_senha.encode(), SENHA.encode()):
        return JSONResponse({"erro": "Senha incorreta. Peça a senha de acesso a quem compartilhou o app."}, status_code=401)
    texto = pedido.anotacoes.strip()
    if not texto:
        return JSONResponse({"erro": "Cole as anotações da reunião antes de gerar a ata."}, status_code=400)
    if len(texto) > LIMITE_CARACTERES:
        return JSONResponse(
            {"erro": f"O texto tem mais de {LIMITE_CARACTERES:,} caracteres. Divida em partes menores.".replace(",", ".")},
            status_code=400,
        )
    try:
        ata = gerar_ata(texto)
    except ErroAgente as e:
        return JSONResponse({"erro": str(e)}, status_code=502)
    return {"ata": ata.model_dump(), "markdown": ata_para_markdown(ata)}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
