# Expediente de cliente — Fase 1 (datos + Estado documentación.xlsx) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dado un cliente y sus PO, reunir todos los datos (ERP, DocFlow, reclamaciones, buzón) y escribir `Estado documentación.xlsx` idéntico a la hoja validada por JP.

**Architecture:** Servicios sin interfaz que devuelven `dict` planos. `expediente_correos` lee y cachea correos; `expediente` agrupa pedidos en PO y monta el expediente con cargadores sustituibles (los tests no tocan ERP ni IMAP); `expediente_texto` da el texto automático y guarda el texto de JP; `expediente_excel` escribe el libro desde cero. Pantallas, Word, copia de correos e informe completo son las fases 2–5 (planes aparte).

**Tech Stack:** Python 3.14 (`.venv`), openpyxl, imaplib vía `core.services.imap`, ERP vía `core.services.erp_common`.

**Spec:** `docs/superpowers/specs/2026-11-23-expediente-cliente-design.md`

## Global Constraints

- Todo es **lectura** de ERP, M: y buzón. Lo único que se escribe: `state/expedientes/`, `state/expediente_correos/` y el `.xlsx` de salida.
- Repositorio público: tests y código con datos **inventados** (`P-99/…`, PO `1099…`, `@ejemplo.test`); nada de clientes, personas o cargos reales en el código.
- Tests = scripts que imprimen `FALLOS: N` y salen con código 1 si N > 0 (patrón de `tests/test_plazos_erp.py`). Se ejecutan con `.venv\Scripts\python.exe tests\<archivo>.py`.
- Lint antes de cada commit: `ruff check --select F401,F811,F841,F821,E402 core tests`.
- Commits sin atribución a Claude. No hacer push.
- Fechas en las hojas: texto `dd/mm/aaaa`. Importes: `float` en los datos, formato español solo al presentar.
- Lo de EIPSA se nombra «EIPSA»; nunca personas de la casa en textos generados.
- Libro siempre escrito entero desde cero (nunca `insert_rows` sobre uno existente). Enlace de correo = `enlaces[msgid]`, jamás por posición de fila.

## Review Focus

1. **Referencia de PO vacía o rara** (`None`, `"N/A"`, letras): el pedido no se pierde ni rompe; queda en un grupo con su propio número de pedido como clave. → test en Task 1.
2. **Buzón no disponible o carpeta inexistente**: el expediente se monta sin correos, con `avisos` explicando qué falló, y el Excel se genera igual. → test en Task 4.
3. **El mismo correo en varias carpetas** (mismo Message-ID): cuenta una vez en correos, reclamaciones y contactos. → test en Task 3.
4. **Factura sin base ni detalle**, o abono que cita una factura que no está en la lista: importe 0 sin excepción; el abono huérfano no resta nada. → test en Task 2.
5. **Fechas del historial en formatos mezclados** (`dd-mm-aaaa`, `dd/mm/aaaa`) y nombre de cliente con `/` o `:`: se interpretan bien; el nombre de archivo y de hoja se sanea (hoja ≤ 31 caracteres). → tests en Task 2 y Task 6.

---

### Task 1: Agrupar pedidos en PO

**Files:**
- Create: `core/services/expediente.py`
- Test: `tests/test_expediente_datos.py`

**Interfaces:**
- Produces:
  - `clave_po(ref: str | None, pedido: str) -> str` — dígitos de `ref`, los 9 primeros; si hay menos de 9 dígitos, devuelve `pedido` sin sufijo de suministro (`"P-99/074"`).
  - `agrupar(ordenes: list[dict], extra: dict[str, list[str]] | None = None) -> dict[str, dict]` — `ordenes` son filas con claves `num_order, num_ref_order, order_date, order_amount, porc_deliveries, last_date_deliveries, closed, warranty_bond_state, warranty_bond_amount, warranty_bond_bank, warranty_bond_expiring_date, warranty_bond_reference, payment_term, material`. Devuelve `{clave: {"po": str, "pedidos": [str sin sufijo -Sxx, ordenados, únicos], "ordenes": [filas]}}`. `po` = la `num_ref_order` de 10 dígitos más frecuente del grupo (si no hay de 10, la clave). `extra` = `{po: [pedido]}` guardado por JP: mueve esos pedidos a ese PO.

