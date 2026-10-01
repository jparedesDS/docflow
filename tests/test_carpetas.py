# -*- coding: utf-8 -*-
"""En qué carpeta env./dev. cae cada documento.

Se ejecuta a mano, sin pytest, con el intérprete de la app:

    docflow_env\\Scripts\\python.exe tests\\test_carpetas.py
"""
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.services import dev_folders as D

fallos = 0


def ok(cond, msg):
    global fallos
    if not cond:
        fallos += 1
        print("  FALLO:", msg)


def carpetas(*nombres):
    return [{"kind": "env", "name": n, "dotted": True, "path": Path("X") / n} for n in nombres]


# Las de un pedido real de WOOD (P-26/004)
ENV = carpetas("Certificados Prueba y Materiales", "Cálculos", "FINAL QUALITY DOSSIER",
               "ITP", "MANUAL", "Manufacturing Program", "Planos", "VDDL")


def elegida(tipo, titulo):
    f = D._by_type_and_title(ENV, tipo, titulo)
    return f["name"] if f else None


# El tipo manda sobre una palabra del título que coincide por casualidad:
# «QUALITY CONTROL PLAN» comparte QUALITY con la carpeta del dossier.
ok(elegida("PPI", "QUALITY CONTROL PLAN") == "ITP",
   f"el ITP va a su carpeta: {elegida('PPI', 'QUALITY CONTROL PLAN')}")
ok(elegida("Dossier", "FINAL QUALITY DOSSIER") == "FINAL QUALITY DOSSIER",
   f"el dossier, a la suya: {elegida('Dossier', 'FINAL QUALITY DOSSIER')}")

# El tipo del ERP no está escrito igual que la clave del catálogo
ok(elegida("Certificados", "MATERIAL AND TEST CERTIFICATES") == "Certificados Prueba y Materiales",
   f"«Certificados» (plural) encuentra su carpeta: {elegida('Certificados', 'MATERIAL AND TEST CERTIFICATES')}")
ok(D._palabras_del_tipo("certificados") == D.TYPE_KEYWORDS["Certificado"],
   "el tipo se busca sin acentos, sin mayúsculas y en singular/plural")
ok(D._palabras_del_tipo("") == [] and D._palabras_del_tipo("Inventado") == [],
   "un tipo desconocido no trae palabras")

# El tipo que ES el nombre de la carpeta, aunque el título no se parezca
ok(elegida("VDDL", "DOCUMENTS LIST") == "VDDL", f"VDDL: {elegida('VDDL', 'DOCUMENTS LIST')}")
ok(elegida("VDDL", "Lista de documentos") == "VDDL", "VDDL con el título en español")

# La misma carpeta, abreviada como la abrevia cada pedido
for nombre in ("CÁL Y PLA", "Pla y Cál", "Cálculos y Planos"):
    carpetas_ = carpetas(nombre, "Planos", "MANUAL")
    elegida_ = D._by_type_and_title(carpetas_, "Cálculos y Planos",
                                    "CÁLCULOS Y PLANOS - - 890-170-FE -05605")
    ok(elegida_ and elegida_["name"] == nombre,
       f"«{nombre}» es la carpeta de cálculos y planos: {elegida_ and elegida_['name']}")

# Los de siempre, que no se rompen
ok(elegida("Planos", "OVERALL DRAWING") == "Planos", f"planos: {elegida('Planos', 'OVERALL DRAWING')}")
ok(elegida("Manual", "INSTALLATION AND MAINTENANCE") == "MANUAL", "manual")
ok(elegida("Programa", "MANUFACTURING PLANNING") == "Manufacturing Program", "programa")

# Y cuando no hay carpeta, no se inventa ninguna
ok(elegida("Repuestos", "LIST OF RECOMMENDED SPARE PARTS") is None,
   f"sin carpeta de repuestos no se inventa: {elegida('Repuestos', 'LIST OF RECOMMENDED SPARE PARTS')}")
ok(elegida("Procedimientos", "PMI PROCEDURE") is None, "sin carpeta de procedimientos tampoco")

