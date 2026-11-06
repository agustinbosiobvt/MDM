# BVT MDM para Google Apps Script

Aplicación interna en JavaScript V8 y HTML, sin compilación ni servidor propio. Incluye Empresas, Clientes, Proveedores y las listas de precios dentro de cada cliente/proveedor. La interfaz está en español y funciona en escritorio y móvil.

**Empieza por `INSTALACION.md`.** El Excel que debes convertir a Google Sheets es **`MDM_Data.xlsx`**. Los otros dos Excel son archivos de muestra para importar desde la aplicación.

## Contenido

- Archivos `.gs`, `.html` y `appsscript.json`: copiar al editor de Apps Script.
- `MDM_Data.xlsx`: base inicial con los nombres de hojas y columnas que espera la aplicación.
- `INSTALACION.md`: instalación, publicación, actualizaciones, copias y recuperación.
- `GUIA_DE_USO.md`: instrucciones para el equipo.
- `PRUEBAS_Y_MIGRACION.md`: datos migrados, resultados de pruebas y comprobaciones pendientes en Google.
- `muestras/`: los dos Excel originales, sin cambios, para probar importaciones.
- `migracion/`: exportación de negocio e historial originales para trazabilidad. No se cargan en Apps Script.

## Estado real de la migración

Se tomó una instantánea de lectura de PostgreSQL el 20 de octubre de 2026. El esquema `mdm` estaba vacío de empresas, clientes, proveedores y precios. Se conservaron sus **427 registros de catálogo** y **23 eventos de auditoría**. Por tanto, las fichas empiezan vacías. Los datos usados en pruebas locales no se incluyeron como datos reales.

Se sigue el documento de migración que ya estaba en la carpeta del proyecto: acceso para todo el dominio BVT, sin roles internos ni pantalla de usuarios. Todos los usuarios admitidos pueden ver y editar. Se conserva el correo del autor de cada cambio.

## Qué queda para ti

Subir el Excel, convertirlo, copiar los archivos al editor y publicar con la cuenta propietaria de BVT. No se ha creado ni desplegado nada en tu cuenta de Google. Las pruebas locales y los resultados de los archivos de muestra están documentados; la comprobación final de Drive, identidad del dominio, permisos y cuotas se hace tras instalar.