- [ ] **Step 1: Write the failing test** `test_agrupar` con, entre otras:

```python
ok(ex.clave_po("1099010710-00", "P-99/048-S00") == "109901071", "sufijo -00")
ok(ex.clave_po("109901071", "P-99/048-S01") == "109901071", "9 dígitos")
ok(ex.clave_po("1099010710 Sup.04", "P-99/048-S04") == "109901071", "Sup.")
ok(ex.clave_po("N/A", "P-99/074-S02R") == "P-99/074", "sin dígitos → pedido")
ok(ex.clave_po(None, "P-99/074-S00") == "P-99/074", "vacío → pedido")
g = ex.agrupar([fila("P-99/048-S00", "109901071"), fila("P-99/048-S01", "1099010710-01"),
                fila("P-99/080-S00", "10990107-02")],            # errata: un dígito de menos
               extra={"1099010710": ["P-99/080"]})
ok(list(g) == ["109901071"] and g["109901071"]["po"] == "1099010710", g)
ok(g["109901071"]["pedidos"] == ["P-99/048", "P-99/080"], g)
```

- [ ] **Step 2:** Run `.venv\Scripts\python.exe tests\test_expediente_datos.py` → FAIL (`ModuleNotFoundError` / `AttributeError`).
- [ ] **Step 3:** Implement `clave_po` and `agrupar` in `core/services/expediente.py` (docstring del módulo: para qué sirve, en castellano, como los demás servicios).
- [ ] **Step 4:** Run the test → `FALLOS: 0`.
- [ ] **Step 5:** `git add core/services/expediente.py tests/test_expediente_datos.py && git commit -m "feat(expediente): agrupar pedidos en PO"`

---

### Task 2: Documentos, facturas y avales de un PO

**Files:**
- Modify: `core/services/expediente.py`
- Test: `tests/test_expediente_datos.py`

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - `documentos(filas: list[dict], pedidos: list[str], hoy: date) -> dict` — `filas` con las columnas de `monitoring.get_monitoring_data()` (`Nº Pedido, Nº Doc. Cliente, Nº Doc. EIPSA, Título, Estado, Nº Revisión, Fecha Env. Doc., Historial Rev., Seguimiento`). Devuelve `{"total": int, "aprobados": int, "cliente": [Doc], "eipsa": [Doc]}` con `Doc = {"pedido", "doc_cliente", "doc_eipsa", "titulo", "estado", "rev": str, "enviado": date|None, "dias": int|None, "envios": int, "primer_envio": date|None, "seguimiento": str}`. `Enviado` → `cliente`; `Com. Menores`, `Com. Mayores`, `Rechazado` (y cualquier otro no aprobado) → `eipsa`. `cliente` ordenado por `dias` descendente. `envios` = nº de entradas «Enviado» del historial, mínimo 1. Ignora estados anulados (`monitoring` ya los excluye).
  - `facturas(cabeceras: list[dict], detalles: list[dict], hoy: date) -> tuple[list[Fac], list[Fac]]` — `cabeceras` con `id, num_invoice, our_ref, their_ref, date_invoice, pay_date, invoice_state, base (texto €), iva, obs_delivnote`; `detalles` con `invoice_header_id, description, total`. Devuelve `(pendientes, verificar)` con `Fac = {"numero", "pedido", "su_ref", "fecha": date, "dias": int, "concepto": str, "base": float, "iva": float, "total": float, "reciente": bool}`.
  - `avales(ordenes: list[dict]) -> list[dict]` — `{"pedido", "importe": float, "banco", "vence", "ref"}` de las filas con `warranty_bond_state` = `EN VIGOR` (sin distinguir mayúsculas).

Reglas de `facturas` (spec, «Datos ▸ Facturas»):
- Pagada si `pay_date` o `invoice_state` == «Pagada».
- Anulada si algún abono (importe < 0) dice «ABONO DE NUESTRA FACTURA F-xx/yyy» citándola; el abono en sí nunca es pendiente.
- `verificar`: no pagada, no anulada, y `obs_delivnote` contiene «confirming» (sin mayúsculas).
- `base` = `administration.money(base)`; si vacío, suma de `money(total)` del detalle; si tampoco, 0.0.
- `concepto` = descripción de la primera línea de detalle sin la palabra inicial «EXCEL» ni saltos de línea; si vacía, `obs_delivnote`.
- `reciente` = `dias < 90`.

