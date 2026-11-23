# Expediente de un cliente que no paga — diseño

Fecha: 2026-11-23 · Pedido por: JP · Parte de un caso real hecho a mano en
noviembre de 2026 (una carpeta para el jefe de JP con la situación de 10 PO de
un mismo cliente que retenía el pago del 10 % «por documentación»).

> Todos los ejemplos de este documento son **inventados** (P-99/…, PO 1099…,
> `ejemplo.test`): el repositorio es público.

## Para qué

Cuando un cliente se atasca con los pagos y pone de excusa la documentación,
JP necesita sacar **a demanda** una carpeta que cuente, PO a PO:

- qué documentación falta y **de qué lado** está (cliente o EIPSA);
- qué nos deben y desde cuándo, y qué avales siguen vivos;
- qué se ha reclamado, qué han contestado y quién;
- con quién hablar, empezando por quien ha contestado más recientemente;
- los correos que lo prueban, **que se abran con un clic** desde el Excel o el
  Word en cualquier ordenador al que llegue la carpeta.

La leen el jefe de JP, Dirección y, si hace falta, los abogados. No se manda al
cliente.

## Objetivos

1. Generar una carpeta **idéntica** a la que JP validó a mano
   (`ESTADO DOCUMENTACION`) **más** el informe completo que se hizo el primer
   día, en una subcarpeta:

   ```
   ESTADO DOCUMENTACION\
   ├─ Estado documentación.xlsx      (5 hojas, ver «Salidas»)
   ├─ .DOC\                          (un Word sencillo por PO)
   ├─ Correos\                       (.eml / .msg enlazados)
   └─ INFORME COMPLETO\
      ├─ 00 Resumen general.docx
      ├─ PO 10990107xx - P-99-0xx - Informe.docx   (uno por PO)
      └─ Anexo - Detalle.xlsx
   ```

2. Que el **texto redactado** (contexto, situación, hechos, citas, reuniones,
   resumen de cada correo) se revise y corrija **en la app antes de generar**, y
   se guarde: la siguiente vez que se saque el expediente del mismo cliente, el
   texto ya está y solo se retoca lo nuevo.
3. Enlaces **relativos** a `Correos\` desde el principio, verificados uno a uno
   al terminar.

## No objetivos

- Envío programado o automático: es a demanda (decisión de JP).
- Enviar nada al cliente ni contestar correos desde aquí.
- PDF: Word y Excel bastan; Word ya exporta a PDF.
- Calcular intereses de demora o cualquier valoración jurídica.

## Anti-objetivos

- **Un enlace que abra un correo equivocado.** Pasó en el caso real (37 enlaces
  descolocados al insertar filas en un Excel existente). Es peor que no tener
  enlace.
- **Texto que «parezca IA»** o que firme en nombre de JP: nada de firma, nada de
  «En pocas palabras» con viñetas en negrita en los Word, nada de nombrar a gente
  de la casa («el CEO…», «Administración…») en los resúmenes de correo. Lo de
  EIPSA sale como «EIPSA».
- **Esconder lo que es de EIPSA.** Lo pendiente de nuestro lado se enseña igual
  de claro (marcado en amarillo): si no, el documento no vale para negociar.
- Afirmar algo sin fuente: cada cifra sale del ERP, de DocFlow o de un correo
  enlazado.
- Escribir en el ERP, en M: o en el buzón. Todo es lectura.
- Datos reales en el repositorio (código, tests, este documento).

## Restricciones

- Python 3.14 del `.venv`, CustomTkinter, la app corre por escritorio remoto
  (nada de un widget por celda en listas largas).
- Lectura del buzón **lenta** (cientos de correos tardan minutos): siempre en
  segundo plano, con progreso, y con caché por Message-ID para no repetir.
- La IA es opcional (`core/services/ia.py`): sin clave, todo funciona igual con
  texto automático.
- Tests como el resto: scripts que imprimen `FALLOS: N`, datos inventados.

## Enfoques considerados

| | Cómo | A favor | En contra |
|---|---|---|---|
| **A (elegido)** | python-docx para los Word, openpyxl para los Excel | Reutiliza casi tal cual los generadores que produjeron la carpeta validada; tablas, enlaces y sombreados sin esfuerzo | Añade `python-docx` a `requirements.txt` |
| B | Escribir el XML del .docx a mano, como `plantilla_docx` | Sin dependencias | Mucho más código y más frágil para tablas y enlaces; el motivo de `plantilla_docx` (no romper Word **ajenos**) no aplica a documentos que creamos de cero |
| C | Plantillas .docx con marcadores | El aspecto se cambia en Word | Las tablas de longitud variable encajan mal; el formato ya está decidido |

JP eligió **A**.

## Cómo se usa (pantallas)

Se llega desde **Reclamaciones**, con un botón «Expediente de cliente» en la
barra superior. Mismo permiso que Reclamaciones.

**1. Elegir cliente y PO.** Un desplegable de clientes y, debajo, sus PO con
documentación pendiente o facturas sin cobrar, todos marcados. Se desmarca lo que
no entra. Cada PO enseña sus pedidos EIPSA; se puede **añadir o quitar un pedido**
de un PO a mano (hay pedidos vinculados que el ERP no agrupa bien).

```
Cliente: [ EJEMPLO ENGINEERING ▾ ]            Carpeta: [ ...\Escritorio ] [Cambiar]
☑ 1099010610  P-99/023 + P-99/064   Termómetros       12 docs pend.   2 facturas
☑ 1099010910  P-99/079 + P-99/015   Placas orificio    2 docs pend.   2 facturas
☐ 1099050710  P-99/101              Niveles            0 docs pend.   0 facturas
                                                       [ Recopilar → ]