# ── El sufijo de la carpeta, según cómo vuelva el documento ─────────────────
for estado, espera in (
    ("Rechazado", "REJ"),          # rehacerlo: carpeta propia, como se archiva a mano
    ("1R - WITH COMMENTS - REJECTED", "REJ"),
    ("Com. Mayores", "COM"),       # corregirlo
    ("Com. Menores", "com"),
    ("Comentado", "com"),
    ("Aprobado", "AP"),
    ("Informativo", "AP"),
    ("Certificado", "AP"),
    ("", "com"),                   # sin estado, lo prudente es «con comentarios»
):
    ok(D._suffix(estado) == espera,
       f"«{estado}» debería ir a rev<N> {espera}, no {D._suffix(estado)}")

# ── El suministro del pedido: P-26/001 tiene una carpeta por cada uno ───────
from core.services import apertura  # noqa: E402

DOCS_S10 = [{"Doc. EIPSA": "26-001-S10-ESP-0005"}, {"Doc. EIPSA": "26-001-S10-ESP-0006"}]
ok(D.pedido_con_suministro("P-26/001", DOCS_S10) == "P-26/001-S10",
   f"el suministro sale del código EIPSA: {D.pedido_con_suministro('P-26/001', DOCS_S10)}")
ok(D.pedido_con_suministro("P-26/001", [{"Supp.": "S10", "Doc. EIPSA": ""}]) == "P-26/001-S10",
   "y del «Supp.» del ERP cuando el código no lo lleva")
ok(D.pedido_con_suministro("P-26/001-S10", [{"Doc. EIPSA": "26-001-S02-ESP-0001"}]) == "P-26/001-S10",
   "si el pedido ya lo trae escrito, manda ese")
ok(D.pedido_con_suministro("P-26/001", [{"Doc. EIPSA": "26-001-S02-ESP-0001"},
                                        {"Doc. EIPSA": "26-001-S10-ESP-0005"}]) == "P-26/001",
   "mezclados, no se elige: no caben en una sola carpeta")
ok(D.pedido_con_suministro("P-26/412", [{"Doc. EIPSA": "23-037-PRC-0006"}]) == "P-26/412",
   "un pedido sin suministro se queda como está")

ok(D.sufijo_de({"Doc. EIPSA": "26-031-S01-PLG-0005"}) == "S01", "el suministro del código")
ok(D.sufijo_de({"Supp.": "S02", "Doc. EIPSA": ""}) == "S02", "y el del ERP")
ok(D.sufijo_de({"Doc. EIPSA": "26-031-PLG-0005"}) == "", "el documento base no lo lleva")

# ── Las carpetas que ofrece «Nuevo pedido» ─────────────────────────────────
# El código va al Excel de importación como nº de documento EIPSA
# («26-099-CER-0002»): dos carpetas con el mismo darían dos filas iguales.
ok(not apertura.validate_catalog(), f"el catálogo está bien formado: {apertura.validate_catalog()}")
_codigos = [e["eipsa_code"] for e in apertura.SUBFOLDER_CATALOG]
ok(len(_codigos) == len(set(_codigos)),
   f"sin códigos repetidos: {[c for c in _codigos if _codigos.count(c) > 1]}")
ok(len(apertura.ALL_SUBFOLDERS) == len(set(apertura.ALL_SUBFOLDERS)), "ni carpetas repetidas")
for _carpeta, _code in (("env. Certificado Visual y Dimensional", "PRC-0013"),
                        ("env. Catálogo", "CAT-0001"),
                        ("env. Certificado ATEX", "ATEX-0001"),
                        ("env. PMI PROCEDURE", "PRC-0008"),
                        ("env. Certificado Cumplimiento", "CER-0002")):
    _e = apertura.SUBFOLDER_INDEX.get(_carpeta)
    ok(_e is not None and _e["eipsa_code"] == _code,
       f"{_carpeta} con {_code}: {_e and _e['eipsa_code']}")
ok("env. PMI" not in apertura.SUBFOLDER_INDEX,
   "«env. PMI» se renombró a «env. PMI PROCEDURE», no conviven las dos")

ok(apertura.sufijos_de_carpeta("P-26-001-S10 - TR-OMEGA - ACME") == {"S10"},
   f"la carpeta de un suministro: {apertura.sufijos_de_carpeta('P-26-001-S10 - TR')}")
ok(apertura.sufijos_de_carpeta("P-26-001 - S00 - S01 - TR-OMEGA") == {"S00", "S01"},
   "una carpeta puede agrupar varios")