- [ ] **Step 1: Write the failing tests** `test_documentos`, `test_facturas`, `test_avales`. Deben incluir:

```python
d = ex.documentos([doc("P-99/048-S00", "Enviado", "15/09/2099",
                       "15/09/2099 Enviado Rev. 7 // 03-09-2099 Com. Menores Rev. 6 // 05-10-2097 Enviado Rev. 0"),
                   doc("P-99/048-S00", "Com. Mayores", "23/10/2099", ""),
                   doc("P-99/048-S00", "Aprobado", "01/01/2099", "")], ["P-99/048"], date(2099, 11, 19))
ok(d["total"] == 3 and d["aprobados"] == 1 and len(d["cliente"]) == 1 and len(d["eipsa"]) == 1, d)
c = d["cliente"][0]
ok(c["dias"] == 65 and c["envios"] == 2 and c["primer_envio"] == date(2097, 10, 5), c)   # formatos mezclados
p, v = ex.facturas([cab(1, "F-99/209", "P-99/028", 2469.58, obs="10%"),
                    cab(2, "F-99/059", "P-99/028", -2469.58, obs="", desc="ABONO DE NUESTRA FACTURA F-99/209"),
                    cab(3, "F-99/061", "P-99/028", 3095.58, obs="10%"),
                    cab(4, "F-99/191", "P-99/079", None, obs="fra. Nueva confirming"),
                    cab(5, "F-99/111", "P-99/079", None, pagada=True),
                    cab(6, "F-99/300", "P-99/079", None, obs=""),                     # sin base ni detalle
                    cab(7, "F-99/301", "P-99/079", -50.0, desc="ABONO DE NUESTRA FACTURA F-99/999")],  # abono huérfano
                   [det(4, "EXCEL", "176698.37")], date(2099, 11, 19))
ok([f["numero"] for f in p] == ["F-99/061", "F-99/300"], p)
ok([f["numero"] for f in v] == ["F-99/191"] and v[0]["base"] == 176698.37, v)
ok(p[1]["base"] == 0.0, "sin base ni detalle → 0")
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `documentos`, `facturas`, `avales` in `core/services/expediente.py`. Fechas con `erp_common.as_date` (acepta `dd/mm/aaaa`, `dd-mm-aaaa`, `aaaa-mm-dd`); el historial se parte por `//` con la regex `(\d{2}[/-]\d{2}[/-]\d{4})\s+(.+?)\s+Rev\.?\s*(\w+)`.
- [ ] **Step 4:** Run → `FALLOS: 0`.
- [ ] **Step 5:** Commit `feat(expediente): documentos, facturas pendientes y avales por PO`.

---

### Task 3: Correos — lectura con caché, reclamaciones y contactos

**Files:**
- Create: `core/services/expediente_correos.py`
- Test: `tests/test_expediente_correos.py`

