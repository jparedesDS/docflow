# Excel de Plazos claro para el jefe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Reescribir `seguimiento_excel.exportar` para que el Excel tenga 4 hojas simples (Resumen, Qué hacer primero, Pedidos, Personas), letra grande y solo lo importante.

**Architecture:** Mismo punto de entrada `exportar(datos, ruta) -> str` (lo usan la vista y el correo de los lunes); por dentro, una función por hoja y dos ayudas puras: `prioridad(item, hoy)` y `nombre(persona)`.

**Tech Stack:** openpyxl.

**Spec:** `docs/superpowers/specs/2026-11-18-seguimiento-oferta-planos-design.md`, sección «Excel para el jefe».

## Global Constraints

- Hojas exactamente: `["Resumen", "Qué hacer primero", "Pedidos", "Personas"]`.
- Cada hoja: fila 1 título (20, negrita), fila 2 una frase, fila 3 cabecera (14, negrita, blanco sobre azul oscuro), datos desde la fila 4; `freeze_panes = "A4"`; horizontal, ajustado al ancho, cabecera repetida al imprimir.
- Letra 14 en todo; fechas `dd/mm/aaaa` como fecha (sin hora); días enteros; «—» si no hay dato o el número sale negativo.
- Nunca en el Excel: «None», «p25», «p75», «mediana», «horquilla», decimales.
- Prioridad: URGENTE (rojo) si margen[0] < 0; JUSTO (ámbar) si < 15; CON TIEMPO (verde) si no. Sin margen: días a la entrega < 30 URGENTE, < 60 JUSTO. Falta solo material: «ESPERA MATERIAL» (gris). Sin entrega ni margen: «SIN FECHA» (gris).
- Datos de prueba inventados; commits sin atribución.

## Review Focus

1. Un pedido con la entrega ya pasada: «vencida hace N días», no un número negativo. → prueba en Tarea 1.
2. Cola vacía: la hoja dice que no hay pedidos esperando, no queda en blanco. → prueba en Tarea 1.
3. Horas con zona en las fechas (correo) no rompen openpyxl. → prueba en Tarea 1 (datos con hora del correo).
4. Persona con nombre de usuario («luis-x», «ana.x») sale legible; iniciales («AC») tal cual. → prueba en Tarea 1.
5. Avisos (sin ERP) se ven en el Resumen. → prueba en Tarea 1.

---

### Task 1: Excel en 4 hojas simples

**Files:**
- Modify: `core/services/seguimiento_excel.py` (reescritura)
- Test: `tests/test_plazos.py` (sección «Tarea 7»: sustituir las aserciones del Excel)

**Interfaces:**
- Consumes: `datos` de `seguimiento.cargar()` (`filas`, `resumen`, `cola`, `generado`, `avisos`, `años`).
- Produces: `exportar(datos: dict, ruta) -> str`; `prioridad(item: dict, hoy: date) -> tuple[str, str]` (texto, color hex); `nombre(persona: str) -> str`.

- [ ] **Step 1:** Sustituir en `tests/test_plazos.py` las aserciones del Excel por: nombres de hoja; Pedidos: cabecera en fila 3 con «Llega la oferta» y «Días hasta planos», A4 = `"P-99/001-S00"`, «Llega la oferta» = `date(2099, 1, 1)` (fecha, no datetime), «Días hasta planos» = 7; Resumen contiene «Contestar una oferta» y «5 días»; ninguna celda de ninguna hoja contiene «None», «p25», «mediana» ni un float con decimales; Qué hacer primero con cola vacía dice «No hay pedidos esperando»; `prioridad` en los casos de las Global Constraints (incluido «vencida»); `nombre("luis-x") == "Luis X"`, `nombre("ana.x") == "Ana X"`, `nombre("AC") == "AC"`; Resumen con `avisos=["Sin ERP"]` muestra «Sin ERP».
- [ ] **Step 2:** Ejecutar `tests\test_plazos.py` → falla.
- [ ] **Step 3:** Reescribir `seguimiento_excel.py`.
- [ ] **Step 4:** `tests\test_plazos.py` → `FALLOS: 0`; batería completa → 0.
- [ ] **Step 5:** Commit `feat(plazos): Excel claro, en cuatro hojas y letra grande`.

### Task 2: Comprobarlo con datos reales

- [ ] **Step 1:** Generar el Excel con `seguimiento.cargar(correo=False)` en el scratchpad, exportarlo a PDF con Excel (COM, solo lectura del xlsx) y mirar las páginas: se lee, cabe a lo ancho, nada raro.
- [ ] **Step 2:** Ajustar anchos o textos si hace falta (con su prueba si cambia comportamiento), batería completa, commit.