```

**2. Recopilar** (segundo plano): ERP, DocFlow, reclamaciones y correos de las
carpetas de cada pedido. Barra de progreso; se puede seguir usando la app.

**3. Revisar.** Una ficha por PO (lista a la izquierda, ficha a la derecha) y una
ficha «General» para el cliente:

```
┌ General ──────┐ ┌ PO 1099010610 · P-99/023 + P-99/064 ─────────────────────┐
│ 1099010610  ● │ │ Situación del pedido                     [Borrador IA]   │
│ 1099010910  ● │ │ ┌──────────────────────────────────────────────────────┐ │
│ 1099040910  ○ │ │ │ El material está entregado desde septiembre de 2025… │ │
└───────────────┘ │ └──────────────────────────────────────────────────────┘ │
                  │ Documentos pendientes            (lado y «según cliente») │
                  │ Correos  ☑ importante  ☐ cita      Qué dice / Respuesta  │
                  │ Hechos   (sugeridos de los correos marcados, editables)   │
                  └──────────────────────────────────────────────────────────┘
                                                   [ Generar carpeta → ]
```

- La ficha **General** lleva el **contexto** (uno por proyecto del cliente: los
  PO de un mismo cliente pueden ser de proyectos distintos, cada uno con su
  contexto), las **reuniones** y las **citas**.
- `●` = revisado y guardado, `○` = con texto automático sin tocar.
- **Borrador IA** rellena el cuadro a partir de los datos y de los correos
  marcados; JP lo corrige. Sin IA, el cuadro trae las frases automáticas.

**4. Generar.** Escribe la carpeta, copia los correos, comprueba **todos** los
enlaces y avisa si la carpeta comprimida pasa de ~20 MB (límite habitual de
adjuntos), enseñando los correos más pesados.

## Datos

Todo en un servicio sin interfaz (`core/services/expediente.py`) que devuelve un
`dict` por PO; las salidas y la pantalla solo leen ese dict.

**Agrupar pedidos en PO.** `orders.num_ref_order` viene escrito de muchas formas
para el mismo PO: `109901071`, `1099010710`, `1099010710-00`, `109901071-01`,
`1099010710 Sup.04`, incluso con un dígito de menos por errata. Clave: quitar
todo lo que no sea dígito y quedarse con los **9 primeros**. Lo que no encaje lo
corrige JP en la pantalla 1 (y queda guardado).

**Documentos** (`monitoring.get_monitoring_data`, pedidos del PO):
- `Enviado` → lado **cliente**; `Com. Menores/Mayores`, `Rechazado` → **EIPSA**.
- Días esperando = hoy − último envío; veces enviado y primer envío, del
  `Historial Rev.` (son mínimos: el historial antiguo está incompleto).
- **Según el cliente** (dónde dice el cliente que está: «con su cliente final»,
  «en revisión»…) y **dossier por reemitir** (aprobado en una revisión anterior,
  falta la reemisión final): campos **manuales** en la pantalla 3, guardados.

**Facturas** (`purch_fact.invoice_header` + `invoice_detail`):
- Pendiente = sin `pay_date` ni estado «Pagada», **y** no anulada por un abono
  que la cite («ABONO DE NUESTRA FACTURA F-…»). Las reemisiones para confirming
  sin fecha de cobro salen aparte como **«verificar con Administración»**.
- Importe: `tax_base_amount`; si está vacío, la suma del detalle. IVA de la
  cabecera. Menos de 90 días → marcada «reciente».
- Se buscan por `our_ref` (pedido) **y** por `their_ref` (PO), porque hay
  facturas de pedidos vinculados con `our_ref` tipo «P-99/080 (P-99/048)».

**Avales**: pedidos del PO con `warranty_bond_state = EN VIGOR` (importe, banco,
vencimiento, referencia).

**Reclamaciones**: fechas del registro de DocFlow (`claims_log.json`) + correos
de documentacion@ con asunto de reclamación/estado del PO + las fechas citadas
en el historial de esos hilos. Se presentan como «al menos N desde…».

**Correos**: carpetas del buzón de documentación `INBOX/P. 20YY/P-YY-NNN` de
cada pedido, más las carpetas generales que se configuren por cliente (en el
caso real había una carpeta del proyecto), más búsqueda por asunto del número de
PO en INBOX. Se guarda por Message-ID en `state/expediente_correos/`. JP puede
**añadir un .msg/.eml suelto** (correos que llegan a su buzón personal, como
pasó el último día).

**Contactos**: de las cabeceras de los correos del PO (dominio del cliente). Se
ordenan por la fecha de su **último correo enviado**; los que solo van en copia,
abajo. Cargo, teléfono y dirección salen de su firma por heurística y se
corrigen a mano en una tabla de contactos **por cliente**, guardada en `state/`
(nunca en el código).

## Texto

- **Automático**, con los datos: «Quedan 4 documentos con el cliente; el más
  antiguo lleva 111 días», «La factura del 10 % (F-99/061, 3.095,58 €) está
  pendiente desde febrero de 2025»…
- **Borrador IA** (opcional) por PO y del contexto, con `ia.redactar`, dándole los
  datos y los correos marcados. Instrucciones fijas: primera persona del plural,
  sin firma, sin nombres de la casa, sin «En pocas palabras».
- **Lo de JP manda**: lo que haya escrito o corregido se guarda en
  `state/expedientes/<cliente>.json` (contexto por proyecto, situación por PO,
  hechos, reuniones, citas, resumen y respuesta de cada correo, campos manuales
  de documentos) y no se pisa con texto nuevo; si los datos han cambiado desde la
  última vez, la ficha lo avisa para que se revise.

## Salidas

Formato, hojas, columnas y estilo **exactamente como en la carpeta validada**
(se toma como referencia visual; los generadores parten del código que la
produjo).

**`Estado documentación.xlsx`** — las **5 hojas** de la carpeta validada (JP
quitó Reuniones, Hechos y Citas, que quedan en el anexo del informe completo):
*Resumen* (lo esencial por PO) · *Estado documentación* (rojo = cliente,
amarillo = EIPSA, enlace al último correo del PO) · *Documentos pendientes* ·
*Últimos correos* (PO/proyecto, fecha, de, asunto, qué dice, respuesta, enlace) ·
*Contactos <cliente>* (por última respuesta). Cabecera congelada, filtros,
apaisado. *(Corregido el 2026-11-23 al comparar con la carpeta validada.)*

**`.DOC\Documentación PO <po> (<pedido>).docx`** — fecha, título, línea
cliente·proyecto·pedido·equipo; **Contexto general** (el del proyecto del PO);
**Situación del pedido**; Documentos pendientes; Últimos correos (con enlace
«Abrir»); Personas de contacto. Sin firma. Tablas grises sobrias.

**`INFORME COMPLETO\`** — el informe del primer día: resumen general (cifras,
tabla de PO, facturas, citas, cómo retrasa el cliente, a quién dirigirse, datos
fiscales) y un Word por PO (en pocas palabras, datos del pedido, deuda y avales,
documentación, reclamaciones, hechos, contactos, personas de EIPSA, fuentes),
más el Excel anexo con todas las tablas.

**Enlaces**: `Correos\…` desde la raíz, `..\Correos\…` desde las subcarpetas.
Cada enlace se resuelve por **Message-ID → archivo**, nunca por posición. Los
Excel se escriben enteros cada vez (no se insertan filas en uno existente). Al
final se comprueba que cada enlace llega a un archivo; si uno falla, se avisa y
no se da por bueno.

**Correos que se copian**: los marcados como importantes, los enlazados desde
citas, hechos, resumen y contactos. Nombre:
`AAAA-MM-DD HHhMM - remitente - asunto.eml` (sin caracteres prohibidos en
Windows; `&` y acentos se respetan).

## Dónde va el código

| Archivo | Qué |
|---|---|
| `core/services/expediente.py` | Datos por PO (sin interfaz) |
| `core/services/expediente_texto.py` | Frases automáticas, borrador IA, guardado del texto |
| `core/services/expediente_excel.py` | Los dos Excel |
| `core/services/expediente_word.py` | Los Word sencillos y el informe completo |
| `core/services/expediente_export.py` | Carpeta, copia de correos, enlaces, verificación, aviso de tamaño |
| `gui/views/expediente.py` | Las cuatro pantallas |
| `tests/test_expediente*.py` | Datos inventados |

`requirements.txt`: añadir `python-docx`. README, CHANGELOG y ayuda F1.

## Orden de construcción

1. Datos + `Estado documentación.xlsx` (lo que más se usa).
2. Word sencillos + copia de correos + enlaces relativos verificados.
3. Pantallas de selección y revisión con el guardado del texto.
4. Informe completo.
5. Borrador IA.

## Decisiones mías (para que JP las revise)

- Se elige **cliente** y luego sus PO (no escribir PO a mano), y salen marcados
  los que tienen documentación pendiente o facturas sin cobrar.
- Clave de PO = 9 primeros dígitos de `num_ref_order`, con corrección manual.
- «Según el cliente» y «dossier por reemitir» son manuales: el ERP no lo sabe.
- Carpeta por defecto en el Escritorio: `ESTADO DOCUMENTACION <cliente> <fecha>`.
- Se mantiene el nombre `.DOC` de la subcarpeta, como en la carpeta validada
  (en Mac queda oculta; se puede renombrar sin romper enlaces).
- Contexto **por proyecto** dentro del cliente (en el caso real, un PO era de
  otro proyecto del mismo cliente y necesitó el suyo).
- «Cliente» = `offers.client` normalizado (la ingeniería contratante), que es lo
  que agrupa todos sus pedidos aunque se facturen a entidades distintas (en el
  caso real, la empresa y una UTE suya). Los datos fiscales de cada informe salen
  de `purch_fact.clients` de las facturas de ese PO.
- Las **carpetas generales del buzón** de un cliente se eligen en la pantalla 1
  (lista de carpetas del buzón) y se guardan con el cliente.
- **Últimos correos por defecto**: los 10 más recientes de cada PO sin contar
  avisos automáticos (eGesdoc, «DEV:», «Leído:», nuestros recordatorios
  repetidos), más todos los marcados como importantes. Se puede quitar o añadir.
- **Hechos sugeridos**: uno por correo marcado (fecha + resumen), editables; se
  pueden añadir hechos sin correo.
- El texto de «cómo retrasa el cliente» y «a quién dirigirse» del informe
  completo va en la ficha General, con un borrador automático.
- **Personas de EIPSA** del informe completo: de Ajustes ▸ Organización; si no
  hay, una lista editable guardada con el cliente.
- La regla de «sin viñetas en negrita / sin En pocas palabras» es para los Word
  sencillos; el informe completo mantiene su formato original, que sí las lleva.

## Lo que queda al constructor

- Heurística de firmas (cargo/teléfono) y patrones de asunto de reclamación.
- Diseño fino de la pantalla de revisión dentro de lo esbozado.
- Estructura interna del JSON de `state/` y de la caché de correos.
- Cómo se detecta que «los datos han cambiado» desde la última revisión.