**Interfaces:**
- Produces:
  - `Correo = {"msgid": str, "fecha": datetime, "de_nombre": str, "de_email": str (minúsculas), "para": str, "cc": str, "asunto": str, "cuerpo": str, "adjuntos": [str], "carpeta": str}`.
  - `carpetas_pedido(pedidos: list[str], todas: list[str]) -> list[str]` — de `todas` (nombres de carpeta del buzón), las que terminan en `P-YY-NNN` de algún pedido (`"P-99/048"` → `".../P-99-048"`).
  - `leer(carpetas: list[str], asuntos: list[str], cache: Path, progreso: Callable[[str], None] | None = None, imap=None) -> tuple[list[Correo], list[str]]` — devuelve `(correos sin duplicados por msgid, avisos)`. Usa la caché JSON `cache` (`{msgid: Correo serializado}`) y solo descarga los UID cuyo Message-ID no esté (cabeceras con `imap.cabeceras_en_lote`, cuerpo con `BODY.PEEK[]`). `asuntos` = textos a buscar con `SEARCH SUBJECT` en `INBOX`. `imap` por defecto el módulo `core.services.imap`; los tests pasan un doble. Un fallo de conexión o de carpeta → aviso de texto, nunca excepción.
  - `es_automatico(c: Correo, propio: str) -> bool` — `True` si el asunto empieza por `DEV:`, `Leído:`, `Read:` o contiene `eGesdoc - New transmittal`, o si el remitente es `propio` (la cuenta de documentación) **y** el asunto coincide con el recordatorio de DocFlow `^P-\d{2}/\d{3} / PO: .* // DOCUMENTS PENDING REVIEW$`.
  - `reclamaciones(correos: list[Correo], claves: list[str], propio_dominio: str, log: list[dict]) -> tuple[list[date], list[date]]` — `(eipsa, cliente)`: días únicos y ordenados. Cuenta los correos cuyo asunto contiene una clave (pedido o PO) **y** `RECLAIM|PENDING REVIEW|FORMAL CLAIM|DOCUMENT STATUS UPDATE|Pending documents|PENDING DOCUMENT`; el lado lo da el dominio del remitente. Además, en el cuerpo, los bloques citados `De:/From:` + `Enviado el:/Sent:` + `Asunto:/Subject:` con esa misma condición (fechas en castellano «jueves, 27 de noviembre de 2099 15:53» e inglés «Thursday, January 29, 2099 11:29 AM»). Suma las fechas `sent_at` de `log` (historial del `claims_log.json` de esos pedidos) al lado EIPSA.
  - `contactos(correos: list[Correo], dominio: str, hoy: date) -> list[Contacto]` — `Contacto = {"nombre", "email", "cargo", "telefono", "ultimo": date|None, "asunto": str, "enviados": int}`; los que han escrito (remitente del `dominio`), ordenados por `ultimo` descendente; después los que solo aparecen en Para/Cc con ≥ 2 apariciones, con `ultimo=None`. `cargo`/`telefono` por `firma(cuerpo, nombre)`.
  - `firma(cuerpo: str, nombre: str) -> tuple[str, str]` — busca la línea con el nombre (sin tildes, sin mayúsculas) y toma las 1–3 siguientes no vacías como cargo hasta la primera que parezca dirección o teléfono; teléfono = primer `(\+\d[\d\s().-]{7,})` en las 8 líneas siguientes. Si no encuentra, `("", "")`.

- [ ] **Step 1: Write the failing tests** `test_carpetas`, `test_leer_cache`, `test_automatico`, `test_reclamaciones`, `test_contactos`, con un doble de IMAP en el propio test. Deben incluir:

```python
ok(ec.carpetas_pedido(["P-99/048"], ["INBOX/P. 2099/P-99-048", "INBOX/P. 2099/P-99-049"]) == ["INBOX/P. 2099/P-99-048"], "carpeta")
# el mismo msgid en dos carpetas → una vez
cs, av = ec.leer(["A", "B"], [], tmp / "c.json", imap=Doble({"A": [m1], "B": [m1, m2]}))
ok(len(cs) == 2 and av == [], (len(cs), av))
cs2, _ = ec.leer(["A", "B"], [], tmp / "c.json", imap=DobleQueFallaSiDescarga())  # todo en caché
ok(len(cs2) == 2, "segunda lectura sale de la caché")
_, av = ec.leer(["NO-EXISTE"], [], tmp / "d.json", imap=Doble({}))
ok(av and "NO-EXISTE" in av[0], av)
e, c = ec.reclamaciones([correo("doc@eipsa.test", "RE: RECLAIMS: P-99/048 / PO: 109901071 // DOC. UNDER REVIEW",
                                cuerpo="De: Ana <ana@ejemplo.test>\nEnviado el: jueves, 27 de noviembre de 2098 15:17\n"
                                       "Asunto: RE: RECLAIMS: P-99/048 / PO: 109901071 // DOC. UNDER REVIEW", dia=date(2099, 5, 13))],
                        ["P-99/048", "1099010710"], "eipsa.test", [{"sent_at": "2099-06-01T10:00:00+00:00"}])
ok(e == [date(2099, 5, 13), date(2099, 6, 1)] and c == [date(2098, 11, 27)], (e, c))
k = ec.contactos([correo("sofia@ejemplo.test", "x", dia=date(2099, 11, 9), nombre="Sofía Ejemplo",
                         cuerpo="Sofía Ejemplo\nDocumentation Expediting\nCalle Falsa 1\nTel. +34 600 000 000"),
                  correo("luis@ejemplo.test", "y", dia=date(2099, 11, 18), nombre="Luis Ejemplo")], "ejemplo.test", date(2099, 11, 20))
ok([x["email"] for x in k] == ["luis@ejemplo.test", "sofia@ejemplo.test"], k)
ok(k[1]["cargo"] == "Documentation Expediting" and k[1]["telefono"] == "+34 600 000 000", k[1])
```

