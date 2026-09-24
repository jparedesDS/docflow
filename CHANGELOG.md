# Historia de DocFlow

Lo que ha ido entrando, por meses. Los detalles finos están en los mensajes de
los commits; aquí queda lo que cambió la forma de trabajar.

## Septiembre 2026

- **Devoluciones sin paquete**: los transmittals «for information» de Wood no
  traen enlace de descarga, pero la devolución existe: ahora se le abre su
  carpeta `dev. <Tipo>ev<N> AP` y el correo queda dentro, como el resto.
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
