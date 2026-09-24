# Cómo está montado DocFlow

Notas para entender el proyecto sin leerlo entero: de dónde salen los datos, qué
hace cada capa y las reglas que no se pueden saltar.

## De dónde sale cada dato

| Dato | Origen | Módulo |
|---|---|---|
| Documentos, estados y revisiones | ERP (PostgreSQL) → `data_erp.xlsx` | `erp_db.py` · `monitoring.py` |
| Pedidos, fechas y % de taller | ERP, tabla de pedidos | `erp_db.py` · `erp_tags.py` |
| Equipos (tags) de un pedido | ERP, tablas de tags | `erp_tags.py` |
| Quién tocó un documento | ERP, registro de cambios | `audit.py` |
| Compras a proveedor | ERP, esquema de compras | `purchases.py` · `vpr.py` |
| Devoluciones del cliente | Correo (IMAP) + portal | `transmittal.py` · `portal_downloads.py` |
| Documentos archivados | Carpeta de red del pedido | `dev_folders.py` |

El ERP se lee **siempre en solo lectura**: la conexión se abre con
`readonly=True` y no hay una sola sentencia de escritura en el proyecto. Si el
ERP no responde, cada servicio devuelve vacío y la app sigue funcionando con los
Excel de `data/`.

## Las capas

```
gui/views/*.py      una vista por sección; solo pinta y recoge lo que el usuario decide
        ↓
core/services/*.py  la lógica: leer el ERP, interpretar correos, escribir ficheros
        ↓
core/utils/*.py     ficheros (sin pisar nada), JSON con bloqueo, HTTP con reintentos
```

Las vistas **nunca** consultan la base de datos ni tocan la red directamente:
lanzan un hilo que llama a un servicio y pintan el resultado al volver. Así la
ventana no se queda colgada cuando la unidad de red tarda.

Esa vuelta se hace siempre con `ui.en_ui(self, …)`, nunca con `after(0, …)` a
pelo: si el usuario cerró la app o el diálogo mientras la consulta estaba en
vuelo, ya no hay nada que pintar y el resultado se descarta en silencio.

## Reglas que no se saltan

- **Nunca se sobrescribe un documento archivado.** Si el destino está ocupado se
  compara tamaño y CRC: si es el mismo fichero, no se hace nada; si es otro, se
  crea la carpeta siguiente del correlativo o se guarda al lado como
  «nombre (2).pdf». La escritura es exclusiva (`open(..., "xb")`), de modo que
  un fallo se convierte en un aviso, nunca en un documento perdido.
- **Las plantillas del cliente se editan como ZIP.** Word y Excel guardan en el
  fichero cosas que cualquier librería que lo reescriba entero se deja por el
  camino: logos, macros, formatos condicionales, cuadros de dibujo. Se cambia
  solo el texto de las celdas y el resto se copia byte a byte
  (`plantilla_docx.py`, `plantilla_xlsx.py`, `formulario_docx.py`).
- **Las contraseñas no viven en el código ni en las preferencias.** Van al
  llavero de Windows o al almacén cifrado local.
- **El correo del cliente se lee sin marcarlo.** Los buzones ajenos se abren en
  modo examen y se descarga el cuerpo sin tocar el estado de leído.

## El ciclo de una devolución

1. Llega el correo del portal → `transmittal.py` reconoce la plataforma y saca
   los documentos con su estado.
2. `portal_downloads.py` descarga el paquete y lo guarda en
   `00 TRANS Y RES\NNN (fecha)` del **pedido base**, junto con el correo.
3. `dev_folders.py` reparte cada PDF en la carpeta `dev.` que le toca, dentro
   del suministro al que pertenece (S00, S10…), con el sufijo del estado:
   `AP` aprobado · `com` comentarios menores · `COM` mayores · `REJ` rechazado.
4. Se apuntan esas carpetas para que la notificación al responsable las enlace.
5. Si algo se quedó sin colocar, el botón del preview permite repartirlo después
   sin volver a pedirle el paquete al portal.

Hay devoluciones que llegan **sin paquete**: Wood avisa de documentos
«2I - FOR INFORMATION ONLY» y el correo no trae enlace de descarga. No hay PDF
que repartir, pero la devolución existe igual, así que se le abre su carpeta
`dev. <Tipo>ev<N> AP` y dentro queda el correo (`archive_email_only`). Es lo
que se hacía a mano, y sin ello el rastro se quedaba solo en «00 TRANS Y RES».

## Las carpetas de revisión

Cada pedido numera sus carpetas a su manera y se respeta la suya:

| Estilo | Ejemplo | Qué es el número |
|---|---|---|
| Correlativo | `rev2-50 AP` | orden de devolución (2) y revisión del cliente (50) |
| Directo | `rev51 COM` | el número **es** la revisión |
| En letra | `revC com` | la revisión es una letra y no hay correlativo |

## Pruebas

En `tests/` hay guiones que se ejecutan a mano y terminan con `FALLOS: n`. No
usan pytest a propósito: se lanzan con el intérprete de la app, contra el código
real, y se leen como una lista de afirmaciones sobre el comportamiento.