- [ ] **Step 2:** Run `.venv\Scripts\python.exe tests\test_expediente_correos.py` → FAIL.
- [ ] **Step 3:** Implement in `core/services/expediente_correos.py`. Serializa `fecha` como ISO en la caché. Cuerpo con `imap.get_plain_body`, recortado a 60 000 caracteres; cabeceras con `imap._decode_header_value`.
- [ ] **Step 4:** Run → `FALLOS: 0`.
- [ ] **Step 5:** Commit `feat(expediente): correos con caché, reclamaciones y contactos`.

---

### Task 4: Montar el expediente

**Files:**
- Modify: `core/services/expediente.py`
- Test: `tests/test_expediente_datos.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `clientes() -> list[str]` — `offers.client` normalizado (`clean`, mayúsculas, sin dobles espacios) de los pedidos con documentación no aprobada o facturas sin cobrar; ordenado.
  - `construir(cliente: str, ordenes, docs, cabeceras, detalles, correos: list[Correo], log: dict, hoy: date, pos: list[str] | None = None, extra=None, dominio: str = "", propio: str = "", avisos: list[str] | None = None) -> dict` — función pura. Devuelve `Expediente = {"cliente": str, "hoy": date, "avisos": [str], "pos": {po: PO}, "contactos": [Contacto con "pos": [po]]}` y `PO = {"po", "pedidos", "proyecto": str, "equipo": str, "importe": float, "ultima_entrega": date|None, "suministros": [...], "docs": (Task 2), "facturas", "verificar", "deuda_base", "deuda_total", "avales", "correos": [Correo con "automatico": bool], "recl_eipsa", "recl_cliente"}`. `pos=None` = todos los PO con algo pendiente; si se pasa, solo esos. Facturas de un PO = cabeceras cuyo `our_ref` contiene alguno de sus pedidos o cuyo `their_ref` contiene los 9 dígitos del PO. Correos de un PO = los de las carpetas de sus pedidos + los que tengan el PO (9 dígitos) o un pedido en el asunto. `proyecto` = `offers.project` del pedido más antiguo (vacío si no hay). `equipo` = `material` del pedido más antiguo.
  - `cargar(cliente: str, pos: list[str] | None = None, progreso=None) -> dict` — llama a ERP (`erp_common.safe_query`), `monitoring.get_monitoring_data()`, `state/claims_log.json`, `expediente_correos.leer(...)` con caché `state/expediente_correos/<slug cliente>.json`, carpetas extra y `extra` guardados por `expediente_texto` (Task 5), y devuelve `construir(...)`. `propio` = `core.config.IMAP_USER`; `dominio` = el dominio más frecuente entre los remitentes no propios de los correos del cliente.

- [ ] **Step 1: Write the failing tests** `test_construir` y `test_construir_sin_buzon` con filas inventadas (dos PO, uno con factura y docs, otro sin nada pendiente):

```python
e = ex.construir("CLIENTE FICTICIO", ORD, DOCS, CABS, DETS, CORREOS, LOG, date(2099, 11, 19),
                 dominio="ejemplo.test", propio="doc@eipsa.test")
ok(list(e["pos"]) == ["1099010610"], "sin pos= → solo los que tienen algo pendiente")
po = e["pos"]["1099010610"]
ok(po["deuda_base"] == 3095.58 and po["docs"]["cliente"] and po["recl_eipsa"], po)
ok(any(c["automatico"] for c in po["correos"]) and not all(c["automatico"] for c in po["correos"]), "marca automáticos")
e2 = ex.construir("CLIENTE FICTICIO", ORD, DOCS, CABS, DETS, [], {}, date(2099, 11, 19), avisos=["Sin buzón: timeout"])
ok(e2["avisos"] == ["Sin buzón: timeout"] and e2["pos"]["1099010610"]["correos"] == [], e2["avisos"])
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `clientes`, `construir`, `cargar`. SQL de `cargar`: pedidos (`public.orders o left join public.offers f on f.num_offer = o.num_offer`, columnas de Task 1 + `f.client, f.project, f.buyer`), facturas (`purch_fact.invoice_header` con `tax_base_amount::text AS base`) y detalle (`purch_fact.invoice_detail ... total_price::text AS total`), siempre con parámetros `%s`.
- [ ] **Step 4:** Run → `FALLOS: 0`.
- [ ] **Step 5:** Commit `feat(expediente): montar el expediente de un cliente`.