ok(apertura.sufijos_de_carpeta("P-26-001-S08-S09R - TR-OMEGA") == {"S08", "S09R"},
   "y llevarlos pegados, con letra")
ok(apertura.parse_pedido("P-26/001-S09R") == ("P-26-001", "S09R"), "el sufijo con letra se lee")

# ── Revisiones en letra: «rev C» sin número por ninguna parte ───────────────
ok(D._partes_rev("rev2-50 AP") == (2, "50", "AP"), f"correlativo: {D._partes_rev('rev2-50 AP')}")
ok(D._partes_rev("rev51 COM") == (51, "", "COM"), "el número ES la revisión")
ok(D._partes_rev("revC com") == (None, "C", "com"), f"en letra: {D._partes_rev('revC com')}")
ok(D._partes_rev("rev B") == (None, "B", ""), "con espacio, igual")
ok(D._partes_rev("revisión pendiente") is None, "y lo que no es una carpeta de revisión, no lo es")
ok(D._env_rev_casa("revC", None, "C"), "la carpeta de envío «revC» es la de la revisión C")
ok(not D._env_rev_casa("revB", None, "C"), "pero «revB» no")
ok(not D._env_rev_casa("rev0", None, "C"), "y sin revisión que comparar, tampoco")

tmp = Path(tempfile.mkdtemp())
try:
    dev = tmp / "dev NDE"
    (dev / "revB com").mkdir(parents=True)             # la devolución de la rev B
    ruta, existe = D._rev_folder_for(dev, None, "C", "AP")
    ok(not existe and ruta.name == "revC AP",
       f"la carpeta sigue el estilo en letra del pedido: {ruta.name}")
    (dev / "revC AP").mkdir()
    otra, existe = D._rev_folder_for(dev, None, "C", "AP")
    ok(existe and otra == ruta, f"y si ya está, se reutiliza: {otra.name} ({existe})")

    # Carpeta dev vacía: manda el nombre de la carpeta de envío
    vacia = tmp / "dev PMI"
    vacia.mkdir()
    ruta, _ = D._rev_folder_for(vacia, None, "C", "com", envio=Path("revC"))
    ok(ruta.name == "revC com", f"lo enviado desde «env PMI\\revC» vuelve a «revC com»: {ruta.name}")
    ruta, _ = D._rev_folder_for(vacia, None, "C", "com")
    ok(ruta.name == "revC com", f"y sin carpeta de envío, igual: {ruta.name}")

    # Donde se lleva correlativo, la letra va detrás del guion, como siempre
    corr = tmp / "dev planos"
    (corr / "rev0-B com").mkdir(parents=True)
    ruta, _ = D._rev_folder_for(corr, None, "C", "com")
    ok(ruta.name == "rev1-C com", f"correlativo con revisión en letra: {ruta.name}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# Y que la carpeta se llame así de verdad, no solo el sufijo suelto
tmp = Path(tempfile.mkdtemp())
try:
    dev = tmp / "dev NDE"
    (dev / "rev1-49 com").mkdir(parents=True)          # la devolución anterior
    ruta, existe = D._rev_folder_for(dev, 50, "", D._suffix("Rechazado"))
    ok(not existe and ruta.name == "rev2-50 REJ",
       f"la nueva carpeta lleva REJ y el correlativo siguiente: {ruta.name}")
    # una carpeta REJ que ya exista se reutiliza en vez de duplicarse
    (dev / ruta.name).mkdir()
    otra, existe = D._rev_folder_for(dev, 50, "", "REJ")
    ok(existe and otra.name == ruta.name, f"se reutiliza la REJ existente: {otra.name} ({existe})")
    # y no se confunde con la de comentarios mayores
    com, _ = D._rev_folder_for(dev, 50, "", "COM")
    ok(com.name != ruta.name, f"REJ y COM son carpetas distintas: {com.name} vs {ruta.name}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ── Devolución sin paquete: el correo abre igual su carpeta dev. ───────────
# Los transmittals «2I - FOR INFORMATION ONLY» de Wood llegan sin enlace de
# descarga. No hay PDF, pero la devolución existe y va donde iría el documento.
tmp = Path(tempfile.mkdtemp())
tecnico_real = D.tecnico_dir
try:
    tecnico = tmp / "2-Tecnico"
    (tecnico / "env. PMI PROCEDURE").mkdir(parents=True)
    (tecnico / "env. MANUAL").mkdir()
    D.tecnico_dir = lambda _pedido: tecnico

    DOC = {"Nº Pedido": "P-26/004", "Supp.": "S00", "Doc. EIPSA": "",
           "Doc. Cliente": "V-1234AB00A-1100-300-PRO-001", "Título": "PMI PROCEDURE",
           "Rev.": "0", "Estado": "Informativo", "Tipo de documento": ""}
    CORREO = b"From: Prodoc.postmaster@woodgroup.com\r\n\r\nWood Transmittal"

    res = D.archive_email_only([DOC], "P-26/004", email_raw=CORREO,
                               email_date="2026-09-24", dry_run=True)
    ok(res["plan"] and res["plan"][0]["dest"].parent.name == "rev0 AP",
       f"el «for information» es AP: {res['plan'] and res['plan'][0]['dest'].parent.name}")
    ok(not (tecnico / "dev. PMI PROCEDURE").exists(), "con dry_run no se crea nada")

    res = D.archive_email_only([DOC], "P-26/004", email_raw=CORREO, email_date="2026-09-24")
    eml = tecnico / "dev. PMI PROCEDURE" / "rev0 AP" / "dev 2026-09-24.eml"
    ok(eml.is_file(), f"el correo queda en dev. PMI PROCEDURE\\rev0 AP: {eml.is_file()}")
    ok(eml.read_bytes() == CORREO, "y es el correo entero")
    ok(res["emails"] == [eml] and not res["skipped"], f"se informa de dónde cayó: {res}")
    ok("correo en dev. PMI PROCEDURE\\rev0 AP" in D.summary_line(res),
       f"el resumen lo dice: {D.summary_line(res)}")

    # Repetirlo no duplica ni la carpeta ni el correo
    antes = sorted(p.name for p in (tecnico / "dev. PMI PROCEDURE").iterdir())
    D.archive_email_only([DOC], "P-26/004", email_raw=b"otro", email_date="2026-09-24")
    ok(sorted(p.name for p in (tecnico / "dev. PMI PROCEDURE").iterdir()) == antes,
       "repetirlo no crea una carpeta nueva")
    ok(eml.read_bytes() == CORREO, "ni pisa el correo que ya estaba")

    # Un documento anulado no abre carpeta dev nueva: cancela algo ya archivado
    void = dict(DOC, Estado="M - VOID", Título="MANUAL")
    res = D.archive_email_only([void], "P-26/004", email_raw=CORREO, email_date="2026-09-24")
    ok(not res["emails"] and res["skipped"], f"un VOID sin carpeta dev se deja fuera: {res['skipped']}")
    ok(not (tecnico / "dev. MANUAL").exists(), "y no le abre carpeta")

    # Pero si la carpeta de esa revisión ya está, la anulación va dentro de ella
    void = dict(DOC, Estado="M - VOID")
    res = D.archive_email_only([void], "P-26/004", email_raw=CORREO, email_date="2026-10-01")
    eml = tecnico / "dev. PMI PROCEDURE" / "rev0 AP" / "VOID" / "dev 2026-10-01.eml"
    ok(res["emails"] == [eml], f"el VOID va a rev0 AP\\VOID: {res['emails']}")
    ok(eml.is_file(), "y el correo queda ahí")
    ok(not (tecnico / "dev. PMI PROCEDURE" / "rev1 VOID").exists(),
       "la anulación no abre un correlativo nuevo")
finally:
    D.tecnico_dir = tecnico_real
    shutil.rmtree(tmp, ignore_errors=True)

# ── Un transmittal con documentos de VARIOS suministros ────────────────────
# TR devolvió en un mismo correo el plano de P-26/031, el de su S01 y el de su
# S02. Cada suministro es una carpeta de pedido distinta; antes se elegía una
# sola para todo el paquete y los tres planos caían en la del S00.
tmp = Path(tempfile.mkdtemp())
tecnico_real = D.tecnico_dir
try:
    tecnicos = {}
    for supp in ("S00", "S01", "S02"):
        t = tmp / f"P-26-031-{supp} - TR-SILLENO" / "2-Tecnico"
        (t / "env planos").mkdir(parents=True)
        tecnicos[f"P-26/031-{supp}"] = t
    tecnicos["P-26/031"] = tecnicos["P-26/031-S00"]    # el pedido a secas es el S00
    D.tecnico_dir = lambda pedido: tecnicos.get(pedido)

    def plano(codigo, supp, cliente):
        return {"Nº Pedido": "P-26/031", "Supp.": supp, "Doc. EIPSA": codigo,
                "Doc. Cliente": cliente, "Título": "OVERALL DRAWING WITH PRINCIPAL DIMENSIONS",
                "Tipo de documento": "Planos", "Rev.": "1", "_rev_cliente": "B",
                "Estado": "C - REVIEWED WITH MINOR COMMENTS"}

    PLANOS = [plano("26-031-PLG-0005", "S00", "SLN.5024-2000-1057410920-C16-0001"),
              plano("26-031-S01-PLG-0005", "S01", "SLN.5024-2000-1057410920-C16-0002"),
              plano("26-031-S02-PLG-0005", "S02", "SLN.5024-2000-1057410920-C16-0003")]

    paquete = tmp / "10571-TRSEI-V-14021.zip"
    with zipfile.ZipFile(paquete, "w") as zf:
        for i, d in enumerate(PLANOS):
            zf.writestr(d["Doc. Cliente"] + ".pdf", b"%PDF-" + str(i).encode())

    res = D.archive_return(paquete, PLANOS, "P-26/031")
    caidos = {Path(dest).parts[-5]: Path(dest).parent.name for _, dest in res["archived"]}
    ok(not res["skipped"] and len(res["archived"]) == 3, f"los tres se colocan: {res['skipped']}")
    ok(caidos == {"P-26-031-S00 - TR-SILLENO": "rev1-B com",
                  "P-26-031-S01 - TR-SILLENO": "rev1-B com",
                  "P-26-031-S02 - TR-SILLENO": "rev1-B com"},
       f"cada plano en la carpeta de SU suministro: {caidos}")

    # Y el suministro que no tiene carpeta no se lleva por delante a los demás
    suelto = plano("26-031-S09-PLG-0007", "S09", "SLN.5024-2000-1057410920-C16-0009")
    otro = tmp / "suelto.zip"
    with zipfile.ZipFile(otro, "w") as zf:
        zf.writestr(suelto["Doc. Cliente"] + ".pdf", b"%PDF-9")
        zf.writestr(PLANOS[1]["Doc. Cliente"] + ".pdf", b"%PDF-1b")
    res = D.archive_return(otro, [suelto, PLANOS[1]], "P-26/031")
    ok(len(res["archived"]) == 1 and len(res["skipped"]) == 1,
       f"uno se coloca y el otro se informa: {res['archived']} / {res['skipped']}")
    ok("S09" in res["skipped"][0][1], f"y se dice qué pedido falta: {res['skipped'][0][1]}")

    # Con un solo suministro en el correo, los documentos que no lo dicen van
    # con el resto (un plano de S01 y su índice sin código de suministro)
    sin_supp = {"Nº Pedido": "P-26/031", "Doc. EIPSA": "26-031-PLG-0009",
                "Doc. Cliente": "SLN.5024-2000-1057410920-C16-0010",
                "Título": "OVERALL DRAWING", "Tipo de documento": "Planos", "Rev.": "1",
                "_rev_cliente": "B", "Estado": "C - REVIEWED WITH MINOR COMMENTS"}
    solo_s01 = tmp / "solo-s01.zip"
    with zipfile.ZipFile(solo_s01, "w") as zf:
        zf.writestr(sin_supp["Doc. Cliente"] + ".pdf", b"%PDF-10")
    res = D.archive_return(solo_s01, [sin_supp, PLANOS[1]], "P-26/031")
    ok(len(res["archived"]) == 1 and
       Path(res["archived"][0][1]).parts[-5] == "P-26-031-S01 - TR-SILLENO",
       f"sigue al único suministro del correo: {res['archived']}")
finally:
    D.tecnico_dir = tecnico_real
    shutil.rmtree(tmp, ignore_errors=True)

# ── Un documento que el cliente ANULA (VOID) ───────────────────────────────
# TR anuló el 01-10-2026 dos planos que ya estaban aprobados en «rev0-A». La
# anulación no es una devolución más: va a «rev0-A\VOID», al lado del aprobado,
# y no abre un correlativo nuevo. Antes se dejaba fuera y había que colocarla
# a mano.
tmp = Path(tempfile.mkdtemp())
tecnico_real = D.tecnico_dir
try:
    tecnico = tmp / "P-24-066-S05 - TR-SINOPEC" / "2-Tecnico"
    (tecnico / "env cál y pla" / "rev 0").mkdir(parents=True)
    (tecnico / "env cál y pla" / "rev 0" / "V-1065110910-0209.pdf").write_bytes(b"%PDF-enviado")
    # El aprobado cuelga de una subcarpeta hecha a mano dentro de la revisión
    aprobado = tecnico / "dev cál y pla" / "rev0-A" / "AProbados"
    aprobado.mkdir(parents=True)
    (aprobado / "V-1065110910-0209.pdf").write_bytes(b"%PDF-aprobado")
    (tecnico / "dev cál y pla" / "rev1-B").mkdir()
    D.tecnico_dir = lambda pedido: tecnico if pedido == "P-24/066-S05" else None

    ANULADO = {"Nº Pedido": "P-24/066", "Supp.": "S05",
               "Doc. EIPSA": "24-066-S05-ESP-0053", "Doc. Cliente": "V-1065110910-0209",
               "Título": "SPECIFICATION AND TECHNICAL DATA 889-260-FE -00311",
               "Tipo de documento": "Cálculos y Planos", "Rev.": "0",
               "_rev_cliente": "A", "Estado": "VOID"}

    paquete = tmp / "10651-TSOOK-1065110910-00081.zip"
    with zipfile.ZipFile(paquete, "w") as zf:
        zf.writestr("V-1065110910-0209.pdf", b"%PDF-anulado")

    res = D.archive_return(paquete, [ANULADO], "P-24/066", email_raw=b"correo",
                           email_date="2026-10-01")
    ok(len(res["archived"]) == 1 and not res["skipped"], f"el VOID se archiva: {res}")
    destino = Path(res["archived"][0][1])
    ok(destino.parent.name == "VOID" and destino.parent.parent.name == "rev0-A",
       f"en rev0-A\\VOID, con el aprobado al lado: {destino.parent}")
    ok((aprobado / "V-1065110910-0209.pdf").read_bytes() == b"%PDF-aprobado",
       "sin tocar el PDF aprobado, que es el mismo nombre de fichero")
    ok(destino.read_bytes() == b"%PDF-anulado", "y con el documento anulado dentro")
    ok((destino.parent / "dev 2026-10-01.eml").is_file(), "el correo queda en la carpeta VOID")
    ok(not (tecnico / "dev cál y pla" / "rev2-A VOID").exists(),
       "la anulación no abre correlativo nuevo")
    ok("rev0-A\\VOID" in D.summary_line(res), f"el resumen lo dice: {D.summary_line(res)}")

    # Repetir la descarga no duplica nada
    antes = sorted(p.name for p in destino.parent.iterdir())
    res = D.archive_return(paquete, [ANULADO], "P-24/066", email_raw=b"otro",
                           email_date="2026-10-01")
    ok(sorted(p.name for p in destino.parent.iterdir()) == antes and not res["skipped"],
       "volver a archivarlo no duplica nada")

    # Sin carpeta de esa revisión, la anulación abre la suya con sufijo VOID
    otra = {**ANULADO, "Doc. EIPSA": "24-066-S05-ESP-0099",
            "Doc. Cliente": "V-1065110910-0299", "Rev.": "3", "_rev_cliente": "D"}
    suelto = tmp / "otro.zip"
    with zipfile.ZipFile(suelto, "w") as zf:
        zf.writestr("V-1065110910-0299.pdf", b"%PDF-anulado-3")
    res = D.archive_return(suelto, [otra], "P-24/066")
    ok(len(res["archived"]) == 1 and
       Path(res["archived"][0][1]).parent.name == "rev2-D VOID",
       f"sin revisión archivada, carpeta propia: {res['archived']} / {res['skipped']}")
finally:
    D.tecnico_dir = tecnico_real
    shutil.rmtree(tmp, ignore_errors=True)

print("FALLOS:", fallos)
