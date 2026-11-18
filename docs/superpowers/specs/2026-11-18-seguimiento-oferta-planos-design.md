# Seguimiento de un pedido: del correo de la oferta a la fábrica — diseño

Fecha: 2026-11-18 · Pedido por: JP (a petición de su jefe) · Revisado el mismo
día tras la primera propuesta.

> **Corrección (2026-11-18, tras implementarlo).** Los compañeros de JP
> aclaran que los planos de `Planos OF` **no** son los que se mandan a fábrica.
> Lo que se manda está en `3-Fabricacion\Envíos`: el técnico envía a fábrica un
> correo («P.Fabricación (envío 01)») y se guarda como .msg, suelto o en
> «envío 01», «envío 02», «superado»… El hito 7 pasa a ser **planos a
> fábrica**: fecha y hora del correo más antiguo de Envíos (también si está en
> «superado»: llegó a fábrica) y su **remitente** (el técnico). Sin correo
> legible, la creación del PDF más antiguo, marcado como «pdf». En 2026, 82 de
> 91 pedidos con Envíos tienen el correo. Donde abajo dice «planos OF», léase
> «planos a fábrica». Esto también contesta la duda de los pedidos con OT y
> Planos OF vacía: sí tienen su correo en Envíos.

## Para qué

El jefe de JP quiere ver, pedido a pedido y **persona a persona**, cuánto se
tarda en cada paso desde que el comercial recibe la petición de oferta (un
correo) hasta que el técnico hace los planos OF y se pasan a fábrica:

1. el comercial recibe la oferta → la contesta → activa el pedido;
2. compras pide el material y llega;
3. el técnico hace los planos OF y se pasan a fábrica.

Con eso quiere decidir qué pedido priorizar para que la fábrica no se quede sin
trabajo.

Lo principal es **el informe con las fechas, los días de cada paso y quién lo
hizo**. El **margen** (qué pedido va primero) es un extra: se hace si sale
fiable y se enseña como horquilla.

## Objetivos

1. Una fila por pedido-suministro con la fecha de cada hito, los días entre
   ellos y la persona de cada paso.
2. Tiempos típicos por paso (mediana y p25–p75): por persona, por tipo de
   equipo y por mes.
3. La cola: pedidos activados que aún no han llegado a fábrica, con lo que les
   falta (planos, material o las dos cosas) y su margen.
4. Tres salidas con los mismos datos: Excel, informe web semanal por correo y
   una sección «Plazos» en DocFlow.

## No objetivos

- Capacidad del taller por horas: las `orders.*_hours` están casi todas a 0.
- Pedidos de Almacén (PA): no pasan por oferta ni planos OF. *Decisión mía.*
- Quién de Compras hizo cada pedido a proveedor: el ERP no lo guarda
  (`supplier_ord_header` no tiene responsable). Compras se mide como
  departamento.

## Anti-objetivos

- Que el tiempo del cliente (presentada → pedido, 50 días de mediana en 2026)
  se cargue a nadie de la casa. Se enseña aparte y marcado como del cliente.
- Que compras y planos se lean como pasos uno detrás de otro: van **en
  paralelo** desde la activación (los dos tardan ~8 días en arrancar).
- Comparar personas con pocos casos como si fuera un ranking: cada cifra por
  persona lleva al lado en cuántos pedidos se basa.
- Escribir en el ERP, en M: o en los buzones. Todo es solo lectura.

## La cadena y de dónde sale cada hito

```
COMERCIAL                         CLIENTE         COMERCIAL
correo RFQ ─► oferta contestada ─► ··· pedido ···► ACTIVACIÓN
                                                     │
                     ┌───────────────────────────────┴──────────────┐
                COMPRAS                                        TÉCNICO
        1.er pedido a proveedor ─► material recibido        planos OF
                     └───────────────────────┬──────────────────────┘
                                          FÁBRICA
                          pasado a fábrica (1.ª OT) ─► 1.er fichaje ─► envío
```