---

### Task 5: Texto automático y texto guardado de JP

**Files:**
- Create: `core/services/expediente_texto.py`
- Test: `tests/test_expediente_texto.py`

**Interfaces:**
- Consumes: `PO` y `Expediente` de Task 4.
- Produces:
  - `slug(cliente: str) -> str` — minúsculas, sin tildes, `[a-z0-9-]`, máx. 60.
  - `cargar_texto(cliente: str) -> dict` / `guardar_texto(cliente: str, datos: dict) -> None` — `state/expedientes/<slug>.json` con `json_store.read_json/write_json`. Estructura: `{"contexto": {proyecto: str}, "pos": {po: {"situacion": str, "punto": str, "siguiente": str, "segun_cliente": {doc_cliente: str}, "reemitir": [doc_cliente]}}, "correos": {msgid: {"importante": bool, "que_dice": str, "respuesta": str}}, "contactos": {email: {"cargo": str, "telefono": str}}, "carpetas": [str], "pedidos_extra": {po: [pedido]}}`; claves que falten = vacías.
  - `elegir(guardado: str | None, auto: str) -> str` — lo guardado si no está vacío; si no, `auto`.
  - `lo_esencial(po: dict, hoy: date) -> list[str]` — viñetas en este orden: deuda (o «No hay facturas pendientes: el 10 % de documentación final ya está cobrado.»), avales si hay, «Material entregado (última entrega dd/mm/aaaa).», documentación («X de Y aprobados; N esperando al cliente (el más antiguo, D días); M en EIPSA.»), reclamaciones («Al menos N reclamaciones o actualizaciones por escrito desde el dd/mm/aaaa.») si hay. Importes con `administration.euros` y dos decimales en formato español (`3.095,58 €`).
  - `punto_auto(po: dict) -> tuple[str, str]` — `(en qué punto, siguiente paso)`: si `docs.cliente` → «N documentos esperando al cliente; el más antiguo lleva D días.» / «Reclamar la devolución de los N documentos.»; si solo `docs.eipsa` → «Pendiente de EIPSA: N documentos.» / «Corregir y reenviar.»; si nada → «Documentación completa.» / «Facturar lo pendiente.».
  - `que_falta(doc: dict, lado: str) -> str` — cliente: «Que el cliente lo devuelva aprobado.»; EIPSA: «Corregir y reenviar.».
  - `ultimos(po: dict, guardado: dict, n: int = 10) -> list[Correo]` — los `n` más recientes no automáticos + todos los marcados `importante`, sin duplicados, ordenados por fecha descendente.

- [ ] **Step 1: Write the failing tests** `test_guardado`, `test_lo_esencial`, `test_punto`, `test_ultimos`:

```python
tx.guardar_texto("Cliente / Ficticio: S.A.", {"pos": {"1099010610": {"situacion": "Texto de JP"}}})
g = tx.cargar_texto("Cliente / Ficticio: S.A.")
ok(g["pos"]["1099010610"]["situacion"] == "Texto de JP" and g["correos"] == {}, g)
ok(tx.elegir("", "auto") == "auto" and tx.elegir("JP", "auto") == "JP", "elegir")
v = tx.lo_esencial(PO, date(2099, 11, 19))
ok(v[0].startswith("Nos deben 3.095,58 € sin IVA en 1 factura(s); la más antigua (F-99/061, 20/02/2099) lleva 272 días"), v[0])
ok(tx.punto_auto(PO)[0] == "4 documentos esperando al cliente; el más antiguo lleva 111 días.", tx.punto_auto(PO))
u = tx.ultimos(PO_12_CORREOS, {"correos": {"m-viejo": {"importante": True}}})
ok(len(u) == 11 and u[-1]["msgid"] == "m-viejo", [c["msgid"] for c in u])
```

(El test usa `state_dir` apuntado a una carpeta temporal: parchear `core.services.expediente_texto.state_dir`.)

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `core/services/expediente_texto.py`.
- [ ] **Step 4:** Run → `FALLOS: 0`.
- [ ] **Step 5:** Commit `feat(expediente): texto automático y guardado del texto de JP`.

