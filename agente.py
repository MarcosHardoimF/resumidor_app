"""Agente resumidor de reuniões.

Recebe anotações brutas de uma reunião e devolve uma ata estruturada,
usando o Claude com saída estruturada (o resultado sempre segue o modelo Ata).
"""

from datetime import date

import anthropic
from pydantic import BaseModel, Field

MODELO = "claude-opus-5-5"

INSTRUCOES = """Você é um assistente especializado em atas de reunião.

Sua tarefa: receber anotações brutas (bagunçadas, incompletas ou transcrição) e produzir uma ata clara e objetiva.

Passo a passo:
1. Leia todo o material antes de escrever.
2. Identifique participantes, data, assuntos discutidos, decisões tomadas, tarefas combinadas e dúvidas em aberto.
3. Para cada tarefa, identifique o responsável e o prazo. Se não estiverem no texto, use exatamente "A definir". Nunca invente.
4. Quando o prazo for relativo (ex.: "até sexta"), converta para uma data no formato DD/MM/AAAA a partir da data da reunião e mantenha a referência original entre parênteses, ex.: "13/11/2026 (sexta)".

Regras:
- Escreva em português, frases curtas, sem jargão desnecessário.
- Não acrescente informação que não esteja nas anotações.
- Se algo estiver ambíguo, coloque em "pontos_em_aberto" em vez de adivinhar.
- O resumo deve ter de 3 a 5 frases."""


class Tarefa(BaseModel):
    tarefa: str = Field(description="O que precisa ser feito")
    responsavel: str = Field(description='Nome do responsável ou "A definir"')
    prazo: str = Field(description='Data do prazo ou "A definir"')


class Ata(BaseModel):
    titulo: str = Field(description="Assunto principal da reunião")
    data: str = Field(description='Data da reunião no formato DD/MM/AAAA ou "A definir"')
    participantes: list[str]
    resumo: str
    decisoes: list[str]
    proximos_passos: list[Tarefa]
    pontos_em_aberto: list[str]


class ErroAgente(Exception):
    """Erro com mensagem já pronta para mostrar ao usuário."""


_cliente: anthropic.Anthropic | None = None


def _get_cliente() -> anthropic.Anthropic:
    global _cliente
    if _cliente is None:
        _cliente = anthropic.Anthropic()
    return _cliente


def gerar_ata(anotacoes: str) -> Ata:
    """Chama o Claude e devolve a ata já validada."""
    hoje = date.today().strftime("%d/%m/%Y")
    try:
        resposta = _get_cliente().beta.messages.parse(
            model=MODELO,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=INSTRUCOES,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Data de hoje: {hoje}. Se as anotações não informarem o ano, use o ano atual.\n\n"
                        f"<anotacoes>\n{anotacoes}\n</anotacoes>"
                    ),
                }
            ],
            output_format=Ata,
        )
    except anthropic.AuthenticationError:
        raise ErroAgente("Chave da API inválida. Confira a variável ANTHROPIC_API_KEY.")
    except anthropic.PermissionDeniedError:
        raise ErroAgente("A chave da API não tem permissão para usar este modelo.")
    except anthropic.RateLimitError:
        raise ErroAgente("Muitas solicitações seguidas. Aguarde um minuto e tente de novo.")
    except anthropic.BadRequestError as e:
        raise ErroAgente(f"A solicitação foi recusada pela API: {e.message}")
    except anthropic.APIStatusError as e:
        raise ErroAgente(f"Erro no serviço do Claude ({e.status_code}). Tente de novo em instantes.")
    except anthropic.APIConnectionError:
        raise ErroAgente("Sem conexão com a API do Claude. Verifique a internet ou o proxy da empresa.")
    except TypeError as e:
        # O SDK levanta TypeError quando não encontra nenhuma credencial.
        if "api_key" in str(e) or "auth" in str(e).lower():
            raise ErroAgente(
                "Nenhuma chave da API encontrada. Defina a variável ANTHROPIC_API_KEY antes de iniciar o app."
            )
        raise

    if resposta.stop_reason == "refusal":
        raise ErroAgente("O Claude não processou essas anotações. Revise o conteúdo e tente de novo.")
    if resposta.stop_reason == "max_tokens":
        raise ErroAgente("As anotações são longas demais para uma única ata. Divida o texto e tente de novo.")
    if resposta.parsed_output is None:
        raise ErroAgente("Não foi possível montar a ata. Tente de novo.")
    return resposta.parsed_output


def ata_para_markdown(ata: Ata) -> str:
    """Converte a ata para Markdown, no mesmo formato do agente do Claude Code."""
    linhas = [
        f"# Ata – {ata.titulo}",
        f"**Data:** {ata.data}   **Participantes:** {', '.join(ata.participantes) or 'A definir'}",
        "",
        "## Resumo",
        ata.resumo,
        "",
        "## Decisões",
        *([f"- {d}" for d in ata.decisoes] or ["- Nenhuma decisão registrada."]),
        "",
        "## Próximos passos",
        "| Tarefa | Responsável | Prazo |",
        "|---|---|---|",
        *[f"| {t.tarefa} | {t.responsavel} | {t.prazo} |" for t in ata.proximos_passos],
        "",
        "## Pontos em aberto",
        *([f"- {p}" for p in ata.pontos_em_aberto] or ["- Nenhum."]),
        "",
    ]
    return "\n".join(linhas)