| # | Hito | Fuente | Persona | Precisión |
|---|------|--------|---------|-----------|
| 1 | Correo de la RFQ recibido | Correo en los buzones de Ofertas, enlazado a la oferta del ERP; si no se enlaza, `offers.recep_date` | `offers.responsible` (comercial) | Hora si se enlaza; si no, día |
| 2 | Oferta contestada | Respuesta en Enviados (`ofertas.enrich_replies`); si no, `offers.presentation_date` | El que envía la respuesta; si no, `offers.responsible` | Hora / día |
| 3 | Pedido del cliente | `orders.order_date` | (cliente) | Día |
| 4 | Activación | Correo «ACTIVACIÓN» (ya lo lee `activaciones.py`); si no, `orders.order_date` | Remitente del correo | Hora / día |
| 5 | 1.er pedido a proveedor | `purch_fact.supplier_ord_header.order_date` del pedido (`notes` → pedido, como `purchases.py`) | Compras | Día |
| 6 | Material recibido | Última `deliv_date_1..3` cuando no queda nada `pending` | Compras / proveedor | Día |
| 7 | **Planos a fábrica** | Correo .msg más antiguo de `3-Fabricacion\Envíos` (recursivo): **fecha y hora del correo** y **remitente**; sin correo, creación del PDF más antiguo | El técnico (remitente del correo) | Hora |
| 8 | Pasado a fábrica | 1.ª OT lanzada (`fabrication.fab_order.start_date`) | — | Día |
| 9 | Fábrica empieza | 1.er fichaje (`fabrication.imp_ot`) de sus OTs | — | Día |
| 10 | Envío | `orders.last_date_deliveries` («dd/mm/aaaa») | — | Día |
| — | Entrega contractual | `orders.expected_date` | — | Día |

Lo comprobado con datos reales (solo lectura, 2026):

- Comercial: recibida → presentada, 4 días de mediana (ERP).
- Cliente: presentada → pedido, 50 días.
- Compras: activación → 1.er pedido a proveedor, 8 días (p25–p75 4–14);
  activación → material completo, 28 días (15–83). 50 de 75 pedidos tienen
  compras.
- Técnico: activación → planos OF, 8 días (p75 21). El fichero de Planos OF
  tiene propietario y hora: en 2026 casi todos son de un mismo técnico, con
  otros tres en algunos pedidos.
- Planos OF ≈ 1.ª OT lanzada (mediana 0 días, 59 pedidos): confirma que es el
  momento en que se pasa a fábrica.
- Fábrica: trabajo efectivo según fichajes, 12 días de mediana; planos OF →
  envío, 40 días. La diferencia es espera (material, cola, inspección).

## Enlazar el correo de la oferta (hito 1 y 2)

El ERP solo tiene el día. Para la hora:

- Se leen los buzones de Ofertas (`ofertas.fetch_inbox_offers`, solo lectura) y
  sus respuestas (`enrich_replies`, Enviados de los buzones compartidos y de
  los comerciales que estén dados de alta en Ajustes).
- Un correo se une a una oferta del ERP si: el remitente está en
  `offers.mails`, o la referencia del cliente (`offers.num_ref_offer`) sale en
  el asunto; **y** la fecha del correo cae entre 3 días antes y 1 después de
  `recep_date`. Si salen varios candidatos, gana el más cercano a `recep_date`.
  Referencias genéricas («EMAIL», «-», «PO 110») no sirven para unir.
- Lo que no se une queda con el día del ERP y la fila lo dice («fecha del
  ERP»). Las cifras dicen cuántas ofertas tienen hora de verdad.
- El buzón solo llega hasta donde lo guarde el servidor: las ofertas antiguas
  saldrán con el día del ERP. Es aceptable.
- Las respuestas desde el correo personal de un comercial solo se ven si su
  buzón está dado de alta en Ajustes ▸ Ofertas (con su consentimiento, como ya
  dice `ofertas.py`).

## Casos que hay que tratar

- **Suministros:** cada `P-xx/xxx-Sxx` es una fila; su carpeta se busca con
  `apertura.find_existing_pedido_dir`. Sin carpeta o sin `3-Fabricacion` →
  «sin carpeta», fuera de las medianas de planos. Compras y OTs se apuntan al
  pedido sin suministro (`P-99/021`): se reparten a todos sus suministros y se
  marca como «compartido».
- **Planos OF vacía:** con `porc_workshop` ≥ 99 o `closed = OK` → «fabricado
  sin planos OF en la carpeta», fuera de la cola.
- **Planos antes del pedido**: «antes del pedido», fuera de las
  medianas del técnico.
- **Pedido sin compras:** el material sale «sin compras» (stock), no
  «pendiente».
- **Pedido sin oferta en el ERP** (internos): hitos 1–2 vacíos.
- **Fechas imposibles** (entrega anterior al pedido): se enseñan con aviso y no
  entran en el margen.
- **Personas:** se enseñan por su nombre corto (iniciales del ERP o el usuario
  de Windows sin dominio). Ningún nombre ni usuario va en el código ni en las
  pruebas.
- **Periodo:** 2025 y 2026 por defecto; el año se puede cambiar.

## La cola y el margen (el extra)

La cola son los pedidos activados que aún no han pasado a fábrica. Cada uno
dice qué le falta:

| Planos OF | Material | Qué significa |
|-----------|----------|---------------|
| No | Recibido | **La fábrica podría empezar y espera al técnico.** Lo primero. |
| No | Pendiente | Hay tiempo para los planos mientras llega el material. |
| Sí | Pendiente | Espera al proveedor; no depende de la oficina técnica. |
| Sí | Recibido / sin compras | Listo para fábrica. |

Margen, para los que faltan planos:

```
margen = entrega contractual − hoy − (planos OF → envío típico de ese tipo de equipo)
```

- «Típico» = p25 y p75 de planos OF → envío de los pedidos ya enviados del
  mismo `offers.material`, histórico 2024–2026. Se enseña como horquilla
  («entre −5 y +30 días») y con «basado en N pedidos».
- Con menos de 5 pedidos de ese tipo, se usan todos los tipos y se dice.
- Orden de la cola: primero «material recibido, sin planos»; dentro de cada
  grupo, por el extremo pesimista del margen; si empatan, por la entrega.
- Su precisión: los rangos por tipo son amplios (vainas 15–112 días), porque
  dependen del proveedor y de la carga de la fábrica. Sirve para ver qué está en
  riesgo, no para dar una fecha.

## Salidas

1. **Excel** (`openpyxl`, como `ofertas.export_excel`): «Pedidos» (una fila por
   suministro: hitos, días y personas), «Cola» (lo que falta y el margen),
   «Por persona» (mediana, p25–p75 y nº de casos de su paso) y «Resumen»
   (por paso, tipo de equipo y mes).
2. **Informe web semanal:** módulo nuevo en `core/services/interactive_report/`
   con el estilo de los existentes. Contiene la cadena con los días típicos de
   cada paso, la cola, los tiempos por persona y la tabla de pedidos. Un tipo
   nuevo de envío programado en `scheduled_reports.py` (lunes 8:00,
   **desactivado** hasta que JP ponga los destinatarios), con el Excel adjunto.
3. **Sección «Plazos» en DocFlow:** pestañas «Cola», «Pedidos» y «Por
   persona»; botones «Excel» e «Informe web»; un clic abre la carpeta del
   pedido. Tablas en Canvas (`pilltable`), por el RDP.

## Cómo se construye

- `core/services/seguimiento.py` hace todo el cálculo; las tres salidas solo lo
  pintan. Lo que calcula hitos, tramos, cola y margen recibe datos ya leídos
  (filas del ERP, correos y fechas de carpetas): se prueba sin ERP, sin correo
  y sin M:.
- Lectores separados, cada uno con su caché: ERP (ofertas, pedidos, compras,
  OTs, fichajes), correo (ofertas y activaciones) y carpetas.
- Carpetas: se guarda en `state/seguimiento_planos.json` la fecha, la hora y el
  propietario del primer fichero de cada `Planos OF`, con la fecha de
  modificación de la carpeta; solo se vuelve a leer la que ha cambiado. El
  propietario se lee con la API de Windows (no con PowerShell por fichero).
- Correo: el escaneo de buzones es lento; se hace en segundo plano y se guarda
  el enlace correo ↔ oferta en `state/seguimiento_correos.json`, para no
  depender de que el correo siga en el buzón.
- Todo en hilos, nunca en la interfaz. ERP en solo lectura; buzones con
  EXAMINE/BODY.PEEK.
- Pruebas con datos inventados (P-99/…, ejemplo.test): hitos, tramos en
  paralelo, cola por grupos, margen, enlace correo ↔ oferta y caché de
  carpetas con carpetas temporales. Además, `import_all`, `smoke_views` y ruff.

## Enfoques considerados

- **Todo desde los correos:** da la hora, pero solo de lo que siga en el buzón,
  y no tiene compras, planos ni fábrica. Descartado como fuente única.
- **Solo el ERP:** no tiene planos OF, ni técnico, ni hora. Descartado.
- **ERP + correos + carpeta Planos OF + fichajes — elegido:** cada hito sale
  de donde de verdad ocurre; el correo pone la hora cuando se puede enlazar y
  el ERP cubre el resto.
- Salida: JP pidió las tres (Excel, informe web semanal y sección en la app)
  sobre un único cálculo.

## Decisiones mías (para revisar)

- Fuera los PA; periodo por defecto 2025–2026.
- El técnico de un pedido es el remitente del primer correo de Envíos.
- Compras se mide como departamento (el ERP no guarda quién).
- El margen usa planos OF → envío, no los fichajes, porque incluye la espera.
- El envío programado nace desactivado.
- Sección «Plazos» junto a Producción en el menú.

## Para quien lo construya

El diseño de columnas del Excel, los gráficos del informe web y el diseño
visual de la sección, siguiendo lo que ya hacen Informes, Producción y Ofertas.