---

### Task 6: `Estado documentación.xlsx`

**Files:**
- Create: `core/services/expediente_excel.py`
- Test: `tests/test_expediente_excel.py`

**Interfaces:**
- Consumes: `Expediente` (Task 4), `cargar_texto`/`elegir`/`lo_esencial`/`punto_auto`/`que_falta`/`ultimos` (Task 5).
- Produces: `exportar(exp: dict, texto: dict, enlaces: dict[str, str], carpeta: Path, corto: str) -> Path` — escribe `carpeta / "Estado documentación.xlsx"` y lo devuelve. `enlaces` = `{msgid: ruta relativa "Correos/<archivo>"}`; si un msgid no está, la celda queda vacía (sin enlace). `corto` = nombre corto del cliente para títulos y cabeceras (p. ej. `"TR"`), saneado de `\/:*?"<>|[]`.

Hojas, en este orden, con título en A1 (negrita 14, `1B3A5C`), nota en A2 (cursiva 10, `666666`), fila 3 vacía, cabecera en fila 4 (blanco negrita sobre `1B3A5C`, borde `C9D3DF`), datos desde la fila 5, filas alternas `F3F6FA`, panel congelado bajo la cabecera, filtro en las hojas 3–5, apaisado ajustado a ancho, zoom 90:

| Hoja | Título (A1) | Nota (A2) | Cabeceras | Anchos |
|---|---|---|---|---|
| `Resumen` | `{cliente}: resumen por PO` | `Datos a {dd/mm/aaaa}. Fuente: ERP, DocFlow y el buzón de documentación.` | PO · Pedido · Proyecto · Lo esencial | 13, 20, 9, 120 |
| `Estado documentación` | `Estado de la documentación por PO` | `Rojo = lo tiene {corto} o su cliente final · Amarillo = lo tiene EIPSA. Los días se cuentan desde el último envío de EIPSA.` | PO · Pedido · Proyecto · Equipo · Total docs. · Aprobados · Esperando a {corto} / cliente · En EIPSA · Días máx. esperando · En qué punto estamos · Siguiente paso · Último correo | 13, 20, 9, 28, 9, 10, 12, 9, 11, 60, 40, 14 |
| `Documentos pendientes` | `Documentos que faltan por cerrar` | `Ordenado por PO y por días de espera. «Veces enviado» es un mínimo según el historial del ERP.` | PO · Pedido · Nº documento {corto} · Título · De qué lado · Dónde está (según {corto}) · Último envío EIPSA · Días esperando · Veces enviado · Qué falta | 13, 15, 27, 55, 15, 38, 12, 10, 9, 55 |
| `Últimos correos` | `Últimos correos importantes` | `Los enlaces abren el correo original guardado en la carpeta Correos, junto a este Excel.` | PO / proyecto · Fecha · De · Asunto · Qué dice · Respuesta / situación · Correo | 13, 11, 24, 45, 60, 38, 13 |
| `Contactos {corto}` | `Contactos de {cliente}, por orden de su última respuesta` | `Arriba, quien ha contestado más recientemente. Solo personas que han escrito al menos un correo; las que solo van en copia, abajo.` | # · Nombre · Cargo · Correo · Teléfono · Último correo enviado · Asunto de ese correo · Correos enviados · PO en los que interviene · Correo | 4, 26, 38, 34, 22, 13, 50, 10, 30, 13 |

