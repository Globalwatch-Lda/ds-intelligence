"""Verifica a integridade de UM ficheiro (PDF ou imagem) fora do CRM.

Para responder à pergunta "este documento foi editado?" sobre um ficheiro que
alguém enviou por email ou WhatsApp, sem ter de o carregar num processo. Usa
exactamente a mesma camada forense da Análise Documental (Fase 3), por isso o
que sair aqui é o que sairia no relatório.

    python scripts/verificar_pdf.py "C:\\caminho\\recibo.pdf" [outro.pdf ...]

Read-only: lê o ficheiro, não escreve nada nem contacta o CRM.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.forense_ficheiro import analisar  # noqa: E402

CORES = {"alto": "!!", "medio": " !", "baixo": "  "}
MEDIA = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}


def verificar(caminho: Path) -> int:
    dados = caminho.read_bytes()
    mt = MEDIA.get(caminho.suffix.lower())
    sinais, factos = analisar(dados, caminho.name, mt)

    print(f"\n=== {caminho.name}  ({len(dados):,} bytes)".replace(",", " "))
    for chave, rotulo in (
        ("producer", "Produtor"), ("creator", "Criador"), ("guardas", "Gravações"),
        ("criado_em", "Criado em"), ("modificado_em", "Modificado em"),
        ("assinado_digitalmente", "Assinado digitalmente"),
        ("software", "Software (EXIF)"), ("data_original", "Data da fotografia"),
        ("data_ficheiro", "Data de gravação"),
    ):
        if factos.get(chave) not in (None, ""):
            print(f"    {rotulo:22}: {factos[chave]}")

    if not sinais:
        print("\n    ✓ Sem sinais de adulteração do ficheiro.")
        return 0
    print(f"\n    {len(sinais)} sinal(is):")
    for s in sinais:
        print(f"    {CORES.get(s['severidade'], '  ')} [{s['severidade']}] {s['titulo']}")
        print(f"         {s['detalhe']}")
    return len([s for s in sinais if s["severidade"] == "alto"])


def main() -> None:
    alvos = [Path(a) for a in sys.argv[1:] if not a.startswith("-")]
    if not alvos:
        print(__doc__)
        sys.exit(2)
    graves = 0
    for alvo in alvos:
        if not alvo.exists():
            print(f"\n=== {alvo}: ficheiro não encontrado")
            continue
        graves += verificar(alvo)
    print(
        "\nNota: estes sinais indicam EDIÇÃO do ficheiro, não falsificação. "
        "Perante um sinal alto, pedir o original ao emitente."
    )
    sys.exit(1 if graves else 0)


if __name__ == "__main__":
    main()
