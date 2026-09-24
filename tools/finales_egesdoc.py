# -*- coding: utf-8 -*-
"""Descarga de eGesDoc el PDF comentado de todos los documentos en Final de un PO.

Es el mismo camino que a mano —entrar en el PO, Documents, la lupa de cada
documento, «Download commented file»— pero seguido: un PO con 345 finales son
345 idas y vueltas al portal, y el portal se atraganta.

    python tools/finales_egesdoc.py 1000100010
    python tools/finales_egesdoc.py 1000100010 "M:\\...\\P-26-001\\comentados"
    python tools/finales_egesdoc.py 1000100010 --listar     (solo mira, no baja)
    python tools/finales_egesdoc.py 1000100010 --max 5      (los 5 primeros, para probar)

Se puede parar (Ctrl+C) y relanzar las veces que haga falta: lo que ya está en
la carpeta no se vuelve a pedir, así que la segunda pasada solo cuesta lo que
falló la primera. Al terminar deja un `_resumen <fecha>.csv` con lo bajado y lo que no.
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from core.services import egesdoc  # noqa: E402


def por_defecto(po: str) -> Path:
    """Dónde dejar los PDF si no se dice otra cosa: en Descargas, nunca dentro
    del repositorio, que es público y esto son documentos del cliente."""
    for nombre in ("Downloads", "Descargas"):
        carpeta = Path.home() / nombre
        if carpeta.is_dir():
            return carpeta / f"eGesDoc {po}"
    return Path.home() / f"eGesDoc {po}"


def uso() -> None:
    print(__doc__.strip())
    sys.exit(1)


def opciones(argv: list[str]) -> dict:
    """{po, destino, limite, listar} de la línea de comandos.

    `--max` solo se traga el siguiente argumento si es un número: con
    «--max "M:\\…\\comentados"» se llevaría por delante la carpeta destino y los
    PDF del cliente acabarían en Descargas sin que nadie lo hubiera pedido.
    """
    argv = list(argv)
    limite = 0
    if "--max" in argv:
        i = argv.index("--max")
        if len(argv) > i + 1 and argv[i + 1].isdigit():
            limite = int(argv[i + 1])
            del argv[i:i + 2]
        else:
            del argv[i]
    listar = "--listar" in argv
    sueltos = [a for a in argv if not a.startswith("--")]
    po = sueltos[0] if sueltos and sueltos[0].isdigit() else ""
    destino = Path(sueltos[1]) if len(sueltos) > 1 else (por_defecto(po) if po else None)
    return {"po": po, "destino": destino, "limite": limite, "listar": listar}


def main() -> None:
    opts = opciones(sys.argv[1:])
    if not opts["po"]:
        uso()
    po, destino, limite = opts["po"], opts["destino"], opts["limite"]

    if not egesdoc.is_configured():
        print("Faltan usuario o contrasena de eGesDoc: Ajustes > Portales.")
        sys.exit(2)

    print(f"Entrando en eGesDoc para el PO {po}...")
    s = egesdoc.login()
    try:
        proyecto = egesdoc.find_project_for_po(s, po)
        egesdoc.enter_po(s, proyecto, po)
        docs = egesdoc.list_documents(s, summary="Finals")
        print(f"Proyecto {proyecto}: {len(docs)} documentos en Final.")
        if opts["listar"]:
            for d in docs:
                fecha = d["return_date"].strftime("%d/%m/%Y") if d["return_date"] else ""
                print(f"  {d['code']:<28} {fecha:<10} {d['return_status']:<32} {d['title'][:50]}")
            return

        destino.mkdir(parents=True, exist_ok=True)
        print(f"Destino: {destino}\n")

        def progreso(n, total, doc, estado):
            print(f"  [{n:>3}/{total}] {doc['code']:<28} {estado}")

        filas = egesdoc.download_final_documents(po, destino, project_hint=proyecto,
                                                 session=s, progreso=progreso,
                                                 limite=limite)
    finally:
        s.close()

    bajados = [f for f in filas if f["file"]]
    fallos = [f for f in filas if f["error"]]
    sin = [f for f in filas if not f["file"] and not f["error"]]

    resumen = egesdoc.write_summary(filas, destino)

    print(f"\n{len(bajados)} de {len(filas)} en la carpeta.")
    if sin:
        print(f"{len(sin)} sin fichero comentado en el portal:")
        for f in sin[:10]:
            print(f"   {f['code']}")
    if fallos:
        print(f"{len(fallos)} fallaron — relanza el mismo comando y se reintentan solos:")
        for f in fallos[:10]:
            print(f"   {f['code']}: {f['error']}")
    print(f"Resumen: {resumen}")


if __name__ == "__main__":
    main()