Contenido:
- `Resumen`: una fila por PO; «Lo esencial» = viñetas «• » de `lo_esencial` + «• En qué punto estamos: » + punto; ajuste de texto.
- `Estado documentación`: columna «Esperando…» con relleno `FDE2E1`; «En EIPSA» con `FFF2CC` si > 0, `E2F0D9` si 0; punto/siguiente = `elegir(guardado, punto_auto)`; «Último correo» = enlace «Abrir correo» (azul `0563C1` subrayado) al correo más reciente de `ultimos(po)` que esté en `enlaces`; fila final `TOTAL` en negrita con las sumas de Total/Aprobados/Esperando/En EIPSA.
- `Documentos pendientes`: primero los del cliente (por días desc.), luego los de EIPSA y los `reemitir` de JP («EIPSA (espera a {corto})», «Por reemitir»); «De qué lado» = `CLIENTE ({corto})` con `FDE2E1` negrita o `EIPSA` con `FFF2CC` negrita; días ≥ 60 en negrita `B41E1E`; «Dónde está» = `segun_cliente` de JP o vacío; «Qué falta» = `que_falta`.
- `Últimos correos`: por PO en el orden de `exp["pos"]`, `ultimos(po, texto)`; «De» = `EIPSA` si el remitente es del dominio propio, si no el nombre; «Qué dice» = `elegir(que_dice guardado, asunto)`; «Respuesta» = guardado o vacío; enlace si `msgid` en `enlaces`.
- `Contactos {corto}`: `exp["contactos"]` (Task 4), numerados 1..N los que han escrito; cargo/teléfono = guardado de JP si existe, si no el de la firma; después una fila «Solo en copia (no han escrito)» en negrita y los de copia sin número; enlace al último correo enviado si está en `enlaces`.

- [ ] **Step 1: Write the failing test** `test_exportar` (con un `Expediente` inventado de dos PO, un texto guardado y `enlaces` para dos msgid):

```python
ruta = xl.exportar(EXP, TEXTO, {"m1": "Correos/2099-11-18 11h14 - ana - RE estado.eml"}, tmp, corto="CF")
wb = load_workbook(ruta)
ok(wb.sheetnames == ["Resumen", "Estado documentación", "Documentos pendientes", "Últimos correos", "Contactos CF"], wb.sheetnames)
ws = wb["Estado documentación"]
ok([c.value for c in ws[4]][6] == "Esperando a CF / cliente" and ws["A5"].value == "1099010610", [c.value for c in ws[4]])
ok(ws.cell(5, 7).fill.fgColor.rgb.endswith("FDE2E1"), "rojo cliente")
ok(ws.cell(ws.max_row, 1).value == "TOTAL", "fila TOTAL")
uc = wb["Últimos correos"]
links = [c.hyperlink.target for r in uc.iter_rows(min_row=5) for c in r if c.hyperlink]
ok(links == ["Correos/2099-11-18 11h14 - ana - RE estado.eml"], links)             # relativo y solo el que existe
ok(wb["Documentos pendientes"].cell(5, 6).value == "Con su cliente final (CF, 18/11)", "texto de JP en «Dónde está»")
ok(wb["Contactos CF"].cell(5, 2).value == "Luis Ejemplo", "último en responder, primero")
ok(xl.exportar(EXP_SIN_PO, {}, {}, tmp / "vacio", corto="A/B:C").exists(), "cliente con / y : y sin PO → genera")
```

- [ ] **Step 2:** Run `.venv\Scripts\python.exe tests\test_expediente_excel.py` → FAIL.
- [ ] **Step 3:** Implement `core/services/expediente_excel.py` (estilos como constantes de módulo; una función privada por hoja).
- [ ] **Step 4:** Run → `FALLOS: 0`.
- [ ] **Step 5:** Run the whole suite and lint: todos los `tests\test_*.py` con `FALLOS: 0`, `tests\smoke_views.py` y `ruff check --select F401,F811,F841,F821,E402 core tests` sin avisos.
- [ ] **Step 6:** Prueba real de solo lectura (no se commitea nada de su salida): `cargar("<cliente real>")` + `exportar(..., enlaces={}, carpeta=<scratchpad>)` y comparar a ojo con la carpeta validada de JP (hojas, columnas, orden, colores). Anotar diferencias para la fase 2.
- [ ] **Step 7:** Añadir una línea a `CHANGELOG.md` («Expediente de cliente — fase 1: datos y Estado documentación.xlsx (sin pantalla todavía)»). Commit `feat(expediente): Estado documentación.xlsx`.

---

## Fases siguientes (planes aparte, cuando esta esté integrada)

2. Word sencillos (`.DOC\`) + copia de correos a `Correos\` + enlaces relativos verificados + aviso de tamaño (añade `python-docx` a `requirements.txt`).
3. Pantallas: elegir cliente y PO, recopilar en segundo plano, revisar y guardar el texto (botón en Reclamaciones).
4. `INFORME COMPLETO\` (resumen general, Word por PO, anexo con hechos y citas).
5. Borrador IA con `ia.redactar`.
