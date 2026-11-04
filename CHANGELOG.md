# Historia de DocFlow

Lo que ha ido entrando, por meses. Los detalles finos están en los mensajes de
los commits; aquí queda lo que cambió la forma de trabajar.

## Octubre y noviembre 2026

- **Activaciones de pedidos**: los correos «ACTIVACIÓN P-26/…» de Comercial
  (al buzón compartido o al personal, una vez aunque lleguen a los dos) crean
  «Abrir pedido …» en la Agenda con la PO, la entrega, el plazo y lo que piden
  de documentación. En «Nuevo pedido» salen arriba: pulsar una rellena el
  formulario (pedido, suministro, S.REF, fechas) y localiza la carpeta de ese
  suministro. Se cierran solas al procesar el pedido o cuando su
  00 DOCUMENTACIÓN ya tiene un Planning o un VDDL de después del correo.
- **Carpetas de devolución**: nuestra revisión ya no se lee del ERP (se rellena
  a mano y se salta revisiones) sino de lo archivado: `rev<nuestra>-<cliente>`,
  con el formato de las carpetas hermanas y en la carpeta `dev.` donde ya están
  las devoluciones anteriores. Un documento anulado (VOID) va a la revisión que
  anula. Las descargas de los portales van de una en una, aunque haya dos
  DocFlow abiertos.
- **Agenda y avisos**: los correos «Cálculos realizados» y «planos hechos» de
  Técnico crean su tarea con carpeta, revisión y notas, y se cierran solas
  cuando el seguimiento muestra el documento enviado. La sincronización con
  Documentos respeta las tareas completadas o borradas a mano.
- **Correo**: el buzón solo se lee (EXAMINE); solo Correo y Devoluciones
  marcan como leído, y Ofertas ya no escribe en los buzones de comercial. La
  lista carga en una petición (2 s → 0,2 s) y, con la clave de IA, «Análisis
  IA» resume el correo abierto.
- **IA opcional con Claude Haiku 5.5**: los párrafos de los informes y el
  análisis de Correo, en `core/services/ia.py`. Sin clave no se llama a nada.
- **Más rápido por escritorio remoto**: volver a una sección ya no vuelve a
  medir cada celda de sus tablas (Calidad 400 → 80 ms), y DocuSign y las
  subcarpetas de «Nuevo pedido» se dibujan en un solo lienzo (DocuSign
  600 → 80 ms). Las ventanas encajan a cualquier escala de Windows (125 %).
- **Limpieza**: fuera ~625 líneas de código muerto, datos inventados en las
  pruebas (nada de clientes reales en el repositorio público), y los Excel
  temporales y las copias del ERP ya no se acumulan en `data/`.

## Septiembre 2026

- **Ni un dato de la empresa en el código**: equipo, clientes, libro de pedidos,
  servidores y buzones salen del repositorio (que es público) a
  `state/organizacion.json`, y se rellenan desde **Ajustes ▸ Organización**.
  Una instalación nueva arranca en blanco y funciona igual.
- **Devoluciones sin paquete**: los transmittals «for information» de Wood no
  traen enlace de descarga, pero la devolución existe: ahora se le abre su
  carpeta `dev. <Tipo>\rev<N> AP` y el correo queda dentro, como el resto.
- **Documentos cerrados de un pedido**: botón «⤓ Comentados del cliente» en
  Pedidos (y `tools/finales_egesdoc.py` para la línea de comandos) que baja de
  eGesDoc el PDF comentado de todos los documentos en Final de un PO —los 345
  de un pedido son 345 clics—. Se puede parar y seguir: lo que ya está en la
  carpeta no se vuelve a pedir. Solo Técnicas Reunidas por ahora.
- **VPR**: el informe mensual de avance para el cliente, con los datos del ERP y
  sobre su propia plantilla de Word.
- **Portadas**: se rellena la plantilla del cliente (Word o Excel) con los datos
  de cada documento; los campos se emparejan **arrastrándolos** y el
  emparejamiento queda guardado por cliente.
- **Devoluciones de los portales, de punta a punta**: descarga automática cada
  diez minutos de eGesDoc, AYESA, SACYR, PRODOC y Document Space, y archivado de
  cada PDF en su carpeta `dev.` del pedido, con el sufijo del estado.
- **Nunca se sobrescribe un documento archivado**: se compara tamaño y CRC, y lo
  que no cabe va a la carpeta siguiente o al lado.
- **La app se organiza por departamentos** y estrena Compras, Producción,
  Calidad, Administración y Almacén, además de la trazabilidad de documentos.
- **Los datos salen del ERP** (PostgreSQL, solo lectura): documentos, equipos,
  órdenes de fabricación, compras y cabecera de pedido.
- **Interfaz**: paleta de comandos `Ctrl+K`, ayuda contextual con `F1`, Inicio
  centrado en «lo de hoy» y menú lateral con scroll.

## Julio 2026

- El pedido, la PO y el nº de documento propio se resuelven contra el ERP a
  partir del número que usa el cliente.

## Junio 2026

- **Apertura de pedidos**: carpetas, Planning con macros e índice de documentos.
- **Informes web interactivos** (semanal, mensual, ejecutivo y por pedido), con
  tablas filtrables y descarga en PDF.
- **Avisos a Teams** y subida de informes a **Nextcloud**.
- **Envíos programados** de pendientes por persona.
- Secciones de **Pedidos, Ofertas, DocuSign y Ajustes** con permisos por usuario.
- Parser del portal **AYESA**.

## Mayo 2026

- Primer arranque: **devoluciones** de los portales de correo, con notificación
  al responsable, y **devolución manual** con la misma plantilla.
- Login con iniciales y contraseña local (PBKDF2-SHA256).
- Communication Matrix y gestor de la fuente de datos.
