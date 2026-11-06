# Migración y verificación

Fecha de la entrega: 20 de octubre de 2026. Base consultada: PostgreSQL local, contenedor `bvt-mdm-db-1`, base `mdm`. Las exportaciones se hicieron en transacciones de solo lectura. No se modificaron tablas ni datos del proyecto original.

## Datos convertidos

| Origen | Destino | Filas |
| --- | --- | ---: |
| `mdm.company`, `customer`, `vendor` y sus `party` | Companies / Customers / Vendors | 0 |
| Direcciones, contactos y códigos Amazon | Addresses / Contacts / VendorCodes | 0 |
| Listas y líneas/precios de listas | PriceLists y archivos de versión | 0 |
| Plantillas de importación | MappingTemplates | 0 |
| Países ISO | Lookups (`country`) | 249 |
| Monedas ISO | Lookups (`currency`) | 155 |
| Condiciones de pago | Lookups (`payment_term`) | 6 |
| Incoterms | Lookups (`incoterm`) | 11 |
| Tipos de precio | Lookups (`price_type`) | 6 |
| Auditoría anterior | AuditLog | 23 |

El Excel tiene 11 hojas con cabeceras en la fila 1. Incluye `ImportJobs` para el estado de las importaciones nuevas. No contiene registros de prueba. La exportación original de negocio y el historial completo están en `migracion` para mantener también los identificadores de usuario y metadatos de auditoría históricos que no necesita la nueva interfaz.

No se migran contraseñas, configuración `.env`, secretos OAuth, cookies, sesiones ni estados de login. El control de acceso se sustituye por el despliegue de Google Workspace, según el plan entregado. No se crean tipos de cambio.

## Pruebas locales realizadas

La lógica `.gs` de la entrega se ejecutó en V8/Node con servicios de Google simulados. Los datos de los dos Excel se leyeron de sus valores guardados reales. Se ejercitaron las llamadas de la aplicación y sus escrituras sobre hojas simuladas.

- 116 comprobaciones de lógica, incluyendo las 27 pruebas puras de `runTests`, identidad interna/externa/vacía, verificación de sesión de página, códigos duplicados, empresa predeterminada, contactos principales, códigos Amazon, referencias, control de versiones, bloqueo de escrituras y guardado/activación de listas.
- Validación por bloques, repetición de un bloque tras una respuesta perdida y repetición del guardado final: sin duplicar líneas ni revisiones.
- Guardado de marca/categoría sin modificar precios; rechazo de exclusiones en versiones activas y de retirada de versiones históricas.
- Prueba de navegador en Chrome sin interfaz: Inicio, listado y detalle de proveedor con precios, edición guardada, entrada/cancelación del importador, creación de empresa y vista móvil sin desbordamiento horizontal. También se completaron selección de hoja, mapeo, validación y guardado del asistente con una hoja de origen simulada a partir del Excel Nobby real. Sin errores JavaScript en esos recorridos.
- El saneamiento XLSX retiró 312 fórmulas del archivo Amazon y 53.326 del Nobby. Se verificó que **todos los valores guardados de todas las hojas** seguían iguales y que no quedaban fórmulas ejecutables en las hojas de las copias saneadas.
- El Excel de base se abrió de nuevo con un lector independiente. Se comprobaron nombres/cabeceras, recuentos y ausencia de fórmulas. Se revisó visualmente la presentación de las hojas.

## Resultados de los archivos reales

| Resultado | Amazon MX | Nobby |
| --- | ---: | ---: |
| Hoja | ALL | Tabelle1 |
| Fila de cabecera | 4 | 7 |
| Primera fila de datos | 7 | 8 |
| Líneas | 7.515 | 7.515 |
| Filas rechazadas | 0 | 0 |
| Advertencias EAN | 1 | 1 |
| Grupos duplicados | 0 | 0 |
| ASIN vacíos | 1.970 | 1.970 |
| Precios totales | 15.030 | 45.061 |

| Tipo / moneda | Amazon MX | Nobby |
| --- | ---: | ---: |
| Import cost / USD | 7.515 | 0 |
| RRP / MXN | 7.515 | 7.515 |
| Purchase / EUR | 0 | 7.486 |
| RRP / EUR | 0 | 7.515 |
| RRP ex VAT / MXN | 0 | 7.515 |
| Retailer cost / MXN | 0 | 7.515 |
| Retailer cost / USD | 0 | 7.515 |

El EAN `43917996264` se conserva tal como aparece. El UPC `043917996264` no se convierte a número. El primer precio de importación Amazon es `78.1126 USD`; el RRP, `3728.8200 MXN`. Las 29 celdas vacías de compra Nobby no se convierten en precios cero.

## Qué debes verificar después de subirlo

Las pruebas locales no acreditan una implementación real de Apps Script. Quedan para el entorno BVT:

1. Ejecutar `setup`, `runTests` y una copia manual.
2. Abrir con dos cuentas BVT y comprobar que una cuenta externa no entra.
3. Importar ambos originales o ejecutar `runSampleTests` y contrastar los recuentos anteriores. Este paso verifica la conversión real de Drive, que localmente fue simulada.
4. Abrir la misma ficha en dos navegadores: guardar desde uno y confirmar que el otro rechaza una versión antigua.
5. Importar un pequeño archivo con dos claves iguales: impedir activación, excluir la sobrante y activar. Reimportar para verificar que la revisión anterior se conserva.
6. Revisar al día siguiente la ejecución del activador nocturno y los archivos de `Backups`.

## Decisiones de adaptación

- Cada versión de precios se guarda en un Google Sheets independiente. En la hoja `Lines`, los pares `p0_amount`/`p0_currency`, etc., corresponden al mapeo en `PriceLists.price_columns`. No hay un número fijo de monedas por producto.
- Los importes son **cadenas decimales canónicas de cuatro posiciones**, no números binarios. Así se conserva el rango y precisión de PostgreSQL `NUMERIC(18,4)`, que excede la precisión numérica de Sheets/JavaScript. Los recuentos y versiones son numéricos; los GTIN, ASIN y códigos son texto.
- Las fechas de datos se almacenan como ISO. Los instantes incluyen zona UTC; las fechas comerciales usan `YYYY-MM-DD`. El proyecto y los activadores están en Europe/Madrid.
- La validación procesa 400 filas por llamada. La importación publica una lista solo al terminar. Los reintentos usan el cursor guardado y un ID estable para no duplicar resultados.
- Las escrituras usan un bloqueo del script y versión por registro. Google Sheets no ofrece transacciones SQL entre hojas: una interrupción del servicio durante una operación de varios registros puede exigir revisión o recuperación. Los reintentos del importador están contemplados; no se promete atomicidad general de una base relacional.
- El historial se agrega desde la app. El propietario de Drive mantiene capacidad de edición directa; no existe el permiso SQL INSERT-only del sistema anterior.
- No hay garantía de tiempos de respuesta en Google antes de la prueba real. Las cuotas publicadas actualmente incluyen seis minutos por ejecución. La conversión inicial es una sola llamada y puede fallar con libros más complejos aunque no superen 20 MB.

Referencias: [cuotas de Apps Script](https://developers.google.com/apps-script/guides/services/quotas), [identidad del usuario](https://developers.google.com/apps-script/reference/base/session), [aplicaciones web](https://developers.google.com/apps-script/guides/web), [Drive avanzado v3](https://developers.google.com/apps-script/advanced/drive), [aislamiento de HTML Service](https://developers.google.com/apps-script/guides/html/restrictions).
